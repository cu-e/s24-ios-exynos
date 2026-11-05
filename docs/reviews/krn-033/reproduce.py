#!/usr/bin/env python3
"""Independent bounded source/capsule audit and fresh focused host probe."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tarfile
import time
import zipfile

HERE = Path(__file__).resolve().parent
WT = HERE.parents[2]
MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
IMPL = MAIN / 'worktrees/krn-033-20261105'
GCM = IMPL / 'src/platform/crypto/gcm'
SHARED = MAIN / 'src/platform/crypto/xts/vendor'
BASE = IMPL / 'artifacts/crypto-gcm'
FROZEN = 'f845dc66ff0124bcdbfe36965c95ce18c3da7c8c'
PIN = '068ff080b369adfac81509f9b57b2afabaf82dc5'
ENV = {**os.environ, 'GIT_NO_LAZY_FETCH': '1', 'GIT_OPTIONAL_LOCKS': '0', 'PYTHONDONTWRITEBYTECODE': '1'}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        while data := f.read(1024 * 1024):
            h.update(data)
    return h.hexdigest()


def must(test, message):
    if not test:
        raise ValueError(message)


def main():
    name = sys.argv[1]
    must(re.fullmatch(r'[a-zA-Z0-9_-]+', name), 'Invalid run name')
    out = WT / 'artifacts/review-gcm' / name
    out.mkdir(parents=True, exist_ok=False)
    evidence = dict(kind='source-review', origin='local-host', outcome='fail', task='REV-018',
                    owner='codex-team-review-gcm-20261105-ce', experiment='GCMREV-001',
                    recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                    commands=[], source_hashes={}, original_capsules={}, verified_artifact_hashes={},
                    admission=[], probe_only=True, QEMU_executed=False)

    def run(argv, label, compile_or_probe=False):
        argv = list(map(str, argv))
        if compile_or_probe:
            samples = []
            for i in range(3):
                available = int(re.search(r'^MemAvailable:\s+(\d+)', Path('/proc/meminfo').read_text(), re.M)[1])
                samples.append({'observed_at': datetime.now(timezone.utc).isoformat(), 'MemAvailable_KiB': available})
                must(available >= 4 * 1024 * 1024, 'Defer below4GiB before ' + label)
                if i < 2:
                    time.sleep(1)
            evidence['admission'].append({'command': label, 'samples': samples})
        stdout, stderr = out / (label + '.stdout'), out / (label + '.stderr')
        started = time.monotonic()
        seen = set()
        peak = 0
        stopped = None
        with stdout.open('wb') as so, stderr.open('wb') as se:
            p = subprocess.Popen(argv, env=ENV, stdout=so, stderr=se, start_new_session=True)
            while p.poll() is None:
                todo = [p.pid]
                current = set()
                rss = 0
                while todo:
                    pid = todo.pop()
                    if pid in current:
                        continue
                    current.add(pid)
                    seen.add(pid)
                    try:
                        status = Path(f'/proc/{pid}/status').read_text()
                        m = re.search(r'^VmRSS:\s+(\d+)', status, re.M)
                        if m:
                            rss += int(m[1]) * 1024
                        todo.extend(map(int, Path(f'/proc/{pid}/task/{pid}/children').read_text().split()))
                    except (FileNotFoundError, ProcessLookupError):
                        pass
                peak = max(peak, rss)
                if rss > 256 * 1024 * 1024 or time.monotonic() - started > 45:
                    stopped = 'RSS cap' if rss > 256 * 1024 * 1024 else '45second timeout'
                    os.killpg(p.pid, signal.SIGKILL)
                    break
                time.sleep(0.02)
            code = p.wait()
        live = []
        for pid in seen:
            try:
                stat = Path(f'/proc/{pid}/stat').read_text().split(')', 1)[1].split()
                if stat[0] != 'Z':
                    live.append(pid)
            except FileNotFoundError:
                pass
        row = dict(argv=argv, label=label, exit_code=code, elapsed_seconds=time.monotonic()-started,
                   peak_owned_RSS_bytes=peak, observed_pids=sorted(seen), live_children_after=live,
                   stdout_sha256=sha(stdout), stderr_sha256=sha(stderr), stopped=stopped)
        evidence['commands'].append(row)
        must(code == 0 and not live and stopped is None, 'Read/test command failed: ' + label)
        return stdout.read_bytes()

    try:
        evidence['commit'] = run(['git', '-C', WT, 'rev-parse', 'HEAD'], 'review-commit').decode().strip()
        evidence['implementation_commit'] = FROZEN
        evidence['source_hashes'][str(Path(__file__))] = sha(__file__)
        evidence['source_hashes'][str(HERE / 'focused.c')] = sha(HERE / 'focused.c')
        capsules = {}
        for session in ['acceptance-session1', 'cpu-controls-session2', 'arm-session1', 'cpu-session1', 'host-session4']:
            path = BASE / session / 'evidence.json'
            data = json.loads(path.read_text())
            capsules[session] = data
            evidence['original_capsules'][session] = dict(path=str(path), sha256=sha(path), outcome=data['outcome'], summary=data['summary'])
            for raw, expected in data['artifact_hashes'].items():
                path = Path(raw) if Path(raw).is_absolute() else MAIN / raw
                must(sha(path) == expected, 'Original artifact changed: ' + raw)
                evidence['verified_artifact_hashes'][str(path)] = expected
        acceptance = capsules['acceptance-session1']
        must(acceptance['commit'] == FROZEN and acceptance['outcome'] == 'pass', 'Frozen acceptance binding')
        for raw, expected in acceptance['source_hashes'].items():
            path = IMPL / raw
            must(sha(path) == expected, 'Actual frozen source changed: ' + raw)
            canonical = run(['git', '-C', MAIN, 'show', FROZEN + ':' + raw], 'frozen-source-' + str(len(evidence['source_hashes'])))
            must(hashlib.sha256(canonical).hexdigest() == expected, 'Frozen commit source differs: ' + raw)
            evidence['source_hashes'][str(path)] = expected
        archive = BASE / 'source-session1/mbedtls.tar.gz'
        must(sha(archive) == 'ca6bd316bbec49ef20088f39b8755fcaec0b7e45781506de55b17cd191ae6937', 'Complete canonical archive binding')
        member_checks = {}
        with tarfile.open(archive) as tar:
            for directory in [GCM / 'vendor', SHARED]:
                provenance = json.loads((directory / 'provenance.json').read_text())
                for member, expected in provenance['files'].items():
                    raw = tar.extractfile('mbedtls-' + PIN + '/' + member).read()
                    actual = directory / member
                    patch = provenance.get('patches', {}).get(member)
                    must(sha(actual) == expected, 'Consumed vendor changed')
                    if patch:
                        must(hashlib.sha256(raw).hexdigest() == patch['upstream_sha256'] and expected == patch['local_sha256'], 'Patch pre/post changed')
                        old = b'#include <assert.h>\n'
                        new = b'/* Owned freestanding AES-only port: this unit uses no runtime assert. */\n#if !defined(S24_XTS_FREESTANDING)\n#include <assert.h>\n#endif\n'
                        must(raw.count(old) == 1 and raw.replace(old, new) == actual.read_bytes(), 'Patch changes beyond named include guard')
                    else:
                        must(hashlib.sha256(raw).hexdigest() == expected, 'Incomplete canonical vendor: ' + member)
                    member_checks[str(actual)] = dict(member=member, sha256=expected, bytes=actual.stat().st_size, accepted_patch=bool(patch))
        evidence['complete_member_checks'] = member_checks
        source_pin = 'c54f35ca767986246321eb901baf8f5ff7923f6a'
        selected = ['EXTERNAL_HEADERS/corecrypto/ccmode.h', 'EXTERNAL_HEADERS/corecrypto/ccmode_impl.h',
                    'EXTERNAL_HEADERS/corecrypto/cc.h', 'libkern/libkern/crypto/register_crypto.h',
                    'libkern/crypto/corecrypto_aes.c', 'bsd/netinet6/esp_rijndael.c']
        for index, raw in enumerate(selected):
            data = run(['git', '-C', MAIN / 'references/apple-xnu', 'show', source_pin + ':' + raw], 'selected-source-' + str(index))
            actual = MAIN / 'references/apple-xnu' / raw
            must(data == actual.read_bytes(), 'Selected source pin differs')
            evidence['source_hashes'][str(actual)] = sha(actual)
        # Independently reconstruct first-valid/first-FAIL primary selections
        # from all records, without executing the full oracle or adapter matrix.
        archive = BASE / 'source-session2/nist-1.zip'
        must(sha(archive) == 'f9fc479e134cde2980b3bb7cddbcb567b2cd96fd753835243ed067699f26a023', 'Primary corpus binding')
        vectors = json.loads((BASE / 'host-session4/vectors.json').read_text())
        selected_records = {}
        groups = set()
        total = 0
        primary_hashes = {}
        with zipfile.ZipFile(archive) as zip:
            for member in sorted(zip.namelist()):
                raw = zip.read(member)
                primary_hashes[member] = hashlib.sha256(raw).hexdigest()
                parameters = {}
                record = {}

                def flush():
                    nonlocal total, record
                    if not record:
                        return
                    total += 1
                    group = (member, tuple(sorted(parameters.items())))
                    groups.add(group)
                    key = (*group, bool(record.get('FAIL')))
                    if key not in selected_records:
                        selected_records[key] = (int(record['Count']), dict(record))
                    record = {}

                for text in raw.decode().splitlines():
                    text = text.strip()
                    if not text:
                        flush()
                    elif text.startswith('['):
                        flush()
                        k, v = text[1:-1].split(' = ')
                        parameters[k] = int(v)
                    elif text == 'FAIL':
                        record['FAIL'] = True
                    elif re.fullmatch(r'\w+\s*=\s*.*', text) and not text.startswith('#'):
                        k, v = re.fullmatch(r'(\w+)\s*=\s*(.*)', text).groups()
                        if k == 'Count':
                            flush()
                        record[k] = v
                flush()
        nist = [v for v in vectors['vectors'] if v['source'] == 'NIST']
        must(len(nist) == len(selected_records) == 4723 and len(groups) == 3150 and total == 47250, 'Independent primary coverage differs')
        for v in nist:
            key = (v['file'], tuple(sorted(v['parameters'].items())), v['bad'])
            count, record = selected_records.pop(key)
            must(count == v['count'], 'Different primary representative selected')
            for k, raw in [('key', 'Key'), ('iv', 'IV'), ('aad', 'AAD'), ('ct', 'CT'), ('tag', 'Tag')]:
                must(v[k] == record[raw], 'Primary vector bytes differ')
            if not v['bad']:
                must(v['pt'] == record['PT'] and v['computed'] == record['Tag'], 'Valid primary plaintext/tag differs')
        must(not selected_records and primary_hashes == vectors['files'], 'Primary file/selection omission')
        evidence['independent_corpus'] = dict(total_records=total, parameter_groups=len(groups), representatives=len(nist),
                                             oracle_extra=len(vectors['vectors'])-len(nist), raw_file_hashes=primary_hashes,
                                             note='FAIL plaintext/computed tags remain oracle-derived; not primary authenticated plaintext')
        host = capsules['host-session4']
        compiler = Path(host['tools']['host']['path'])
        must(sha(compiler) == host['tools']['host']['sha256'], 'Accepted host compiler changed')
        evidence['compiler'] = host['tools']['host']
        for raw, expected in host['tools']['host']['runtime_hashes'].items():
            must(sha(raw) == expected, 'Accepted sanitizer runtime changed')
        objects = [BASE / 'host-session4' / ('host-' + n + '.o') for n in ['adapter', 'backend', 'block', 'constant']]
        objects += [Path(p) for p in host['reused_host_objects']]
        for obj in objects:
            expected = host['artifact_hashes'].get(str(obj.relative_to(MAIN))) or host['reused_host_objects'].get(str(obj))
            must(expected and sha(obj) == expected, 'Reused actual object mismatch')
        evidence['linked_objects'] = {str(p): sha(p) for p in objects}
        common = ['-O1', '-g', '-Wall', '-Wextra', '-Werror', '-fno-builtin', '--target=x86_64-unknown-linux-gnu',
                  '-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-Wl,--threads=1',
                  '-I' + str(GCM), '-I' + str(GCM / 'vendor/include'), '-I' + str(SHARED / 'include'),
                  '-I' + str(GCM / 'vendor/library'), '-I' + str(SHARED / 'library'),
                  '-I' + str(MAIN / 'references/apple-xnu/EXTERNAL_HEADERS'),
                  '-DMBEDTLS_CONFIG_FILE="s24_gcm_profile.h"']
        run([compiler, *common, '-MMD', '-MF', out / 'focused.d', HERE / 'focused.c', *objects, '-o', out / 'focused'], 'focused-compile-link', True)
        probe = run([out / 'focused'], 'focused-run', True).decode()
        must(re.search(r'GCM REVIEW PASS checks=\d+ context=1312 alignment=16', probe), 'Fresh focused marker absent')
        evidence['focused_result'] = probe.strip()
        evidence['outcome'] = 'pass'
        evidence['summary'] = 'Independent canonical source/capsule/corpus audit and descriptor-sized ASan/UBSan GCM review probe pass; bounded no finding'
    except Exception as error:
        evidence['error'] = repr(error)
        evidence['summary'] = 'Independent review stopped with retained diagnostic; inspect before drawing findings'
    finally:
        evidence['finished_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
        evidence['reviewer_process_memory'] = [s for s in Path('/proc/self/status').read_text().splitlines() if s.startswith(('VmHWM:', 'VmRSS:'))]
        artifacts = {str(p.relative_to(MAIN)): sha(p) for p in out.iterdir() if p.is_file()}
        evidence['artifacts'] = list(artifacts)
        evidence['artifact_hashes'] = artifacts
        (out / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps({k: evidence.get(k) for k in ['outcome', 'summary', 'error', 'focused_result', 'reviewer_process_memory']}, indent=2))
    return 0 if evidence['outcome'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
