#!/usr/bin/env python3
"""Light read-only acceptance binding audit; never runs algorithms or guests."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import time

HERE = Path(__file__).resolve().parent
WT = HERE.parents[2]
MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
IMPL = MAIN / 'worktrees/krn-036-20261105'
REVIEW = MAIN / 'worktrees/rev-cts3-20261105'
REVIEW_SHA = '8b961ac546f9819ae231cdfd5df40fe6d6f7cb73'
SERIES = ['09111a9', '89ff8f2', '8a4233a', '55ea7b7', '80ee7fd', 'b9fa5ca']
ENV = {**os.environ, 'GIT_NO_LAZY_FETCH': '1', 'GIT_OPTIONAL_LOCKS': '0', 'PYTHONDONTWRITEBYTECODE': '1'}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        while data := f.read(1024 * 1024):
            h.update(data)
    return h.hexdigest()


def must(value, why):
    if not value:
        raise ValueError(why)


def main():
    name = sys.argv[1]
    must(re.fullmatch(r'[A-Za-z0-9_-]+', name), 'Invalid fresh run name')
    out = WT / 'artifacts/platform-integration' / name
    out.mkdir(parents=True, exist_ok=False)
    report = dict(kind='host-test', origin='local-host', outcome='fail', task='INT-003', experiment='PLATINT-001',
                  owner='codex-integrator-platform-20261106-cn', recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                  commands=[], admission=[], bindings={}, frozen_files={}, dependency_status={},
                  main_published=False, common_check_executed=False, algorithms_replayed=False, guest_executed=False)

    def run(argv):
        argv = list(map(str, argv))
        p = subprocess.run(argv, env=ENV, capture_output=True, timeout=30)
        report['commands'].append(dict(argv=argv, exit_code=p.returncode, stdout_sha256=hashlib.sha256(p.stdout).hexdigest(),
                                        stderr_sha256=hashlib.sha256(p.stderr).hexdigest()))
        must(p.returncode == 0, 'Read-only Git command failed: ' + repr(argv))
        return p.stdout

    def bind(path, expected):
        path = Path(path)
        must(re.fullmatch('[0-9a-f]{64}', expected), 'Not a SHA256: ' + str(path))
        if str(path) in report['bindings']:
            must(report['bindings'][str(path)] == expected, 'Conflicting identities: ' + str(path))
            return
        must(path.is_file() and sha(path) == expected, 'Missing or changed bound input: ' + str(path))
        report['bindings'][str(path)] = expected

    def mapping(data, base):
        for name, expected in data.items():
            must(isinstance(expected, str), 'Non-hash mapping member')
            bind(Path(name) if Path(name).is_absolute() else base / name, expected)

    def capsule(path, expected=None):
        if expected:
            bind(path, expected)
        else:
            bind(path, sha(path))
        return json.loads(path.read_text())

    try:
        # Prospective admission precedes every audit child; no heavy operation.
        for i in range(3):
            available = int(re.search(r'^MemAvailable:\s+(\d+)', Path('/proc/meminfo').read_text(), re.M)[1])
            report['admission'].append(dict(recorded_at=datetime.now(timezone.utc).isoformat(), MemAvailable_KiB=available))
            must(available >= 4194304, 'Resource-deferred below4GiB; no audit child spawned')
            if i < 2:
                time.sleep(1)
        report['commit'] = run(['git', '-C', WT, 'rev-parse', 'HEAD']).decode().strip()
        report['auditor_sha256'] = sha(__file__)
        commits = [run(['git', '-C', MAIN, 'rev-parse', x]).decode().strip() for x in SERIES]
        report['source_commits'] = commits + [REVIEW_SHA]
        actual = run(['git', '-C', MAIN, 'rev-list', '--reverse', commits[0] + '^..' + commits[-1]]).decode().splitlines()
        must(actual == commits, 'Component series contains unexpected commits')
        for commit in commits + [REVIEW_SHA]:
            paths = run(['git', '-C', MAIN, 'diff-tree', '--no-commit-id', '--name-only', '-r', commit]).decode().splitlines()
            allowed = ('docs/reviews/krn-036/',) if commit == REVIEW_SHA else ('src/platform/crypto/cts3/', 'docs/procedures/crypto-cts3/')
            must(paths and all(any(p.startswith(a) for a in allowed) for p in paths), 'Unscoped commit path: ' + commit)
        ledger = json.loads((MAIN / 'state/lab.json').read_text())
        for identity in ['KRN-029', 'KRN-032', 'KRN-038']:
            task = next(t for t in ledger['tasks'] if t['id'] == identity)
            must(task['status'] == 'done', 'Dependency is not done: ' + identity)
            report['dependency_status'][identity] = dict(status=task['status'], owner=task['owner'], evidence=task.get('evidence'))
        owner = capsule(IMPL / 'artifacts/crypto-cts3/cpu-final1/evidence.json', 'a95b5c69a14519bc2cfc2da8dea025a684bda3a82647b27e66d93d90109afc57')
        review = capsule(REVIEW / 'docs/reviews/krn-036/evidence.json', '19069702c8083d8428dfda91bd337708449ceec86f7a0907d4792a84236fae3c')
        qualified = capsule(IMPL / 'docs/procedures/crypto-cts3/qualified-evidence.json', review['actual_final_qualified_owner_capsule']['sha256'])
        must(owner['outcome'] == qualified['outcome'] == review['outcome'] == 'pass', 'Missing positive actual capsule')
        must(review['recommendation'] == 'accept-bounded-component' and review['blocking_findings'] == [], 'Independent review does not accept bounded component')
        must(owner['host_checks'] == owner['arm_checks'] == 28794 and owner['host_vectors'] == 381 and owner['cbc_fixture_vectors'] == 18, 'Actual count mismatch')
        must(review['focused_checks'] == 7722 and review['focused_compile_jobs'] == 1, 'Independent focused evidence mismatch')
        mapping(owner['artifact_hashes'], MAIN)
        mapping(owner['dependency_hashes'], MAIN)
        mapping(owner['owned_source_hashes'], IMPL)
        for group in owner['accepted_dependencies'].values():
            mapping(group, MAIN)
        for key in ['shared_runtime', 'resource_supervisor', 'primary_source_pins']:
            bind(owner[key]['path'], owner[key]['sha256'])
        mapping(review['sha256'], MAIN)
        final_binding = capsule(REVIEW / 'docs/reviews/krn-036/final-binding.json')
        must(final_binding['outcome'] == 'pass' and len(final_binding['checks']) == 146, 'Independent final binding incomplete')
        mapping(final_binding['inputs'], MAIN)
        focused = capsule(MAIN / review['focused_report']['path'], review['focused_report']['sha256'])
        must(focused['outcome'] == 'pass' and focused['focused_checks'] == 7722 and focused['reviewer_guest_runs'] == 0, 'Independent focused result/guest boundary')
        mapping(focused['inputs'], MAIN)
        # Verify the final committed source and all50 review files against the
        # actual owner worktrees, without trusting only their raw JSON hashes.
        for commit, root, prefixes in [(commits[-1], IMPL, ['src/platform/crypto/cts3', 'docs/procedures/crypto-cts3']),
                                       (REVIEW_SHA, REVIEW, ['docs/reviews/krn-036'])]:
            names = run(['git', '-C', MAIN, 'ls-tree', '-r', '--name-only', commit, *prefixes]).decode().splitlines()
            for name in names:
                data = run(['git', '-C', MAIN, 'show', commit + ':' + name])
                expected = hashlib.sha256(data).hexdigest()
                bind(root / name, expected)
                report['frozen_files'][name] = dict(source_commit=commit, sha256=expected)
        for stage in qualified['stage_capsules']:
            actual = capsule(MAIN / stage['path'], stage['sha256'])
            must(actual['outcome'] == stage['outcome'] and actual.get('commit') == stage['commit'], 'Historical stage was relabelled')
        unchanged = owner['audit_continuation']['unchanged_compiled_and_oracle_sources']
        for name, expected in unchanged.items():
            for commit in [owner['audit_continuation']['compiled_source_commit'], owner['audit_continuation']['qualification_commit']]:
                data = run(['git', '-C', MAIN, 'show', commit + ':' + name])
                must(hashlib.sha256(data).hexdigest() == expected, 'Compiled body changed during qualification continuation')
        for read in owner['source_reads']:
            must(read['argv'][0] == 'git' and 'show' in read['argv'] and read['exit_code'] == 0, 'Unexpected source read command')
            data = run(read['argv'])
            must(hashlib.sha256(data).hexdigest() == read['stdout_sha256'], 'Pinned primary source read differs')
        aes = owner['canonical_AES_inputs']
        bind(aes['archive'], aes['sha256'])
        with tarfile.open(aes['archive']) as tar:
            for name, facts in aes['files'].items():
                data = tar.extractfile('mbedtls-' + aes['commit'] + '/' + name).read()
                must(hashlib.sha256(data).hexdigest() == facts['canonical_sha256'], 'Canonical AES member differs')
                bind(MAIN / 'src/platform/crypto/xts/vendor' / name, facts['actual_sha256'])
        must(not owner['native_device'] and not owner['xnu_executed'] and not owner['provider_registered'] and not owner['test_CBC16_is_production'], 'Unqualified promotion in original capsule')
        must(owner['fortified_memory_boundary']['actual_macho_import'] == '___memcpy_chk' and
             owner['fortified_memory_boundary']['native_kernel_provider_qualified'] is False, 'Native fortified-memory gate lost')
        must(all(x['accepted'] for x in owner['guest_cases']) and len(owner['guest_cases']) == 4, 'Missing real guest control')
        for command in owner['commands']:
            must(not command['after']['owned_processes'] and command['after']['owned_tree_rss_bytes'] == 0, 'Guest child not cleaned up')
        source = (IMPL / 'src/platform/crypto/cts3/production.json').read_text()
        must('__memcpy_chk' in source, 'Production memory boundary missing')
        report['reviewed_results'] = dict(host_checks=28794, ARM_checks=28794, CS3_records=381, CBC16_records=18,
                                         independent_checks=7722, actual_guest_controls=4,
                                         production_native_memcpy_chk_closed=False, CBC16_fixture_is_production=False,
                                         NFS_ignored_return_integration_qualified=False)
        report['outcome'] = 'pass'
        report['summary'] = 'Exact036+021 scope, source/dependency/artifact/continuation bindings verified; bounded component eligible for isolated replay, not MAIN publication'
    except Exception as error:
        report['error'] = repr(error)
        report['summary'] = 'Platform candidate binding audit failed or resource-deferred; no MAIN mutation or common check'
    finally:
        report['finished_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
        report['process_memory'] = [x for x in Path('/proc/self/status').read_text().splitlines() if x.startswith(('VmHWM:', 'VmRSS:'))]
        (out / 'binding-index.json').write_text(json.dumps(report['bindings'], indent=2) + '\n')
        report['artifacts'] = [str((out / 'binding-index.json').relative_to(MAIN))]
        report['artifact_hashes'] = {report['artifacts'][0]: sha(out / 'binding-index.json')}
        (out / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report.get(k) for k in ['outcome', 'summary', 'error', 'process_memory']}, indent=2))
    return report['outcome'] != 'pass'


if __name__ == '__main__':
    raise SystemExit(main())
