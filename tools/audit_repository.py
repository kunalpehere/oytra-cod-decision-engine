"""Inspect Git's publishable file set without displaying credential values.

Uses staged/tracked plus untracked non-ignored files. This is a guard for common
credential formats and prohibited file paths, not a guarantee against all secrets.
"""

import argparse
import json
import re
import subprocess
from pathlib import Path

PROHIBITED_DIRS={'data','.aws','.ssh','.codex','.agents','tmp','submission-staging'}
PRIVATE_REPORTS={'reports/data_quality_issues.csv','reports/data_transformation_log.csv',
                 'reports/engine/validation_decisions.csv','reports/engine/evaluation_decisions.csv'}
PATTERNS={
    'private key':re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
    'Groq API key':re.compile(r'\bgsk_[A-Za-z0-9]{40,}\b'),
    'OpenAI-style API key':re.compile(r'\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{32,}\b'),
    'GitHub token':re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b'),
    'AWS access key':re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    'Google API key':re.compile(r'\bAIza[A-Za-z0-9_-]{30,}\b'),
}


def path_issue(name):
    path=Path(name)
    parts=path.as_posix().lower().split('/')
    basename=parts[-1]
    normalized='/'.join(parts)
    if any(part in PROHIBITED_DIRS for part in parts[:-1]):
        return 'private data or local state path'
    if (basename.startswith('.env') or basename.endswith(('.env','.pem','.key','.p12','.pfx','.keystore'))
            or ('credentials' in basename and basename.endswith('.json'))
            or ('secrets' in basename and basename.endswith('.json'))):
        return 'credential file path'
    if normalized in PRIVATE_REPORTS or normalized.startswith('reports/dashboard/exports/'):
        return 'private per-order report'
    return None


def content_issues(content):
    return [kind for kind,pattern in PATTERNS.items() if pattern.search(content)]


def audit(root,git='git'):
    root=Path(root).resolve()
    result=subprocess.run([git,'ls-files','--cached','--others','--exclude-standard','-z'],cwd=root,
                          capture_output=True,check=True)
    files=sorted(set(name for name in result.stdout.decode('utf-8').split('\0') if name))
    issues=[]
    for name in files:
        reason=path_issue(name)
        if reason:
            issues.append(dict(file=name,issue=reason))
        path=root/name
        if not path.is_file():
            continue
        # No printing matched text or credential values, even on failures.
        text=path.read_bytes().decode('utf-8',errors='ignore')
        issues.extend(dict(file=name,issue=kind) for kind in content_issues(text))
    return dict(files_checked=len(files),issues=issues,passed=not issues,
                scope='Current tracked/staged and non-ignored working-tree files; Git history and remote contents are not scanned.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--git',default='git')
    args=parser.parse_args()
    result=audit(args.root,args.git)
    print(json.dumps(result,indent=2))
    if not result['passed']:
        raise SystemExit(1)


if __name__=='__main__':
    main()
