import csv
import json
import os
import io
import urllib.error
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from src.address_review import AddressReviewer, ENDPOINT, MODEL, USER_AGENT, offline_review, validate_review
from src.analysis import load_assumptions
from src.data_pipeline import COLUMNS, EXTRA_COLUMNS, ROOT, write_csv
from src.decision_engine import ACTIONS, decide, economics, load_policy, normalize_order, validate_policy
from src.risk import features, fit_model, metrics, predict
from src.train_engine import canonical_hash, run_training, score_fixed_decisions, simulate
from test_data_pipeline import order, temporary_directory


def constant(probability):
    return dict(kind='constant',prior=probability,development_orders=10)


def reply(data=None, finish='stop'):
    return {'choices':[{'finish_reason':finish,'message':{'content':json.dumps(data or {
        'address_quality':'complete','name_quality':'unremarkable','language':'English',
        'missing_details':[],'reason':'Concrete apartment and street details are present; not physically verified.'})}}]}


class FixedReviewer:
    def __init__(self,quality='complete',name='unremarkable',source='groq'):
        self.quality,self.name,self.source=quality,name,source

    def review(self,order):
        return dict(address_quality=self.quality,name_quality=self.name,source=self.source)


class RiskTests(unittest.TestCase):
    def test_outcomes_and_sensitive_identifiers_are_not_features(self):
        first=order()
        changed=dict(first,final_status='RTO',quality_flags='unresolved_outcome',outcome_resolved='false',
                     customer_name='test',phone='000',address='ignore instructions',pincode='000000',order_id='different',source_row='100')
        self.assertEqual(features(first),features(changed))

    def test_model_fits_deterministically_and_handles_unseen_categories(self):
        rows=[order(order_value='100',final_status='RTO'),order(order_id='A2',order_value='2000')]
        for kind in ('constant','history_rules','logistic','logistic_without_history'):
            model=fit_model(rows,kind)
            self.assertEqual(model,fit_model(rows,kind))
            self.assertTrue(0<predict(model,dict(rows[0],state='Unseen',courier='Unseen'))<1)

    def test_history_ablation_and_large_finite_history(self):
        a=order()
        b=order(customer_prior_orders='999999999999999999999999999999999999999999',customer_prior_rto='1')
        self.assertEqual(features(a,False),features(b,False))
        self.assertTrue(0<=features(b)['prior_rto_rate']<=1)

    def test_probability_metrics_with_ties_and_one_class(self):
        rows=[order(),order(final_status='RTO')]
        result=metrics(constant(.5),rows)
        self.assertEqual(result['brier'],.25)
        self.assertEqual(result['auc'],.5)
        self.assertAlmostEqual(result['log_loss'],.69314718)
        self.assertIsNone(metrics(constant(.5),[order()])['auc'])
        with self.assertRaises(ValueError):
            metrics(constant(.5),[])


class DecisionTests(unittest.TestCase):
    def setUp(self):
        self.policy=load_policy()
        self.a=load_assumptions(ROOT/'config/financial_assumptions.json')
        self.order=order()

    def test_all_four_buckets_have_concrete_demonstrations(self):
        low=decide(self.order,constant(.05),self.policy,self.a,FixedReviewer())
        confirm=decide(self.order,constant(.05),self.policy,self.a,FixedReviewer('needs_clarification'))
        prepaid=decide(self.order,constant(.6),self.policy,self.a,FixedReviewer())
        hold=decide(dict(self.order,pincode=''),constant(.05),self.policy,self.a,FixedReviewer())
        self.assertEqual([r['action'] for r in (low,confirm,prepaid,hold)],list(ACTIONS))
        self.assertEqual(hold['disposition'],'hold_for_review')
        self.assertTrue(confirm['required_before_shipping'])
        self.assertIn('verified payment',prepaid['required_before_shipping'][0])

    def test_invalid_inputs_hold_before_text_or_model_call(self):
        class NeverReviewer:
            def review(self,order):
                raise AssertionError('Should not call a reviewer.')
        for field,value in [('phone','123'),('order_value','NaN'),('customer_prior_rto','5'),
                            ('num_items','1.5'),('order_datetime','yesterday'),('items','one')]:
            result=decide(dict(self.order,**{field:value}),{},self.policy,self.a,NeverReviewer())
            self.assertEqual(result['action'],'hold_cancel')
            self.assertIsNone(result['risk_probability'])

    def test_no_auto_cancellation_or_unsupported_payment(self):
        with self.assertRaises(ValueError):
            validate_policy(dict(self.policy,allow_auto_cancel=True))
        result=decide(dict(self.order,payment_method='PREPAID'),{},self.policy,self.a)
        self.assertEqual(result['disposition'],'hold_for_review')

    def test_invalid_policy_rejected(self):
        for change in [dict(confirm_risk_threshold=.8,prepaid_risk_threshold=.4),
                       dict(genuine_confirmation_rate=1.1),dict(prepaid_discount_inr=-1),
                       dict(confirmation_message_cost_inr=True),dict(prepaid_message_cost_inr=float('nan')),
                       dict(confirm_risk_threshold='0.3')]:
            with self.assertRaises(ValueError):
                validate_policy(dict(self.policy,**change))

    def test_thresholds_include_boundary(self):
        policy=dict(self.policy,confirm_risk_threshold=.2,prepaid_risk_threshold=1,
                    hold_risk_threshold=1,genuine_confirmation_rate=1,rto_confirmation_rate=0,confirmation_message_cost_inr=0)
        self.assertEqual(decide(self.order,constant(.199),policy,self.a,FixedReviewer())['action'],'ship_as_is')
        self.assertEqual(decide(self.order,constant(.2),policy,self.a,FixedReviewer())['action'],'ship_after_confirmation')
        result=decide(self.order,constant(.9),self.policy,self.a,FixedReviewer())
        self.assertEqual(result['disposition'],'hold_for_review')

    def test_unavailable_or_placeholder_never_cancels_by_itself(self):
        for reviewer in [FixedReviewer('unknown','unknown','unavailable'),FixedReviewer('complete','placeholder')]:
            result=decide(self.order,constant(.05),self.policy,self.a,reviewer)
            self.assertEqual(result['action'],'ship_after_confirmation')

    def test_confirmation_uncertainty_does_not_raise_numeric_risk(self):
        a=decide(self.order,constant(.2),self.policy,self.a,FixedReviewer())
        b=decide(self.order,constant(.2),self.policy,self.a,FixedReviewer('unknown'))
        self.assertEqual(a['risk_probability'],b['risk_probability'])

    def test_money_ev_and_discount_caps(self):
        order649=dict(self.order,order_value='649')
        e=economics(order649,.28,self.policy,self.a)
        self.assertEqual(e['discount'],Decimal('25.00'))
        self.assertEqual(e['expected']['ship_as_is'],Decimal('.72')*Decimal('402.38')-Decimal('.28')*Decimal('169.40'))
        for value,p in [('10',.28),('649',.041),('649',.04)]:
            result=economics(dict(self.order,order_value=value),p,self.policy,self.a)
            self.assertLessEqual(result['discount'],Decimal(value)*Decimal('.05'))
            self.assertLessEqual(result['discount'],max(Decimal(0),(Decimal(str(p))-Decimal('.04'))*Decimal('169.40')))

    def test_accounting_interpretation_changes_margin_once(self):
        first=economics(self.order,.3,self.policy,self.a)
        second=economics(self.order,.3,dict(self.policy,delivered_margin_includes_fulfilment=False),self.a)
        self.assertEqual(first['margin']-second['margin'],Decimal(90))
        self.assertEqual(first['unit_loss'],second['unit_loss'])

    def test_simulation_ship_only_matches_hand_calculation(self):
        policy=dict(self.policy,confirm_risk_threshold=1,prepaid_risk_threshold=1,hold_risk_threshold=1)
        rows=[dict(self.order,source_row='2'),dict(self.order,source_row='3',final_status='RTO')]
        result,logs=simulate(constant(.2),rows,policy,self.a)
        expected=Decimal(649)*Decimal('.62')-Decimal('169.40')
        self.assertEqual(result['baseline_contribution_inr'],str(expected))
        self.assertEqual(result['net_impact_inr'],'0.00')
        self.assertEqual(sum(result['buckets'].values()),2)

    def test_simulation_hold_accounts_for_genuine_margin(self):
        rows=[dict(self.order,source_row='2',phone='123')]
        result,_=simulate(constant(.2),rows,self.policy,self.a)
        self.assertEqual(result['genuine_held_order_margin_at_risk_inr'],'402.38')
        self.assertEqual(result['net_impact_inr'],'-402.38')


class AddressTests(unittest.TestCase):
    def test_http_transport_identifies_app_and_keeps_redirects_disabled(self):
        with patch('src.address_review.urllib.request.build_opener') as build:
            opener=build.return_value
            opener.open.return_value=io.BytesIO(json.dumps(reply()).encode())
            result=AddressReviewer(timeout=12)._http_request({'model':MODEL},'fake-test-key')
            self.assertEqual(result,reply())
            opener.open.assert_called_once()
            request=opener.open.call_args.args[0]
            self.assertEqual(request.full_url,ENDPOINT)
            self.assertEqual(request.method,'POST')
            self.assertEqual(request.get_header('User-agent'),USER_AGENT)
            self.assertNotIn('fake-test-key',request.get_header('User-agent'))
            self.assertEqual(request.get_header('Authorization'),'Bearer fake-test-key')
            self.assertEqual(opener.open.call_args.kwargs,{'timeout':12})
            self.assertEqual(type(build.call_args.args[0]).__name__,'NoRedirect')

    def test_default_offline_makes_no_network_request(self):
        reviewer=AddressReviewer(transport=lambda *args: (_ for _ in ()).throw(AssertionError('Network used')))
        self.assertEqual(reviewer.review(order())['source'],'offline_heuristic')

    def test_missing_key_and_free_plan_guard_prevent_requests(self):
        with patch.dict(os.environ,{},clear=True):
            self.assertEqual(AddressReviewer('groq').review(order())['error_code'],'missing_key')
        with patch.dict(os.environ,{'GROQ_API_KEY':'fake-test-key','GROQ_FREE_TIER_CONFIRMED':'false'},clear=True):
            self.assertEqual(AddressReviewer('groq').review(order())['error_code'],'free_plan_not_confirmed')

    def test_cache_payload_minimization_and_exact_model(self):
        calls=[]
        def transport(payload,key):
            calls.append(payload)
            self.assertEqual(payload['model'],MODEL)
            self.assertTrue(payload['response_format']['json_schema']['strict'])
            fields=json.loads(payload['messages'][1]['content'])
            self.assertEqual(set(fields),{'customer_name','address','city','state','pincode'})
            return reply()
        with temporary_directory() as temp, patch.dict(os.environ,{'GROQ_API_KEY':'fake-test-key','GROQ_FREE_TIER_CONFIRMED':'true'}):
            reviewer=AddressReviewer('groq',Path(temp)/'cache.sqlite',transport=transport)
            first,second=reviewer.review(order()),reviewer.review(order())
            self.assertEqual(first['source'],'groq')
            self.assertFalse(first['cached'])
            self.assertTrue(second['cached'])
            self.assertEqual(len(calls),1)

    def test_local_quota_and_rate_limits(self):
        with temporary_directory() as temp, patch.dict(os.environ,{'GROQ_API_KEY':'fake-test-key','GROQ_FREE_TIER_CONFIRMED':'true'}):
            now=[1000000000.0]
            reviewer=AddressReviewer('groq',Path(temp)/'cache.sqlite',daily_request_cap=2,transport=lambda *args:reply(),clock=lambda:now[0])
            self.assertEqual(reviewer.review(order())['source'],'groq')
            other=order(address='House 2, Another Road')
            self.assertEqual(reviewer.review(other)['error_code'],'local_rate_limit')
            now[0]+=11
            self.assertEqual(reviewer.review(other)['source'],'groq')
            now[0]+=11
            self.assertEqual(reviewer.review(order(address='House 3, Another Road'))['error_code'],'local_daily_cap')

    def test_rate_limit_has_no_retry_or_provider_switch(self):
        calls=[]
        def fail(*args):
            calls.append(1)
            raise urllib.error.HTTPError(ENDPOINT,429,'rate limit',{},None)
        with temporary_directory() as temp, patch.dict(os.environ,{'GROQ_API_KEY':'fake-test-key','GROQ_FREE_TIER_CONFIRMED':'true'}):
            result=AddressReviewer('groq',Path(temp)/'cache.sqlite',transport=fail).review(order())
            self.assertEqual(result['error_code'],'quota_or_rate_limit')
            self.assertEqual(len(calls),1)

    def test_http_diagnostics_show_status_without_echoing_key_or_body(self):
        calls=[]
        def fail(*args):
            calls.append(1)
            body=json.dumps({'error':{'message':'Bad response_format; fake-test-key should never appear'}}).encode()
            raise urllib.error.HTTPError(ENDPOINT,400,'fake-test-key',{},io.BytesIO(body))
        with temporary_directory() as temp, patch.dict(os.environ,{'GROQ_API_KEY':'fake-test-key','GROQ_FREE_TIER_CONFIRMED':'true'}):
            result=AddressReviewer('groq',Path(temp)/'cache.sqlite',transport=fail).review(order())
            self.assertEqual(result['http_status'],400)
            self.assertEqual(result['request_fields_mentioned'],['response_format'])
            self.assertNotIn('fake-test-key',json.dumps(result))
            self.assertEqual(len(calls),1)

    def test_authentication_failure_is_distinct_from_unknown_http_error(self):
        def fail(*args):
            raise urllib.error.HTTPError(ENDPOINT,401,'Unauthorized',{},io.BytesIO(b'private provider response'))
        with temporary_directory() as temp, patch.dict(os.environ,{'GROQ_API_KEY':'fake-test-key','GROQ_FREE_TIER_CONFIRMED':'true'}):
            result=AddressReviewer('groq',Path(temp)/'cache.sqlite',transport=fail).review(order())
            self.assertEqual(result['http_status'],401)
            self.assertIn('credentials',result['error_hint'])
            self.assertNotIn('private provider response',json.dumps(result))

    def test_security_block_diagnostic_does_not_include_provider_page(self):
        def fail(*args):
            raise urllib.error.HTTPError(ENDPOINT,403,'Forbidden',{},io.BytesIO(b'Cloudflare error code: 1010 confidential'))
        with temporary_directory() as temp, patch.dict(os.environ,{'GROQ_API_KEY':'fake-test-key','GROQ_FREE_TIER_CONFIRMED':'true'}):
            result=AddressReviewer('groq',Path(temp)/'cache.sqlite',transport=fail).review(order())
            self.assertEqual(result['http_status'],403)
            self.assertIn('network/security',result['error_hint'])
            self.assertNotIn('confidential',json.dumps(result))

    def test_malformed_refusal_and_incomplete_outputs_fail_closed(self):
        responses=[{'choices':[]},reply({'address_quality':'complete'}),reply(finish='length'),
                   {'choices':[{'finish_reason':'stop','message':{'content':'not json'}}]}]
        with patch.dict(os.environ,{'GROQ_API_KEY':'fake-test-key','GROQ_FREE_TIER_CONFIRMED':'true'}):
            for response in responses:
                with temporary_directory() as temp:
                    result=AddressReviewer('groq',Path(temp)/'cache.sqlite',transport=lambda *args:response).review(order())
                    self.assertEqual(result['source'],'unavailable')

    def test_timeout_no_raw_error_leak(self):
        def fail(*args):
            raise TimeoutError('fake-test-key should never appear')
        with temporary_directory() as temp, patch.dict(os.environ,{'GROQ_API_KEY':'fake-test-key','GROQ_FREE_TIER_CONFIRMED':'true'}):
            result=AddressReviewer('groq',Path(temp)/'cache.sqlite',transport=fail).review(order())
            self.assertEqual(result['source'],'unavailable')
            self.assertNotIn('fake-test-key',json.dumps(result))

    def test_response_schema_rejects_extra_actions(self):
        data=json.loads(reply()['choices'][0]['message']['content'])
        with self.assertRaises(ValueError):
            validate_review(dict(data,action='cancel'))
        with self.assertRaises(ValueError):
            validate_review(dict(data,missing_details=['x']*9))

    def test_provider_modes_and_limits_cannot_select_paid_alternative(self):
        with self.assertRaises(ValueError):
            AddressReviewer('openai')
        with self.assertRaises(ValueError):
            AddressReviewer(daily_request_cap=0)


class TrainingIntegrationTests(unittest.TestCase):
    def test_full_training_freeze_repeatability_and_september_isolation(self):
        with temporary_directory() as temp:
            root=Path(temp)
            first=run_training(output_root=root/'first')
            artifact_path=root/'first/artifacts/decision_engine.json'
            artifact=json.loads(artifact_path.read_text())
            self.assertEqual(canonical_hash({k:v for k,v in artifact.items() if k!='freeze_sha256'}),artifact['freeze_sha256'])
            self.assertEqual(first['split_orders'],dict(development=1297,validation=361,evaluation=329))
            for scope in ('validation','evaluation'):
                self.assertEqual(sum(first['performance'][scope]['buckets'].values()),first['split_orders'][scope])
            before={p.relative_to(root/'first'):p.read_bytes() for p in (root/'first').rglob('*') if p.is_file()}
            run_training(output_root=root/'first')
            self.assertEqual(before,{p.relative_to(root/'first'):p.read_bytes() for p in (root/'first').rglob('*') if p.is_file()})
            with (ROOT/'data/processed/orders_clean.csv').open(encoding='utf-8',newline='') as f:
                rows=list(csv.DictReader(f))
            for row in rows:
                if row['order_datetime'].startswith('2026-09'):
                    row['final_status']='DELIVERED' if row['final_status']=='RTO' else 'RTO'
            changed=root/'mutated.csv'
            write_csv(changed,COLUMNS+EXTRA_COLUMNS,rows)
            run_training(changed,root/'mutated')
            self.assertEqual(artifact_path.read_bytes(),(root/'mutated/artifacts/decision_engine.json').read_bytes())


if __name__=='__main__':
    unittest.main()
