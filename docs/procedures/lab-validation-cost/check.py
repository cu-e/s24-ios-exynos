#!/usr/bin/env python3
"""Bounded LAB-003 source tests and actual-snapshot measurements; no MAIN writes."""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path('/home/egor/dev/pet/s24-ios-exynos')
BASE = Path(__file__).resolve().parent
WT = BASE.parents[2]
OWNER = 'codex-lab-validation-20261106-dp'
ENV = dict(os.environ, GIT_NO_LAZY_FETCH='1', GIT_OPTIONAL_LOCKS='0', PYTHONDONTWRITEBYTECODE='1')


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True)
    parser.add_argument('--phase', choices=['tests', 'profile'], required=True)
    args = parser.parse_args()
    out = BASE / 'runs' / args.run
    out.mkdir(parents=True, exist_ok=False)
    report = dict(kind='host-test', origin='local-host', outcome='fail', task='LAB-003',
                  recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), commands=[], checks=[])

    def check(name, condition):
        report['checks'].append(dict(name=name, passed=bool(condition)))
        if not condition:
            raise AssertionError(name)

    def prospective():
        state = load(ROOT / 'state/lab.json')
        task = next(t for t in state['tasks'] if t['id'] == 'LAB-003')
        plan = next(e for e in state['experiments'] if e['id'] == 'LABVAL-001')
        check('actual-owned-planned-experiment', task['owner'] == OWNER and task['status'] == 'in_progress'
              and plan['owner'] == OWNER and plan['task'] == 'LAB-003' and plan['status'] == 'planned')
        return plan

    def command(argv, label, seconds=30, negative=False):
        prospective()
        result = supervisor.run(argv, out, label, seconds, 256)
        report['commands'].append(result)
        check('command-' + label, (result['exit_code'] != 0 if negative else result['exit_code'] == 0)
              and result['outcome'] == ('fail' if negative else 'pass')
              and not result['after']['owned_processes'] and result['peak_total_owned_rss_bytes'] <= 256 * 1024 ** 2)
        return result

    try:
        (out / 'prospective-plan.json').write_text(json.dumps(prospective(), indent=2) + '\n')
        helper = ROOT / 'src/platform/crypto/des/check.py'
        check('accepted-bounded-supervisor', sha(helper) == '08454d87ea5197b5eafc9521833136f6ba9dc34b09c1a78f4e2c5c50e8dd2c63')
        spec = importlib.util.spec_from_file_location('bounded_lab_source_checks', helper)
        supervisor = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(supervisor)
        if args.phase == 'tests':
            tests = WT / 'tests'
            command([sys.executable, '-m', 'unittest', 'discover', '-s', tests, '-p', 'test_lab_validation_cache.py', '-v'], 'freshness-tests')
            command([sys.executable, '-m', 'unittest', 'discover', '-s', tests, '-p', 'test_lab.py', '-v'], 'ledger-tests')
            command([sys.executable, '-m', 'unittest', 'discover', '-s', tests, '-p', 'test_planning.py', '-v'], 'planning-tests')
            source = (WT / 'tools/lab.py').read_text()
            check('exact-negative-injection', source.count('    files = _ValidationFiles(root)\n') == 1)
            negative = source.replace('def validate(root, state):', '_negative_views = {}\n\ndef validate(root, state):', 1)
            negative = negative.replace('    files = _ValidationFiles(root)\n', '    files = _negative_views.setdefault(root, _ValidationFiles(root))\n', 1)
            (out / 'negative_lab.py').write_text(negative)
            env = Path(shutil.which('env')).resolve()
            command([env, 'LAB_VALIDATION_TARGET=' + str(out / 'negative_lab.py'), sys.executable, '-m', 'unittest',
                     'discover', '-s', tests, '-p', 'test_lab_validation_cache.py', '-v'], 'persistent-cache-negative', negative=True)
            negative_log = (out / 'persistent-cache-negative.log').read_text()
            check('real-freshness-controls-detect-stale-cache', 'FAIL: test_deleted_artifact_is_rechecked_next_validation' in negative_log
                  and 'FAIL: test_artifact_symlink_retargeted_outside_is_rejected' in negative_log)
        else:
            raw = (ROOT / 'state/lab.json').read_bytes()
            (out / 'registry-snapshot.json').write_bytes(raw)
            report['snapshot_sha256'] = sha(out / 'registry-snapshot.json')
            report['sources_registry_sha256_before'] = sha(ROOT / 'research/sources.json')
            argv = ['git', '-C', str(WT), 'show', '4bea9b59d1d24c2f7f53f4028769b6e420be556e:tools/lab.py']
            result = subprocess.run(argv, env=ENV, capture_output=True, timeout=15)
            check('frozen-baseline-git-read', result.returncode == 0)
            report['baseline_source_read'] = dict(argv=argv, exit_code=result.returncode,
                                                  stdout_sha256=hashlib.sha256(result.stdout).hexdigest(),
                                                  environment_overrides={k: ENV[k] for k in ['GIT_NO_LAZY_FETCH', 'GIT_OPTIONAL_LOCKS']})
            (out / 'baseline_lab.py').write_bytes(result.stdout)
            variants = [('baseline', out / 'baseline_lab.py'), ('candidate', WT / 'tools/lab.py')]
            for label, module in variants:
                command([sys.executable, BASE / 'worker.py', 'profile', '--module', module, '--root', ROOT,
                         '--snapshot', out / 'registry-snapshot.json', '--out', out / (label + '-profile')], label + '-profile', 90)
            before = load(out / 'baseline-profile/report.json')
            after = load(out / 'candidate-profile/report.json')
            check('same-full-validation-result', before['returned_full_unchanged_state'] and after['returned_full_unchanged_state']
                  and before['result_sha256'] == after['result_sha256'] and before['snapshot_sha256'] == after['snapshot_sha256'])
            for label, module in variants:
                command([sys.executable, BASE / 'worker.py', 'outputs', '--module', module, '--root', ROOT,
                         '--snapshot', out / 'registry-snapshot.json', '--out', out / (label + '-outputs')], label + '-outputs', 30)
            check('all-generated-output-bytes-identical', load(out / 'baseline-outputs/report.json')['generated']
                  == load(out / 'candidate-outputs/report.json')['generated'])
            check('source-registry-unchanged-during-profile', report['sources_registry_sha256_before'] == sha(ROOT / 'research/sources.json'))
            report['profile_comparison'] = {'baseline': before, 'candidate': after,
                                            'wall_speedup': before['seconds'] / after['seconds']}
        report['outcome'] = 'pass'
        report['summary'] = 'Bounded real filesystem freshness/claim tests and stale-cache negative pass' if args.phase == 'tests' else 'Actual identical registry snapshot validates with identical full state/output bytes; measured profile improvement recorded'
    except Exception as error:
        report['error'] = repr(error)
        if 'supervisor' in locals() and isinstance(error, supervisor.ResourceDeferred):
            report['outcome'] = 'inconclusive'
            report['summary'] = 'Resource-deferred at unchanged stable4GiB admission; no child started for deferred command'
    report['source_hashes'] = {str(p): sha(p) for p in [WT / 'tools/lab.py', WT / 'tests/test_lab_validation_cache.py', BASE / 'worker.py', Path(__file__)]}
    report['artifacts'] = {str(p.relative_to(ROOT)): sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    (out / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report.get(k) for k in ['outcome', 'error', 'summary']}, indent=2))
    return report['outcome'] != 'pass'


if __name__ == '__main__':
    raise SystemExit(main())
