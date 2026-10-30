"""Prepare the free local assignment demo from an evaluator-supplied CSV."""

import argparse
import hashlib
import json
import shutil
import time
from pathlib import Path

from src.analysis import run_analysis
from src.data_pipeline import ROOT,read_source,run_pipeline
from src.flow_demo import generate_demo
from src.train_engine import run_training


def prepare(source,output_root=ROOT):
    source,output_root=Path(source).resolve(),Path(output_root).resolve()
    read_source(source)  # Fail before copying malformed input or generating reports.
    target=output_root/'data/raw/orders_sample.csv'
    source_bytes=source.read_bytes()
    if target.exists() and target.read_bytes()!=source_bytes:
        raise ValueError('A different raw dataset already exists here. Use a separate checkout to preserve it.')
    target.parent.mkdir(parents=True,exist_ok=True)
    if source!=target.resolve() and not target.exists():
        shutil.copyfile(source,target)
    started=time.perf_counter()
    cleaning=run_pipeline(target,output_root)
    analysis=run_analysis(output_root/'data/processed/orders_clean.csv',ROOT/'config/financial_assumptions.json',output_root)
    engine=run_training(output_root/'data/processed/orders_clean.csv',output_root)
    # Demo scoring uses this checkout's frozen artifact; alternate output roots
    # would otherwise mix artifacts. Keep setup scoped to the current checkout.
    demo=generate_demo(output_root) if output_root==ROOT.resolve() else None
    return dict(input_sha256=hashlib.sha256(source_bytes).hexdigest(),input_rows=cleaning['input_rows'],
                retained_orders=cleaning['unique_orders_retained'],resolved_orders=analysis['outcome_analysis_orders'],
                frozen_artifact_sha256=engine['freeze_sha256'],offline_demo_scenarios=demo['scenarios'] if demo else 0,
                seconds=round(time.perf_counter()-started,2),api_calls=0,
                next_command='python -m src.app')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,default=ROOT/'data/raw/orders_sample.csv',help='Path to the assignment CSV supplied separately by the evaluator.')
    args=parser.parse_args()
    try:
        result=prepare(args.input)
    except (ValueError,OSError,KeyError) as error:
        parser.exit(1,f'Setup failed: {error}\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
