#!/usr/bin/env python3
"""Apply the reviewed S24 delta to an isolated copy of the exact open XNU source."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sources


def main():
    root = Path(__file__).resolve().parents[2]
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', required=True)
    args = p.parse_args()
    if not args.run.replace('-', '').replace('_', '').isalnum() or len(args.run) > 80:
        raise ValueError('Use a unique simple run name')
    data = json.loads((root / 'research/sources.json').read_text())['sources']
    provenance = [sources.verify(root, next(s for s in data if s['id'] == i)) for i in ['s24-port', 'apple-xnu']]
    out = root / 'artifacts/xnu-prepare' / args.run
    if out.resolve() != out:
        raise ValueError('Run path cannot use symlinks')
    out.mkdir(parents=True, exist_ok=False)
    report = dict(kind='host-test', origin='local-host', outcome='inconclusive', recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'), provenance=provenance, commands=[], kernel_compiled=False, device_executed=False)
    try:
        work = out / 'xnu'
        shutil.copytree(root / 'references/apple-xnu', work, ignore=shutil.ignore_patterns('.git'))
        # A nested directory without its own Git root can make `git apply` use
        # the parent project and skip paths outside its prefix while exiting 0.
        sources.git(work, 'init', '--quiet')
        donor = root / 'references/s24-port'
        patches = [donor / 'xnu/hackios/redwood.patch', *sorted((donor / 'xnu/e1s/patches').glob('[0-9][0-9][0-9][0-9]-*.patch'))]
        report['patches'] = []
        for i, patch in enumerate(patches):
            for mode in ['--check', '--apply']:
                argv = ['git', '-c', 'core.hooksPath=/dev/null', 'apply', '--whitespace=nowarn'] + (['--check'] if mode == '--check' else []) + [str(patch)]
                x = subprocess.run(argv, cwd=work, capture_output=True, text=True, timeout=60)
                report['commands'].append(dict(argv=argv, exit_code=x.returncode, stdout=x.stdout, stderr=x.stderr))
                if x.returncode:
                    raise RuntimeError(f'Patch {patch.name} failed: {x.stderr}')
            report['patches'].append(dict(name=str(patch.relative_to(donor)), sha256=hashlib.sha256(patch.read_bytes()).hexdigest()))
            if i == 0:
                shutil.copytree(donor / 'xnu/hackios/files', work, dirs_exist_ok=True)
        required = ['config/MASTER.arm64.e1s', 'pexpert/pexpert/arm64/E1S.h', 'bsd/dev/e1s_touch.c', 'bsd/dev/e1s_ufs.c']
        report['required_files'] = {f: hashlib.sha256((work / f).read_bytes()).hexdigest() for f in required}
        report.update(outcome='pass', summary='Exact open XNU plus embedded HakiOS and all E1S patches apply; no kernel compiled')
    except Exception as exc:
        report.update(outcome='fail', error=str(exc))
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'outcome': report['outcome'], 'report': str((out / 'report.json').relative_to(root)), 'error': report.get('error')}, indent=2))
    return 0 if report['outcome'] == 'pass' else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, sources.SourceError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)
