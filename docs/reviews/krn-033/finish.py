#!/usr/bin/env python3
"""Resume only the unlaunched focused probe after verified source-stage deferral."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
sys.dont_write_bytecode = True
from reproduce import HERE, WT, MAIN, GCM, SHARED, ENV, sha, must


def main():
    parent = WT / 'artifacts/review-gcm/source-session2/evidence.json'
    prior = json.loads(parent.read_text())
    must(prior['error'] == "ValueError('Defer below4GiB before focused-compile-link')" and
         prior['independent_corpus']['representatives'] == 4723 and
         not any(c['label'] == 'focused-compile-link' for c in prior['commands']), 'Exact pre-compile deferral required')
    name = sys.argv[1]
    must(re.fullmatch(r'[A-Za-z0-9_-]+', name), 'Invalid run name')
    out = WT / 'artifacts/review-gcm' / name
    out.mkdir(parents=True, exist_ok=False)
    evidence = dict(kind='source-review', origin='local-host', outcome='fail', task='REV-018',
                    experiment='GCMREV-001', recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                    parent={'path': str(parent), 'sha256': sha(parent)}, commands=[], admission=[],
                    source_hashes={str(HERE / n): sha(HERE / n) for n in ['focused.c', 'finish.py', 'verify_controls.py']})

    def run(argv, label, admit=False):
        if admit:
            admission = {'label': label, 'samples': [], 'admitted': False}
            evidence['admission'].append(admission)
            for i in range(3):
                available = int(re.search(r'^MemAvailable:\s+(\d+)', Path('/proc/meminfo').read_text(), re.M)[1])
                admission['samples'].append({'recorded_at': datetime.now(timezone.utc).isoformat(), 'MemAvailable_KiB': available})
                must(available >= 4194304, 'Defer below4GiB before ' + label + ': ' + str(available) + 'KiB; no child launched')
                if i < 2:
                    time.sleep(1)
            admission['admitted'] = True
        argv = list(map(str, argv))
        started = time.monotonic()
        peak = 0
        seen = set()
        stopped = None
        with (out / (label + '.stdout')).open('wb') as so, (out / (label + '.stderr')).open('wb') as se:
            p = subprocess.Popen(argv, env=ENV, stdout=so, stderr=se, start_new_session=True)
            while p.poll() is None:
                todo = [p.pid]
                current = set()
                rss = 0
                while todo:
                    pid = todo.pop()
                    if pid in current:
                        continue
                    current.add(pid); seen.add(pid)
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
                    stopped = 'RSS cap or45second timeout'
                    os.killpg(p.pid, signal.SIGKILL)
                    break
                time.sleep(0.02)
            code = p.wait()
        live = []
        for pid in seen:
            try:
                if Path(f'/proc/{pid}/stat').read_text().split(')', 1)[1].split()[0] != 'Z':
                    live.append(pid)
            except FileNotFoundError:
                pass
        evidence['commands'].append(dict(argv=argv, label=label, exit_code=code,
                                         elapsed_seconds=time.monotonic()-started, peak_owned_RSS_bytes=peak,
                                         live_children_after=live, stopped=stopped))
        must(code == 0 and not live and not stopped, 'Focused command failed: ' + label)
        return (out / (label + '.stdout')).read_text()

    try:
        # Source/corpus reconstruction already succeeded. Recheck identities,
        # without repeating the full parser or the original algorithm suite.
        for group in ['source_hashes', 'verified_artifact_hashes', 'linked_objects']:
            for path, expected in prior[group].items():
                must(sha(path) == expected, 'Verified source-stage input changed: ' + path)
        compiler = Path(prior['compiler']['path'])
        must(sha(compiler) == prior['compiler']['sha256'], 'Verified compiler changed')
        for path, expected in prior['compiler']['runtime_hashes'].items():
            must(sha(path) == expected, 'Verified sanitizer runtime changed')
        run([sys.executable, HERE / 'verify_controls.py'], 'independent-control-bytes')
        symbols = run(['nm', '--defined-only', *prior['linked_objects']], 'linked-symbols')
        definitions = [s.split()[-1] for s in symbols.splitlines() if len(s.split()) >= 3]
        must(definitions.count('mbedtls_platform_zeroize') == 1 and definitions.count('mbedtls_aes_crypt_ecb') == 1,
             'Duplicate shared zeroizer/AES definitions')
        flags = ['-O1', '-g', '-Wall', '-Wextra', '-Werror', '-fno-builtin', '--target=x86_64-unknown-linux-gnu',
                 '-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-Wl,--threads=1',
                 '-I' + str(GCM), '-I' + str(GCM / 'vendor/include'), '-I' + str(SHARED / 'include'),
                 '-I' + str(GCM / 'vendor/library'), '-I' + str(SHARED / 'library'),
                 '-I' + str(MAIN / 'references/apple-xnu/EXTERNAL_HEADERS'), '-DMBEDTLS_CONFIG_FILE="s24_gcm_profile.h"']
        run([compiler, *flags, '-MMD', '-MF', out / 'focused.d', HERE / 'focused.c', *prior['linked_objects'], '-o', out / 'focused'], 'focused-compile-link', True)
        result = run([out / 'focused'], 'focused-run', True)
        must(re.search(r'GCM REVIEW PASS checks=\d+ context=1312 alignment=16', result), 'Independent focused marker absent')
        dependencies = (out / 'focused.d').read_text().replace('\\\n', ' ').split(':', 1)[1].split()
        evidence['dependencies'] = {p: sha(p) for p in dependencies}
        evidence['focused_result'] = result.strip()
        evidence['outcome'] = 'pass'
        evidence['summary'] = 'Frozen source/corpus stage reused with all identities rechecked; independent guest bytes and fresh descriptor-sized ASan/UBSan probe pass'
    except Exception as error:
        evidence['error'] = repr(error)
        evidence['summary'] = 'Independent focused continuation failed or resource-deferred; original capsules remain unchanged'
    finally:
        evidence['reviewer_process_memory'] = [s for s in Path('/proc/self/status').read_text().splitlines() if s.startswith(('VmHWM:', 'VmRSS:'))]
        evidence['artifact_hashes'] = {str(p.relative_to(MAIN)): sha(p) for p in out.iterdir() if p.is_file()}
        evidence['artifacts'] = list(evidence['artifact_hashes'])
        (out / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps({k: evidence.get(k) for k in ['outcome', 'error', 'focused_result', 'reviewer_process_memory']}, indent=2))
    return evidence['outcome'] != 'pass'


if __name__ == '__main__':
    raise SystemExit(main())
