#!/usr/bin/env python3
"""Run source-pinned real-candidate packaging controls, without compiler or guest."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
TOOL = ROOT / 'tools/build/avf_guest_mockfs.py'


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(65536), b''):
            h.update(block)
    return h.hexdigest()


def hwm(pid):
    try:
        for row in Path(f'/proc/{pid}/status').read_text().splitlines():
            if row.startswith('VmHWM:'):
                return int(row.split()[1]) * 1024
    except FileNotFoundError:
        pass
    return None


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--main', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {'kind': 'host-test', 'origin': 'local-host', 'task': 'VM-024',
              'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'argv': sys.argv, 'controls': [], 'commands': [], 'outcome': 'fail',
              'compiler_executed': False, 'guest_executed': False,
              'executable_qualified': False}

    def check(name, passed, **detail):
        report['controls'].append(dict(name=name, passed=bool(passed), **detail))
        if not passed:
            raise ValueError(name)

    def run(name, arguments, expected=0):
        argv = [sys.executable, '-s', str(TOOL)] + [str(x) for x in arguments]
        start = time.monotonic()
        observed, timed_out = None, False
        stdout, stderr = out / (name + '.stdout.json'), out / (name + '.stderr.txt')
        with stdout.open('xb') as sout, stderr.open('xb') as serr:
            proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=sout, stderr=serr,
                                    start_new_session=True,
                                    env=dict(os.environ, LC_ALL='C', PYTHONUTF8='1',
                                             PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1'))
            while True:
                value = hwm(proc.pid)
                if value is not None:
                    observed = max(observed or 0, value)
                ended = os.waitid(os.P_PID, proc.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                if ended is not None:
                    break
                if time.monotonic() - start >= 10:
                    timed_out = True
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    break
                time.sleep(0.005)
            code = proc.wait(timeout=2)
        row = {'name': name, 'argv': argv, 'exit_code': code, 'expected_exit_code': expected,
               'elapsed_seconds': time.monotonic() - start, 'timed_out': timed_out,
               'stdout': str(stdout), 'stderr': str(stderr), 'stdout_sha256': sha(stdout),
               'stderr_sha256': sha(stderr), 'observed_proc_VmHWM_bytes': observed}
        try:
            row['child_proc_self_VmHWM_bytes'] = json.loads(
                (stdout if code == 0 else stderr).read_text())['proc_self_VmHWM_bytes']
        except (ValueError, KeyError):
            row['child_proc_self_VmHWM_bytes'] = None
        report['commands'].append(row)
        check(name, code == expected and not timed_out)

    try:
        spec = json.loads((HERE / 'vm034-candidate.json').read_text())
        check('frozen-packager', sha(TOOL) == spec['frozen_packager_sha256'])
        report['packager_sha256'] = sha(TOOL)
        report['runner_sha256'] = sha(Path(__file__))
        report['input_descriptor_sha256'] = sha(HERE / 'vm034-candidate.json')
        pins = spec['pins']
        original_sources = json.loads((HERE / 'sources.json').read_text())['sources']

        def snapshot():
            rows = []
            for pin in pins + original_sources:
                path = args.main / pin['path']
                actual = sha(path)
                check('input-pin-' + pin['path'], actual == pin['sha256'])
                row = {'path': str(path), 'sha256': actual, 'bytes': path.stat().st_size,
                       'mode': path.stat().st_mode & 0o777}
                if 'git_blob_sha1' in pin:
                    git = hashlib.sha1(f"blob {path.stat().st_size}\0".encode())
                    with path.open('rb') as stream:
                        for block in iter(lambda: stream.read(65536), b''):
                            git.update(block)
                    check('canonical-blob-' + pin['path'], git.hexdigest() == pin['git_blob_sha1'])
                    row['git_blob_sha1'] = git.hexdigest()
                rows.append(row)
            return rows

        report['inputs_before'] = snapshot()
        by_role = {row['role']: args.main / row['path'] for row in pins}
        image = by_role['candidate_executable']
        descriptor = json.loads(by_role['candidate_descriptor'].read_text())
        provenance = by_role['mockfs_provenance']
        review = json.loads(by_role['compiled_admission'].read_text())
        check('external-compiled-review-exact-candidate', review['outcome'] == 'pass' and
              review['compiled_ABI_review_pass'] is True and review['candidate'] == descriptor)
        check('raw-build-provenance-binding', json.loads(provenance.read_text())['build_evidence'] ==
              review['raw_build_evidence'])
        report['external_review_boundaries'] = review['boundaries']
        report['retained_build_warning'] = by_role['retained_build_warning'].read_text()
        samples = []
        for i in range(3):
            line = next(s for s in Path('/proc/meminfo').read_text().splitlines()
                        if s.startswith('MemAvailable:'))
            samples.append({'sample': i + 1, 'MemAvailable_bytes': int(line.split()[1]) * 1024})
            if i < 2:
                time.sleep(1)
        report['memory_admission'] = samples
        check('stable-memory-admission', all(s['MemAvailable_bytes'] >= 4 * 1024 ** 3 for s in samples))
        sha_input = descriptor['sha256']
        for name in ('package-one', 'package-two'):
            run(name, ['pack', '--input', image, '--input-sha256', sha_input,
                       '--provenance', provenance, '--out', out / name])
            run('verify-' + name, ['verify', '--package', out / name])
        first, second = out / 'package-one', out / 'package-two'
        meta = json.loads((first / 'package.json').read_text())
        check('deterministic-image', sha(first / 'root.ramdisk') == sha(second / 'root.ramdisk'))
        check('deterministic-metadata', sha(first / 'package.json') == sha(second / 'package.json'))
        check('exact-provenance-preserved', meta['provenance'] == json.loads(provenance.read_text()) and
              meta['provenance_descriptor_sha256'] == sha(provenance))
        check('package-flags-retain-limits', meta['executable_qualified'] is False and
              meta['guest_executed'] is False)
        n = image.stat().st_size
        expected_image_hash = hashlib.sha256()
        with image.open('rb') as source, (first / 'root.ramdisk').open('rb') as packed:
            for block in iter(lambda: source.read(65536), b''):
                check('independent-exact-executable-prefix', packed.read(len(block)) == block)
                expected_image_hash.update(block)
            tail = packed.read(16384)
            check('independent-zero-padding', len(tail) == -n % 16384 and not any(tail) and
                  not packed.read(1))
            expected_image_hash.update(bytes(-n % 16384))
        check('independent-entire-image-hash', expected_image_hash.hexdigest() == sha(first / 'root.ramdisk'))
        pristine_hashes = {str(p.relative_to(out)): sha(p) for parent in (first, second)
                           for p in parent.iterdir() if p.is_file()}
        run('reject-output-reuse', ['pack', '--input', image, '--input-sha256', sha_input,
                                   '--provenance', provenance, '--out', first], 1)

        def copied(name):
            destination = out / name
            shutil.copytree(first, destination)
            return destination

        changed = copied('tampered-prefix')
        with (changed / 'root.ramdisk').open('r+b') as stream:
            at = min(4096, n - 1)
            stream.seek(at)
            value = stream.read(1)[0]
            stream.seek(at)
            stream.write(bytes([value ^ 1]))
        run('reject-changed-prefix', ['verify', '--package', changed], 1)
        truncated = copied('tampered-truncation')
        with (truncated / 'root.ramdisk').open('r+b') as stream:
            stream.truncate(meta['image_bytes'] - 1)
        run('reject-truncated-image', ['verify', '--package', truncated], 1)
        extended = copied('tampered-extension')
        with (extended / 'root.ramdisk').open('ab') as stream:
            stream.write(b'\0')
        run('reject-extended-image', ['verify', '--package', extended], 1)
        false_claim = copied('tampered-qualification')
        claim = json.loads((false_claim / 'package.json').read_text())
        claim['executable_qualified'] = True
        save(false_claim / 'package.json', claim)
        run('reject-qualified-flag', ['verify', '--package', false_claim], 1)
        wrong_provenance = copied('tampered-provenance')
        claim = json.loads((wrong_provenance / 'package.json').read_text())
        claim['provenance']['input_sha256'] = '0' * 64
        save(wrong_provenance / 'package.json', claim)
        run('reject-wrong-provenance-input', ['verify', '--package', wrong_provenance], 1)
        if -n % 16384:
            nonzero = copied('tampered-padding')
            with (nonzero / 'root.ramdisk').open('r+b') as stream:
                stream.seek(n)
                stream.write(b'X')
            run('reject-nonzero-padding', ['verify', '--package', nonzero], 1)
        check('pristine-packages-unchanged-after-controls',
              all(sha(out / p) == value for p, value in pristine_hashes.items()))
        report['inputs_after'] = snapshot()
        check('all-pinned-inputs-immutable', report['inputs_before'] == report['inputs_after'])
        report['outputs'] = [{'path': str(p), 'bytes': p.stat().st_size, 'sha256': sha(p)}
                             for parent in (first, second) for p in sorted(parent.iterdir())]
        report['outcome'] = 'pass'
    except Exception as error:
        report['error'] = {'type': type(error).__name__, 'message': str(error)}
    report['checker_proc_self_VmHWM_bytes'] = hwm(os.getpid())
    report['finished_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    save(out / 'report.json', report)
    files = [{'path': str(p), 'bytes': p.stat().st_size, 'sha256': sha(p)}
             for p in sorted(out.rglob('*')) if p.is_file()]
    save(out / 'artifact-manifest.json', files)
    print(json.dumps({'outcome': report['outcome'], 'report': str(out / 'report.json'),
                      'controls': len(report['controls']), 'commands': len(report['commands']),
                      'error': report.get('error')}))
    return 0 if report['outcome'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
