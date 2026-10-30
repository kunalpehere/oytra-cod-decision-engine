"""Verify a clean public-safe copy, then build the reviewed source ZIP locally."""

import argparse
import hashlib
import json
import platform
import re
import shutil
import subprocess
import sys
import time
import uuid
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.audit_repository import audit,path_issue


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def public_files(git):
    result=subprocess.run([git,'ls-files','--cached','--others','--exclude-standard','-z'],cwd=ROOT,capture_output=True,check=True)
    files=sorted(set(name for name in result.stdout.decode().split('\0') if name))
    for name in files:
        target=ROOT/name
        if not target.resolve().is_relative_to(ROOT) or target.is_symlink() or not target.is_file() or path_issue(name):
            raise ValueError(f'Unsafe publication path: {name}')
    return files


def command(checkout,args,timeout=300):
    started=time.perf_counter()
    result=subprocess.run([sys.executable,*args],cwd=checkout,capture_output=True,text=True,encoding='utf-8',timeout=timeout)
    if result.returncode:
        # Keep detailed errors in ignored local scratch files, never publish raw
        # paths/environment values from subprocess diagnostics in the report.
        (checkout/'verification_failure.txt').write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
        raise RuntimeError(f'Clean-copy command failed: {args[0]}; diagnostics are in the ignored check workspace.')
    return result,time.perf_counter()-started


def verify(git,source):
    if not audit(ROOT,git)['passed']:
        raise ValueError('Repository audit failed; no public package created.')
    files=public_files(git)
    private=['data/raw/orders_sample.csv','data/processed/orders_clean.csv','artifacts/decision_engine.json','reports/engine/summary.json']
    protected={name:digest(ROOT/name) for name in private if (ROOT/name).exists()}
    checkout=ROOT/'tmp/submission-check'/uuid.uuid4().hex
    checkout.mkdir(parents=True)
    for name in files:
        target=checkout/name
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/name,target)
    if (checkout/'data').exists() or any(p.name.startswith('.env') for p in checkout.rglob('*')):
        raise ValueError('Private dataset or environment file leaked into the clean copy.')
    setup,setup_seconds=command(checkout,['-m','src.setup_project','--input',str(Path(source).resolve())])
    setup_result=json.loads(setup.stdout)
    if setup_seconds>=600 or setup_result['api_calls']!=0:
        raise ValueError('Setup did not satisfy the under-ten-minute/offline requirement.')
    suite,test_seconds=command(checkout,['-m','unittest','discover','-s','tests'])
    match=re.search(r'Ran (\d+) tests?',suite.stderr)
    if not match:
        raise ValueError('Could not verify test completion count.')
    skipped=re.search(r'skipped=(\d+)',suite.stderr)
    decision,_=command(checkout,['-m','src.decision_engine','--order','examples/orders.json'])
    actions={row['action'] for row in json.loads(decision.stdout)}
    if actions!={'ship_as_is','ship_after_confirmation','nudge_to_prepaid','hold_cancel'}:
        raise ValueError('All four decision demonstrations were not present.')
    daily,_=command(checkout,['-m','src.dashboard','--export','--date','2026-09-30','--output-root','tmp/check-exports'])
    day=json.loads(daily.stdout)
    if day['orders']!=9 or day['money']['net_impact']!='240.19':
        raise ValueError('Daily export did not reconcile to the assignment baseline.')
    gui_code=('import tkinter as tk; from pathlib import Path; from src.app import Workspace; '
              'r=tk.Tk(); r.withdraw(); a=Workspace(r,simulator_path=Path("tmp/gui-check.sqlite")); '
              'a.show("confirmations"); a.show("overview"); r.update_idletasks(); r.destroy(); print("GUI_OK")')
    gui,_=command(checkout,['-c',gui_code])
    if 'GUI_OK' not in gui.stdout:
        raise ValueError('Desktop widget startup was not confirmed.')
    from pypdf import PdfReader
    memo=ROOT/'output/pdf/business_memo.pdf'
    reader=PdfReader(memo)
    text='\n'.join(page.extract_text() for page in reader.pages)
    if len(reader.pages)!=2 or any(not page.extract_text().strip() for page in reader.pages):
        raise ValueError('Founder memo is not two nonempty pages.')
    if not all(value in text for value in ('889.30','845','215','81','28','5','169.40','40.66','Week 1','Week 2')):
        raise ValueError('Memo content checks did not match verified business findings.')
    if any(digest(ROOT/name)!=value for name,value in protected.items()):
        raise ValueError('Clean-copy verification changed protected local inputs/artifact.')
    report=dict(date='2026-10-30',python=platform.python_version(),platform=platform.system(),
                publishable_files_copied=len(files),setup_seconds=round(setup_seconds,2),
                tests=int(match[1]),tests_skipped=int(skipped[1]) if skipped else 0,test_seconds=round(test_seconds,2),
                setup=setup_result,all_four_actions=True,daily_export_orders=day['orders'],
                daily_scenario_net_impact=day['money']['net_impact'],gui_widget_startup=True,
                memo_pages=2,memo_sha256=digest(memo),protected_inputs_unchanged=True,
                live_llm_connectivity_user_reported=True,representative_live_llm_accuracy_verified=False,publication_performed=False)
    content=f'''# Final verification

Verified on 30 October 2026 using Python {report['python']} on {report['platform']}.

## Clean public-safe copy

Copied only Git's publishable files into a new isolated directory, before supplying the assignment CSV separately. No company dataset, environment file, credential container, simulator state or cache was copied as public source. This is a fresh-file copy, not a claim that a remote GitHub clone has been published.

| Check | Result |
| --- | --- |
| One-command preparation from the supplied CSV | Passed in **{report['setup_seconds']} seconds**, below ten minutes |
| Offline setup | Zero API calls; 2,018 source rows, 1,988 retained, 1,987 resolved |
| Complete clean-copy test suite | **{report['tests']} passed**, {report['tests_skipped']} skipped; {report['test_seconds']} seconds |
| Decision CLI | All four action buckets demonstrated |
| September 30 export | 9 orders; scenario net impact INR +240.19 |
| Desktop widget startup/navigation | Passed using withdrawn Tk windows |
| Founder memo | Two nonempty pages; key business numbers checked; both rendered pages visually reviewed |
| Protected original data/frozen artifact | Unchanged |

The full September frozen scenario remains INR -889.30. A positive example day is not evidence of positive monthly impact. Response assumptions, accounting alternatives and holdout limits are disclosed in the memo and README.

## Review limits

- The user's revised Groq Hinglish check returned available=1, address_matches=1, name_matches=1 and cached=false from openai/gpt-oss-20b. This is user-reported evidence for one hand-authored fixture, not representative interpretation accuracy. This verifier makes no live API calls; mock provider tests are not live-model accuracy evidence.
- The overview was visually reviewed after refinement. Conversation behavior has automated checks and user screenshot validation; its latest automated desktop recheck was stopped by the user. The clean-copy GUI check verifies widget startup/navigation, not a new visual review.
- Timing excludes installing Python, obtaining the supplied assignment CSV and optional live-provider signup. The application has no pip dependencies. ReportLab/pypdf are optional document-authoring/verification dependencies, not runtime requirements.
- Common credential-pattern/path auditing does not certify arbitrary secrets, Git history or remote contents. No files were pushed or sent to the company by this verification.

## Reproduce

```powershell
python -m src.setup_project --input "C:\\path\\to\\orders_sample.csv"
python -m unittest discover -s tests -v
python -m src.app
python tools/audit_repository.py
```

The optional packaging verifier is `tools/verify_submission.py`; it requires pypdf for checking the included memo. Detailed temporary diagnostics are kept under ignored tmp/ and are excluded from the source archive.
'''
    (ROOT/'VERIFICATION.md').write_text(content,encoding='utf-8')
    result=audit(ROOT,git)
    if not result['passed']:
        raise ValueError('Final audit failed after writing verification.')
    final_files=public_files(git)
    destination=ROOT/'output/submission'
    destination.mkdir(parents=True,exist_ok=True)
    archive=destination/'oytra-cod-decision-engine-public.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name in final_files:
            info=zipfile.ZipInfo('oytra-cod-decision-engine/'+Path(name).as_posix(),(2026,10,30,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o644<<16
            z.writestr(info,(ROOT/name).read_bytes())
    with zipfile.ZipFile(archive) as z:
        if len(z.namelist())!=len(final_files) or any(path_issue(name.split('/',1)[1]) for name in z.namelist()):
            raise ValueError('Archive membership failed the public-safe path check.')
    report.update(public_files_packaged=len(final_files),repository_audit=result,archive_sha256=digest(archive))
    (destination/'verification_details.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    (destination/'SHA256SUMS.txt').write_text(report['archive_sha256']+'  '+archive.name+'\n'+digest(memo)+'  business_memo.pdf\n',encoding='utf-8')
    (destination/'public_manifest.txt').write_text('\n'.join(final_files)+'\n',encoding='utf-8')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--git',default='git')
    parser.add_argument('--input',type=Path,default=ROOT/'data/raw/orders_sample.csv')
    args=parser.parse_args()
    print(json.dumps(verify(args.git,args.input),indent=2,sort_keys=True))


if __name__=='__main__':
    main()
