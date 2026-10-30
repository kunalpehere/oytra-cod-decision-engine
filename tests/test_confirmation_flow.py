import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from src.confirmation_flow import FlowStore, load_flow_config, timestamp, validate_config
from src.flow_demo import generate_demo
from src.flow_messages import TEMPLATES, intent
from test_data_pipeline import order, temporary_directory


def recommendation(row,action='ship_after_confirmation',address='complete',name='unremarkable'):
    return dict(order_id=row['order_id'],action=action,reason='Synthetic test recommendation.',
                address_review=dict(address_quality=address,name_quality=name),
                prepaid_discount_inr='25.00' if action=='nudge_to_prepaid' else '0.00')


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.temp=temporary_directory()
        self.directory=Path(self.temp.__enter__())
        self.path=self.directory/'flow.sqlite'
        self.store=FlowStore(self.path,start='2026-10-30T09:00:00+05:30')
        self.order=order()

    def tearDown(self):
        self.temp.__exit__(None,None,None)

    def start(self,action='ship_after_confirmation',address='complete',name='unremarkable',language='English'):
        return self.store.start(self.order,recommendation(self.order,action,address,name),language)

    def test_yes_confirms_complete_cod_and_persists(self):
        self.start()
        result=self.store.reply('A1','YES','yes-1')
        self.assertEqual(result['state'],'ready_to_ship_cod')
        self.assertTrue(result['can_ship'])
        reopened=FlowStore(self.path,start='2020-01-01T00:00:00+00:00').snapshot('A1')
        self.assertEqual(reopened,result)

    def test_missing_details_cannot_be_bypassed_with_yes(self):
        self.start(address='needs_clarification',name='placeholder')
        result=self.store.reply('A1','yes','yes-1')
        self.assertFalse(result['can_ship'])
        self.assertEqual(result['state'],'awaiting_details')
        self.store.reply('A1','ADDRESS: House 12, Main Road, Sector 4','address-1')
        result=self.store.reply('A1','yes','yes-2')
        self.assertEqual(result['state'],'awaiting_details')
        self.store.reply('A1','NAME: Ananya','name-1')
        result=self.store.reply('A1','yes','yes-3')
        self.assertTrue(result['can_ship'])
        corrections=[r for r in result['audit'] if r['kind']=='customer_corrected_details']
        self.assertEqual(len(corrections),2)

    def test_invalid_details_do_not_clear_requirements(self):
        self.start(address='unknown',name='unknown')
        self.store.reply('A1','ADDRESS: near temple','address-1')
        self.store.reply('A1','NAME: test','name-1')
        result=self.store.reply('A1','yes','yes-1')
        self.assertTrue(result['needs_address'])
        self.assertTrue(result['needs_name'])
        self.assertFalse(result['can_ship'])

    def test_explicit_no_cancels_but_paid_claim_does_not_verify(self):
        self.start('nudge_to_prepaid')
        result=self.store.reply('A1','paid','claim-1')
        self.assertEqual(result['payment_status'],'pending')
        self.assertFalse(result['can_ship'])
        result=self.store.reply('A1','NO','no-1')
        self.assertEqual(result['state'],'cancelled')

    def test_unclear_replies_clarify_then_hold_without_cancelling(self):
        self.start()
        first=self.store.reply('A1','huh?','unclear-1')
        self.assertEqual(first['state'],'awaiting_confirmation')
        final=self.store.reply('A1','yes no maybe','unclear-2')
        self.assertEqual(final['state'],'held_for_review')
        self.assertEqual(final['messages'][-1]['template'],'unclear_hold')

    def test_exact_24_hour_boundary_holds_before_processing_reply(self):
        self.start()
        self.store.advance(24,'advance-1')
        result=self.store.reply('A1','YES','yes-late')
        self.assertEqual(result['state'],'held_for_review')
        self.assertEqual(result['messages'][-1]['template'],'late_reply')

    def test_fractional_second_clock_change_is_rejected_without_mutation(self):
        initial=self.start()
        with self.assertRaises(ValueError):
            self.store.advance(23.999,'advance-1')
        self.assertEqual(self.store.snapshot('A1')['now'],initial['now'])

    def test_just_before_deadline(self):
        initial=self.start()
        self.store.advance('23.99','advance-1')
        result=self.store.reply('A1','YES','yes-1')
        self.assertTrue(result['can_ship'])
        self.assertEqual(result['deadline'],initial['deadline'])

    def test_reminder_once_and_timer_order_on_large_jump(self):
        initial=self.start('nudge_to_prepaid')
        self.store.advance(30,'advance-1')
        result=self.store.snapshot('A1')
        outgoing=[r for r in result['messages'] if r['direction']=='outgoing_mock']
        self.assertEqual([r['template'] for r in outgoing],['prepaid','reminder','cod_fallback','timeout'])
        self.assertEqual([r['at']-initial['created_at'] for r in outgoing],[0,12*3600,18*3600,24*3600])
        self.store.advance(24,'advance-2')
        self.assertEqual(self.store.snapshot('A1')['messages'],result['messages'])

    def test_success_payment_releases_prepaid_and_not_cod(self):
        initial=self.start('nudge_to_prepaid')
        result=self.store.mock_payment('A1','success','payment-1')
        self.assertEqual(result['state'],'ready_to_ship_prepaid')
        self.assertEqual(result['payment_status'],'verified')
        self.assertEqual(initial['payable'],'624.00')
        self.assertEqual(result['messages'][-1]['template'],'ready_prepaid')

    def test_payment_cannot_bypass_address_or_name_correction(self):
        self.start('nudge_to_prepaid',address='unknown')
        result=self.store.mock_payment('A1','success','payment-1')
        self.assertEqual(result['state'],'awaiting_details')
        self.store.reply('A1','ADDRESS: House 12, Main Road, Sector 4','correction-1')
        self.assertFalse(self.store.snapshot('A1')['can_ship'])
        result=self.store.reply('A1','YES','yes-1')
        self.assertEqual(result['state'],'ready_to_ship_prepaid')

    def test_paid_order_cannot_switch_to_cod_and_collect_twice(self):
        self.start('nudge_to_prepaid',address='unknown')
        self.store.mock_payment('A1','success','payment-1')
        result=self.store.reply('A1','COD','cod-1')
        self.assertEqual(result['mode'],'prepaid')
        self.assertEqual(result['messages'][-1]['template'],'already_prepaid')

    def test_failure_and_expiry_fall_back_to_full_price_cod(self):
        self.start('nudge_to_prepaid')
        result=self.store.mock_payment('A1','failed','payment-1')
        self.assertEqual(result['mode'],'COD')
        self.assertIn('649',result['messages'][-1]['text'])
        result=self.store.reply('A1','YES','yes-1')
        self.assertEqual(result['state'],'ready_to_ship_cod')

    def test_declining_prepaid_requires_fresh_cod_confirmation(self):
        self.start('nudge_to_prepaid')
        result=self.store.reply('A1','COD','cod-1')
        self.assertEqual(result['state'],'awaiting_confirmation')
        self.assertFalse(result['can_ship'])
        self.assertEqual(self.store.reply('A1','yes','yes-1')['state'],'ready_to_ship_cod')

    def test_yes_does_not_count_as_prepaid_payment(self):
        self.start('nudge_to_prepaid')
        result=self.store.reply('A1','yes','yes-1')
        self.assertFalse(result['can_ship'])
        self.assertEqual(result['state'],'awaiting_payment')

    def test_wrong_payment_amount_and_id_are_not_verified(self):
        initial=self.start('nudge_to_prepaid')
        result=self.store.mock_payment('A1','success','bad-id',payment_id='OTHER')
        self.assertEqual(result['payment_status'],'pending')
        result=self.store.mock_payment('A1','success','bad-amount',amount='1.00')
        self.assertFalse(result['can_ship'])
        self.assertTrue(result['payment_review_required'])
        self.assertEqual(result['state'],'held_for_review')

    def test_payment_at_expiry_or_after_cod_is_held_for_review(self):
        self.start('nudge_to_prepaid')
        self.store.advance(18,'advance-1')
        self.assertEqual(self.store.snapshot('A1')['state'],'awaiting_confirmation')
        result=self.store.mock_payment('A1','success','late-payment')
        self.assertEqual(result['state'],'held_for_review')
        self.assertTrue(result['refund_review_required'])

    def test_payment_after_cancellation_does_not_reopen_order(self):
        self.start('nudge_to_prepaid')
        self.store.reply('A1','NO','no-1')
        result=self.store.mock_payment('A1','success','late-payment')
        self.assertEqual(result['state'],'cancelled')
        self.assertTrue(result['refund_review_required'])
        self.assertFalse(result['can_ship'])

    def test_explicit_cancellation_after_payment_requests_refund_review(self):
        self.start('nudge_to_prepaid')
        self.store.mock_payment('A1','success','payment-1')
        result=self.store.reply('A1','no','no-1')
        self.assertEqual(result['state'],'cancelled')
        self.assertTrue(result['refund_review_required'])

    def test_duplicate_ids_are_idempotent_and_conflicting_reuse_rejected(self):
        self.start()
        first=self.store.reply('A1','yes','same-event')
        self.assertEqual(self.store.reply('A1','yes','same-event'),first)
        with self.assertRaises(ValueError):
            self.store.reply('A1','no','same-event')
        self.assertEqual(self.store.snapshot('A1'),first)

    def test_duplicate_clock_event_does_not_advance_twice(self):
        self.start()
        first=self.store.advance(12,'clock')
        self.assertEqual(self.store.advance(12,'clock'),first)

    def test_concurrent_duplicate_payment_events_release_once(self):
        self.start('nudge_to_prepaid')
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.store.mock_payment('A1','success','same-payment'),range(2)))
        result=self.store.snapshot('A1')
        self.assertTrue(all(r['can_ship'] for r in results))
        self.assertEqual(sum(m['template']=='ready_prepaid' for m in result['messages']),1)

    def test_new_ids_cannot_duplicate_or_reverse_successful_payment(self):
        self.start('nudge_to_prepaid')
        self.store.mock_payment('A1','success','payment-1')
        self.store.mock_payment('A1','success','payment-2')
        final=self.store.mock_payment('A1','failed','payment-3')
        self.assertEqual(final['state'],'ready_to_ship_prepaid')
        self.assertEqual(sum(m['template']=='ready_prepaid' for m in final['messages']),1)

    def test_start_is_idempotent_and_cannot_reset_deadline(self):
        initial=self.start()
        self.store.advance(12,'clock')
        resumed=self.start()
        self.assertEqual(resumed['created_at'],initial['created_at'])
        with self.assertRaises(ValueError):
            self.start(language='Hindi')

    def test_original_bucket_guards_remain_in_force(self):
        c=self.start('hold_cancel')
        self.assertEqual(c['state'],'held_for_review')
        self.assertEqual(c['messages'],[])
        self.assertFalse(self.store.reply('A1','YES','yes-1')['can_ship'])

    def test_ship_as_is_sends_no_unnecessary_customer_messages(self):
        c=self.start('ship_as_is')
        self.assertTrue(c['can_ship'])
        self.assertEqual(c['messages'],[])

    def test_languages_have_matching_templates_and_explicit_intents(self):
        self.assertEqual(set(TEMPLATES['English']),set(TEMPLATES['Hindi']))
        self.assertEqual(set(TEMPLATES['English']),set(TEMPLATES['Hinglish']))
        for text in ('yes','हाँ','haan'):
            self.assertEqual(intent(text),'yes')
        for text in ('no cancel','yes no','do not cancel','I paid but cancel?'):
            self.assertEqual(intent(text),'unclear')
        c=self.start(language='Hindi')
        self.assertIn('ऑर्डर',c['messages'][0]['text'])

    def test_config_and_clock_validation(self):
        config=load_flow_config()
        for change in ({'timeout_hours':48},{'reminder_hours':24},{'payment_expiry_hours':0},
                       {'default_language':'Other'},{'max_unclear_replies':True}):
            with self.assertRaises(ValueError):
                validate_config(dict(config,**change))
        for advance in (-1,0,True,'NaN',.00001):
            with self.assertRaises(ValueError):
                self.store.advance(advance,'bad-clock')
        with self.assertRaises(ValueError):
            timestamp('2026-10-30T09:00:00')

    def test_settings_are_snapshotted_for_existing_conversation(self):
        initial=self.start()
        self.store.config=dict(self.store.config,reminder_hours=1)
        self.store.advance(1,'clock')
        final=self.store.snapshot('A1')
        self.assertEqual(final['reminder_at'],initial['reminder_at'])
        self.assertFalse(final['reminder_sent'])


class FlowDemoTests(unittest.TestCase):
    def test_demo_transcripts_are_complete_and_reproducible(self):
        with temporary_directory() as temp:
            root=Path(temp)
            result=generate_demo(root)
            self.assertEqual(result['scenarios'],8)
            self.assertEqual(result['states']['FLOW-PAID'],'ready_to_ship_prepaid')
            self.assertEqual(result['states']['FLOW-DETAILS'],'ready_to_ship_cod')
            self.assertEqual(result['states']['FLOW-CANCEL'],'cancelled')
            self.assertEqual(result['states']['FLOW-TIMEOUT'],'held_for_review')
            before={p.name:p.read_bytes() for p in (root/'reports/flows').iterdir()}
            generate_demo(root)
            self.assertEqual(before,{p.name:p.read_bytes() for p in (root/'reports/flows').iterdir()})


if __name__=='__main__':
    unittest.main()
