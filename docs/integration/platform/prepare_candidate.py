#!/usr/bin/env python3
"""Replay a verified scoped source series only in this isolated worktree."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
WT = HERE.parents[2]
MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
ENV = {**os.environ, 'GIT_NO_LAZY_FETCH': '1', 'GIT_OPTIONAL_LOCKS': '0', 'PYTHONDONTWRITEBYTECODE': '1'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    audit_path = Path(sys.argv[1]).resolve()
    name = sys.argv[2]
    assert WT.is_relative_to(MAIN / 'worktrees') and re.fullmatch(r'[A-Za-z0-9_-]+', name)
    audit = json.loads(audit_path.read_text())
    assert audit['outcome'] == 'pass' and audit_path.is_relative_to(WT)
    out = WT / 'artifacts/platform-integration' / name
    out.mkdir(parents=True, exist_ok=False)
    report = dict(kind='host-test', origin='local-host', outcome='fail', task='INT-003', experiment='PLATINT-001',
                  recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                  audit={'path': str(audit_path), 'sha256': sha(audit_path.read_bytes())},
                  commands=[], admission=[], commit_map=[], main_published=False, common_check_executed=False)

    def run(*args, expected=0):
        argv = ['git', '-c', 'core.hooksPath=/dev/null', '-C', str(WT), *map(str, args)]
        result = subprocess.run(argv, env=ENV, capture_output=True, timeout=45)
        i = len(report['commands'])
        for field, data in [('stdout', result.stdout), ('stderr', result.stderr)]:
            (out / (str(i) + '.' + field)).write_bytes(data)
        report['commands'].append(dict(argv=argv, exit_code=result.returncode,
                                        stdout_sha256=sha(result.stdout), stderr_sha256=sha(result.stderr)))
        if expected is not None and result.returncode != expected:
            raise ValueError('Candidate operation failed; preserve state: ' + repr(argv))
        return result.stdout, result.returncode

    try:
        for i in range(3):
            available = int(re.search(r'^MemAvailable:\s+(\d+)', Path('/proc/meminfo').read_text(), re.M)[1])
            report['admission'].append(dict(at=datetime.now(timezone.utc).isoformat(), MemAvailable_KiB=available))
            if available < 4194304:
                raise ValueError('Resource-deferred below4GiB; no candidate child spawned')
            if i < 2:
                time.sleep(1)
        assert not run('status', '--porcelain=v1', '--untracked-files=no')[0], 'Candidate tracked state is dirty'
        report['base_head'] = run('rev-parse', 'HEAD')[0].decode().strip()
        for source in audit['source_commits']:
            assert re.fullmatch('[0-9a-f]{40}', source)
            run('cherry-pick', '--no-gpg-sign', source)
            candidate = run('rev-parse', 'HEAD')[0].decode().strip()
            patches = [run('show', '--format=', '--binary', '--full-index', '--no-ext-diff', '--no-renames', value)[0]
                       for value in [source, candidate]]
            assert patches[0] == patches[1], 'Candidate patch differs from exact source'
            report['commit_map'].append(dict(source=source, candidate=candidate, patch_sha256=sha(patches[0])))
        for name, facts in audit['frozen_files'].items():
            assert sha((WT / name).read_bytes()) == facts['sha256'], 'Candidate final bytes differ: ' + name
        report['candidate_head'] = run('rev-parse', 'HEAD')[0].decode().strip()
        report['paths'] = run('diff', '--name-only', '--no-renames', report['base_head'], report['candidate_head'])[0].decode().splitlines()
        _, code = run('diff', '--check', report['base_head'], report['candidate_head'], expected=None)
        report['diff_check_exit'] = code
        report['outcome'] = 'pass'
        report['summary'] = 'Exact source patches and final frozen bytes replayed in isolated candidate; MAIN publication/common check remain unauthorized'
    except Exception as error:
        report['error'] = repr(error)
        report['summary'] = 'Isolated candidate preparation failed/deferred; no MAIN mutation or automatic rollback'
    finally:
        report['process_memory'] = [x for x in Path('/proc/self/status').read_text().splitlines() if x.startswith(('VmHWM:', 'VmRSS:'))]
        report['artifact_hashes'] = {str(p.relative_to(MAIN)): sha(p.read_bytes()) for p in out.iterdir() if p.is_file()}
        report['artifacts'] = list(report['artifact_hashes'])
        (out / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report.get(k) for k in ['outcome', 'summary', 'error', 'candidate_head', 'diff_check_exit']}, indent=2))
    return report['outcome'] != 'pass'


if __name__ == '__main__':
    raise SystemExit(main())
