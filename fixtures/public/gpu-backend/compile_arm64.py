#!/usr/bin/env python3
"""Compile the SGPU core as ARM64 Mach-O with the qualified native compiler and kernel flags.

Takes the real argv recorded for one compiled kernel object and changes only the
source, the output, the depfile and one include directory. Output is never
executed. It shows the core compiles in the kernel's environment and which
symbols it needs; it does not show that the core works on any GPU.
"""
import argparse
import datetime
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import subprocess
import sys

sys.dont_write_bytecode = True
MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
WT = Path(__file__).resolve().parents[3]
COMMON = (MAIN/'tools/build/avf_kernel_objects.py', '9929a7d6f1e748770f54abf3e101350648092027a18c419a242d0348f620f755')
RECIPE = (MAIN/'worktrees/str-040-e1s-native-bsd-a-tail-20261110/artifacts/e1s-native-compile/bsd-a-tail-001/evidence.json', 'bsd/apfs_deflate.o')
COMPILER_SHA = '7972eb2820ae25b5bedff1ea954cef9e9a0e4a15c7a8e440628e8b6540fafc82'
NM = MAIN/'artifacts/xnu-macho-tools/macho-session4/prefix/bin/aarch64-apple-darwin-nm'
QUEUE = MAIN/'artifacts/team-coordination/20261106-team/resource-queue.json'
LOCK = MAIN/'state/.integration.lock'
SOURCES = {'sgpu_abi.h': WT/'src/platform/gpu/abi/sgpu_abi.h', 'sgpu_abi.c': WT/'src/platform/gpu/abi/sgpu_abi.c',
           'sgpu_backend.h': WT/'src/platform/gpu/native/backend/sgpu_backend.h', 'sgpu_backend.c': WT/'src/platform/gpu/native/backend/sgpu_backend.c'}
OBJECTS = ['sgpu_backend', 'sgpu_abi']
LEASE = 'gpu-013-arm64-compile-20261110-claude'
ISSUER = 'claude-gpu-backend-20261110-g13'


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_common():
    raw = COMMON[0].read_bytes()
    require(hashlib.sha256(raw).hexdigest() == COMMON[1], 'Changed common helper')
    spec = importlib.util.spec_from_file_location('gpu_common', COMMON[0])
    module = importlib.util.module_from_spec(spec)
    exec(compile(raw, str(COMMON[0]), 'exec'), module.__dict__)
    return module


def replace_queue(mutate, suffix):
    with LOCK.open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        queue = json.loads(QUEUE.read_text())
        mutate(queue)
        temporary = QUEUE.with_suffix(suffix)
        with temporary.open('x') as stream:
            json.dump(queue, stream, indent=2)
            stream.write('\n')
        os.replace(temporary, QUEUE)


def transform(argv, source, output, depfile, include):
    """Exactly four substitutions; every other flag stays as the kernel build used it."""
    result = list(argv)
    positions = {'-MF': result.index('-MF'), '-o': result.index('-o')}
    result[positions['-MF']+1] = str(depfile)
    result[positions['-o']+1] = str(output)
    sources = [i for i, a in enumerate(result) if a.endswith('.c') and i and result[i-1] not in ('-MF', '-o')]
    require(len(sources) == 1, 'Expected exactly one source in the recipe')
    result[sources[0]] = str(source)
    result.insert(sources[0], '-I'+str(include))
    return result


def limit_memory():
    limit = 4 << 30
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))


def run(argv, cwd, timeout):
    record = dict(argv=[str(a) for a in argv], cwd=str(cwd), started_at=now())
    done = subprocess.run(['/usr/bin/timeout', '--foreground', '--signal=TERM', '--kill-after=10s', f'{timeout}s', *record['argv']], cwd=cwd, env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'},
                          capture_output=True, text=True, preexec_fn=limit_memory)
    record.update(exit_code=done.returncode, ended_at=now())
    return record, done.stdout, done.stderr


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    args = parser.parse_args()
    out = WT/'artifacts/gpu-backend'/args.run
    out.mkdir(parents=True, exist_ok=False)
    snapshot = out/'source'
    snapshot.mkdir()
    report = dict(schema_version=1, kind='host-test', origin='local-host', outcome='inconclusive', recorded_at=now(), task='GPU-013', owner=ISSUER,
                  commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=WT, text=True).strip(),
                  sha256={}, objects={}, commands=[], target_code_executed=False, gpu_executed=False, apple_sdk_used=False,
                  lease=dict(id=LEASE, kind='light_compile', issued_by=ISSUER, note='Self-issued by the Claude session acting as coordinator under the owner directive of 2026-11-10, not by the Codex root coordinator.'))
    for name, path in SOURCES.items():
        (snapshot/name).write_bytes(path.read_bytes())
        report['sha256'][name] = sha(path)
    evidence = json.loads(RECIPE[0].read_text())
    process = next(c['process'] for c in evidence['commands'] if c['role'] == RECIPE[1])
    require(sha(process['argv'][0]) == COMPILER_SHA, 'Compiler is not the qualified binary')
    report['recipe'] = dict(evidence=str(RECIPE[0]), evidence_sha256=sha(RECIPE[0]), role=RECIPE[1], compiler=process['argv'][0], compiler_sha256=COMPILER_SHA, argv_entries=len(process['argv']))
    common = load_common()

    def grant(queue):
        require(all(queue.get(key) is None for key in ['heavy', 'qemu', 'light_compile']), 'Another lease is active')
        queue['light_compile'] = dict(id=LEASE, granted_at=now(), issued_by=ISSUER, purpose='Two small ARM64 Mach-O compiles for GPU-013; lease self-issued by the Claude session acting as coordinator under the owner directive of 2026-11-10, not by the Codex root coordinator. No QEMU or phone operations.')

    replace_queue(grant, '.gpu013.tmp')
    try:
        for name in OBJECTS:
            output, depfile = out/(name+'.o'), out/(name+'.d')
            argv = transform(process['argv'], snapshot/(name+'.c'), output, depfile, snapshot)
            record, stdout, stderr = run(argv, Path(process['cwd']), 120)
            (out/(name+'.stderr.txt')).write_text(stderr)
            record.update(role='compile-'+name, stdout=stdout[-1000:], stderr_lines=len(stderr.splitlines()), warnings=stderr.count(' warning: '), errors=stderr.count(' error: '))
            report['commands'].append(record)
            require(record['exit_code'] == 0, 'Compile failed: '+name+': '+stderr[-1500:])
            validation = common.macho(output, False)
            require(validation['arm64_macho_object'] is True and validation['sha256'] == sha(output), 'Not an ARM64 Mach-O object: '+name)
            symbols, nm_out, nm_err = run([NM, '-u', output], out, 30)
            symbols.update(role='undefined-'+name, stderr=nm_err[-500:])
            report['commands'].append(symbols)
            require(symbols['exit_code'] == 0, 'nm failed: '+nm_err[-500:])
            report['objects'][name] = dict(object=str(output), sha256=sha(output), arm64_macho_object=True, undefined_symbols=sorted(nm_out.split()))
        report['outcome'] = 'pass'
    except Exception as error:
        report.update(outcome='fail', error=repr(error))
    finally:
        def release(queue):
            require(queue['light_compile']['id'] == LEASE, 'Lease changed underneath this run')
            queue['last_light_compile_release'] = dict(id=LEASE, outcome=report['outcome'], evidence=str(out/'evidence.json'), owned_survivors=0)
            queue['light_compile'] = None

        (out/'evidence.json').write_text(json.dumps(report, indent=2)+'\n')
        replace_queue(release, '.gpu013.release.tmp')
    print(json.dumps(dict(outcome=report['outcome'], objects=report['objects'], error=report.get('error'), warnings={c['role']: c.get('warnings') for c in report['commands'] if c['role'].startswith('compile-')}), indent=1))
    return 0 if report['outcome'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
