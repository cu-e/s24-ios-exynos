#!/usr/bin/env python3
"""Record the actual bounded audit exit and a MAIN-relative ledger envelope."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
WT = HERE.parents[2]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--main', type=Path, default=Path('/home/egor/dev/pet/s24-ios-exynos'))
    p.add_argument('--run', required=True)
    p.add_argument('--experiment', default='CRYSRC-002')
    a = p.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]+', a.run):
        p.error('Invalid run name')
    main_root = a.main.resolve()
    WT.relative_to(main_root)
    out = WT / 'artifacts/crypto-source-integrity' / a.run
    if out.exists():
        p.error('Existing run must remain immutable')
    argv = [sys.executable, str(HERE / 'audit.py'), '--main', str(main_root),
            '--run', a.run, '--experiment', a.experiment]
    env = {**os.environ, 'GIT_NO_LAZY_FETCH': '1', 'GIT_OPTIONAL_LOCKS': '0', 'PYTHONDONTWRITEBYTECODE': '1'}
    started = datetime.now(timezone.utc).isoformat(timespec='seconds')
    r = subprocess.run(argv, env=env, capture_output=True, timeout=180)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'audit.stdout').write_bytes(r.stdout)
    (out / 'audit.stderr').write_bytes(r.stderr)
    capsule = out / 'evidence.json'
    rich = json.loads(capsule.read_bytes()) if capsule.is_file() else {}
    hashes = {str(f.relative_to(main_root)): hashlib.sha256(f.read_bytes()).hexdigest()
              for f in sorted(out.iterdir()) if f.is_file()}
    passed = r.returncode == 0 and rich.get('outcome') == 'pass'
    evidence = {'kind': 'source-review', 'origin': 'local-host', 'outcome': 'pass' if passed else 'fail',
                'task': 'KRN-038', 'experiment': a.experiment,
                'recorded_at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'started_at': started,
                'summary': 'Complete67-source correction,3 historical truncations,44 API bodies and14 negative controls' if passed else 'Source audit failed; inspect retained capsule',
                'commit': rich.get('tested_commit'), 'commands': [{'argv': argv, 'exit_code': r.returncode}],
                'artifacts': list(hashes), 'artifact_hashes': hashes,
                'recorder_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'audit_tool': rich.get('tool'), 'process_memory': rich.get('process_memory'),
                'limits': ['Source-only; no compiler, algorithm execution, QEMU, device or native/private-ABI qualification.']}
    (out / 'ledger-evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    sys.stdout.buffer.write(r.stdout)
    sys.stderr.buffer.write(r.stderr)
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
