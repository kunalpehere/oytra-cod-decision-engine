"""Compare a text reviewer with hand-authored fixtures; offline by default."""

import argparse
import json
from pathlib import Path

from src.address_review import AddressReviewer
from src.data_pipeline import ROOT


def evaluate_cases(reviewer, cases):
    results=[]
    for case in cases:
        review=reviewer.review(case['order'])
        available=review['source']!='unavailable'
        results.append(dict(case_id=case['id'],review=review,available=available,
                            address_matches=available and review['address_quality']==case['expected_address_quality'],
                            name_matches=available and review['name_quality']==case['expected_name_quality']))
    return dict(cases=len(cases),available=sum(r['available'] for r in results),
                address_matches=sum(r['address_matches'] for r in results),
                name_matches=sum(r['name_matches'] for r in results),results=results,
                limitation='Small hand-authored fixture check only; not representative accuracy or physical delivery verification. Offline heuristic results are not LLM output.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=('offline','groq'),default='offline')
    parser.add_argument('--case-id',help='Live mode checks exactly one case to limit requests.')
    args=parser.parse_args()
    cases=json.loads((ROOT/'examples/address_cases.json').read_text(encoding='utf-8'))
    if args.case_id:
        cases=[c for c in cases if c['id']==args.case_id]
        if not cases:
            parser.error('Unknown case ID.')
    elif args.mode=='groq':
        parser.error('Live mode requires --case-id; do not batch-call a free API.')
    result=evaluate_cases(AddressReviewer(args.mode),cases)
    print(json.dumps(result,indent=2,ensure_ascii=True))
    if result['available']!=result['cases']:
        raise SystemExit(2)


if __name__=='__main__':
    main()
