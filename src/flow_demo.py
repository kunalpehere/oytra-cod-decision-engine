"""Generate reproducible local conversation transcripts without opening a window."""

import argparse
import json
import tempfile
from pathlib import Path

from src.chat_simulator import load_engine, score_order
from src.confirmation_flow import FlowStore
from src.data_pipeline import ROOT


def generate_demo(output_root=ROOT):
    output_root=Path(output_root)
    artifact=load_engine()
    examples=json.loads((ROOT/'examples/orders.json').read_text(encoding='utf-8'))
    base={order['order_id']:order for order in examples}
    temp_root=output_root/'tmp/flow-demo'
    temp_root.mkdir(parents=True,exist_ok=True)
    context=tempfile.TemporaryDirectory(dir=temp_root)
    if not Path(context.name).resolve().is_relative_to(temp_root.resolve()):
        raise RuntimeError('Demo database escaped its temporary directory.')
    results=[]
    with context as directory:
        def setup(identifier,source,language):
            order=dict(base[source],order_id=identifier)
            store=FlowStore(Path(directory)/(identifier+'.sqlite'),start='2026-10-30T09:00:00+05:30')
            store.start(order,score_order(order,artifact),language)
            return store
        store=setup('FLOW-DETAILS','DEMO-HINGLISH','Hinglish')
        store.reply('FLOW-DETAILS','YES','details-yes')
        store.reply('FLOW-DETAILS','ADDRESS: House 21, Gali 4, Station Road','details-address')
        results.append(store.reply('FLOW-DETAILS','haan','details-confirm'))
        store=setup('FLOW-CANCEL','DEMO-HINGLISH','Hindi')
        results.append(store.reply('FLOW-CANCEL','नहीं','cancel-no'))
        store=setup('FLOW-UNCLEAR','DEMO-HINGLISH','English')
        store.reply('FLOW-UNCLEAR','what is this?','unclear-one')
        results.append(store.reply('FLOW-UNCLEAR','some random text','unclear-two'))
        store=setup('FLOW-TIMEOUT','DEMO-HINGLISH','English')
        store.advance(24,'timeout-clock')
        results.append(store.snapshot('FLOW-TIMEOUT'))
        store=setup('FLOW-PAID','DEMO-PRIOR-RTO','English')
        store.reply('FLOW-PAID','paid','paid-claim')
        results.append(store.mock_payment('FLOW-PAID','success','paid-verified'))
        store=setup('FLOW-PAYMENT-FAILED','DEMO-PRIOR-RTO','Hindi')
        store.mock_payment('FLOW-PAYMENT-FAILED','failed','payment-failed')
        results.append(store.reply('FLOW-PAYMENT-FAILED','हाँ','payment-failed-confirm'))
        store=setup('FLOW-PAYMENT-EXPIRED','DEMO-PRIOR-RTO','Hinglish')
        store.advance(18,'expired-clock')
        results.append(store.reply('FLOW-PAYMENT-EXPIRED','YES','expired-confirm'))
        store=setup('FLOW-COD-CHOICE','DEMO-PRIOR-RTO','English')
        store.reply('FLOW-COD-CHOICE','COD','cod-choice')
        store.reply('FLOW-COD-CHOICE','YES','cod-confirm')
        results.append(store.mock_payment('FLOW-COD-CHOICE','success','late-payment'))
    report_dir=output_root/'reports/flows'
    report_dir.mkdir(parents=True,exist_ok=True)
    (report_dir/'demo_conversations.json').write_text(json.dumps(results,indent=2,sort_keys=True,ensure_ascii=False)+'\n',encoding='utf-8')
    lines=['# Phase 4 - local conversation examples','',
           'All messages, customers, payments, and shipments below are simulated. No WhatsApp access, paid services, API keys or network calls are used. Times are shown in IST. The clock starts at 09:00 on 30 October 2026 for every independent scenario.','',
           '## Rules demonstrated','',
           '- Initial message immediately; one reminder at 12 hours; payment offer expires at 18 hours; review hold at 24 hours. All deadlines remain anchored to the initial message.',
           '- YES releases COD only when required recipient/address details are complete. Corrections need a fresh YES.',
           '- NO explicitly cancels; silence and repeated unclear replies cause review holds, not cancellation.',
           '- PAID is only customer text. A matching local mock payment event is needed to mark prepaid.',
           '- Failed/expired prepaid offers fall back to COD confirmation at the full COD price. Late success after COD/cancellation is held for payment/refund review.',
           '- Payment verification is simulated, not a production payment gateway. Nothing is actually sent or shipped.',
           '- State changes and corrections are audited. Replaying an event ID cannot repeat effects; conflicting reuse is rejected.',
           '- Runtime messages use templates and explicit reply vocabulary. Free-form ambiguity asks for clarification; no LLM interpretation or paid content is used.',
           '- Customer corrections are format checks and explicit customer assertions, not address verification. This phase allows name/address text corrections only; changes to city/state/pincode/phone require operations to revalidate and rescore the order.',
           '- Phase 3 financial scenarios are not replaced by these examples. Measured confirmation/retention rates are still unavailable.','']
    for c in results:
        lines.extend([f"## {c['id']}",'',f"Language: {c['language']}. Final state: **{c['state']}**. Ready to ship (mock): {c['can_ship']}. Payment: {c['payment_status']}.",''])
        for msg in c['messages']:
            who='Customer' if msg['direction']=='customer_mock' else 'Store'
            lines.extend([f"**{who}, {msg['time']}**",'',msg['text'],''])
        lines.extend(['Audit transitions:',''])
        for event in c['audit']:
            if event['kind']=='state_changed':
                lines.append(f"- {event['time']}: {event['payload']['previous']} -> {event['payload']['state']} ({event['payload']['reason']}).")
        lines.append('')
    (report_dir/'demo_transcripts.md').write_text('\n'.join(lines),encoding='utf-8')
    return dict(scenarios=len(results),states={c['id']:c['state'] for c in results},real_messages_sent=0,real_payments=0,api_calls=0)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root',type=Path,default=ROOT)
    args=parser.parse_args()
    print(json.dumps(generate_demo(args.output_root),indent=2))


if __name__=='__main__':
    main()
