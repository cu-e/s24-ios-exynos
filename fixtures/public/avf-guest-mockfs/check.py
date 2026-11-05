#!/usr/bin/env python3
"""Real CLI controls using generated, nonbootable structural inputs; no compiler."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
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


def fixture():
    # Header, __TEXT segment and UNIXTHREAD, followed by deliberately ZERO data.
    # No instructions are authored or executed; not an owned PID1 candidate.
    segment = struct.pack('<II16sQQQQiiII', 0x19, 72, b'__TEXT',
                          0x100000000, 4096, 0, 512, 5, 5, 0, 0)
    thread = bytearray(288)
    struct.pack_into('<4I', thread, 0, 5, 288, 6, 68)
    struct.pack_into('<Q', thread, 272, 0x100000190)
    header = struct.pack('<8I', 0xFEEDFACF, 0x0100000C, 0, 2, 2, 360, 0, 0)
    return bytearray((header + segment + thread).ljust(512, b'\0'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--main', type=Path, required=True)
    args = parser.parse_args()
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    results = []
    sources = json.loads((Path(__file__).parent / 'sources.json').read_text())
    for row in sources['sources']:
        path = args.main / row['path']
        canonical = hashlib.sha1(f'blob {path.stat().st_size}\0'.encode())
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(65536), b''):
                canonical.update(block)
        results.append({'name': 'source-pin-' + row['upstream']['path'],
                        'pass': sha(path) == row['sha256'] and canonical.hexdigest() == row['git_blob_sha1'],
                        'path': str(path), 'sha256': sha(path), 'git_blob_sha1': canonical.hexdigest()})

    def run(name, argv, expected):
        start = time.monotonic()
        peak = None
        with (out / (name + '.stdout.txt')).open('xb') as stdout, (out / (name + '.stderr.txt')).open('xb') as stderr:
            env = dict(os.environ, LC_ALL='C', PYTHONUTF8='1', PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1')
            proc = subprocess.Popen(argv, stdout=stdout, stderr=stderr, env=env,
                                    stdin=subprocess.DEVNULL, start_new_session=True)
            deadline = start + 10
            while True:
                value = hwm(proc.pid)
                if value is not None:
                    peak = max(peak or 0, value)
                # Linux retains /proc VmHWM for this owned child until waitpid.
                ended = os.waitid(os.P_PID, proc.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                if ended is not None:
                    break
                if time.monotonic() >= deadline:
                    os.killpg(proc.pid, signal.SIGKILL)
                    break
                time.sleep(0.005)
            code = proc.wait(timeout=2)
        result = {'name': name, 'argv': [str(x) for x in argv], 'exit_code': code,
                  'expected_exit_code': expected, 'pass': code == expected,
                  'elapsed_seconds': round(time.monotonic() - start, 6),
                  'proc_VmHWM_observed_bytes': peak,
                  'stdout_sha256': sha(out / (name + '.stdout.txt')),
                  'stderr_sha256': sha(out / (name + '.stderr.txt'))}
        if code in (0, 1):
            captured = out / (name + ('.stdout.txt' if code == 0 else '.stderr.txt'))
            try:
                result['child_proc_self_VmHWM_bytes'] = json.loads(captured.read_text())['proc_self_VmHWM_bytes']
            except (ValueError, KeyError):
                result['child_proc_self_VmHWM_bytes'] = None
        results.append(result)
        return code

    base = fixture()
    (out / 'synthetic.macho').write_bytes(base)
    provenance = {'origin': 'synthetic-structural-control',
                  'input_sha256': sha(out / 'synthetic.macho'),
                  'sources': [{'path': str(Path(__file__).resolve()), 'sha256': sha(Path(__file__))}],
                  'build_evidence': 'Generated structural headers and zero bytes only; no compiler or executable candidate.'}
    (out / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
    prefix = [sys.executable, '-s', str(TOOL)]

    def pack(name, src, destination, expected=0, declared=None, prov=None):
        return run(name, prefix + ['pack', '--input', str(src), '--input-sha256', declared or sha(src),
                                  '--provenance', str(prov or out / 'provenance.json'),
                                  '--out', str(destination)], expected)

    pack('pack-one', out / 'synthetic.macho', out / 'one')
    pack('pack-two', out / 'synthetic.macho', out / 'two')
    run('verify', prefix + ['verify', '--package', str(out / 'one')], 0)
    image = (out / 'one/root.ramdisk').read_bytes()
    results.append({'name': 'independent-exact-prefix-zero-padding',
                    'pass': len(image) == 16384 and image[:512] == base and not any(image[512:])})
    results.append({'name': 'deterministic-output',
                    'pass': sha(out / 'one/root.ramdisk') == sha(out / 'two/root.ramdisk') and
                    sha(out / 'one/package.json') == sha(out / 'two/package.json')})
    pack('reuse-output', out / 'synthetic.macho', out / 'one', 1)
    pack('wrong-hash', out / 'synthetic.macho', out / 'bad-hash', 1, '0' * 64)
    pp = out / 'wrong-hash.provenance.json'
    pp.write_text(json.dumps(dict(provenance, input_sha256='0' * 64)) + '\n')
    pack('wrong-bound-input-bytes', out / 'synthetic.macho', out / 'bad-bound-bytes', 1,
         '0' * 64, pp)
    link = out / 'symlink.macho'
    link.symlink_to(out / 'synthetic.macho')
    pack('symlink-input', link, out / 'bad-symlink', 1)

    mutants = {}
    mutants['short-header'] = base[:31]
    mutants['short-command-table'] = base[:391]
    mutants['short-segment-bytes'] = base[:511]

    def mutant(name, position, fmt, *values):
        data = base.copy()
        struct.pack_into(fmt, data, position, *values)
        mutants[name] = data

    mutant('wrong-cpu', 4, '<I', 7)
    mutant('arm64e-not-selected', 8, '<I', 2)
    mutant('object-not-executable', 12, '<I', 1)
    mutant('zero-command-count', 16, '<I', 0)
    mutant('huge-command-count', 16, '<I', 0xFFFFFFFF)
    mutant('huge-command-table', 20, '<I', 0xFFFFFFFF)
    mutant('nonzero-reserved', 28, '<I', 1)
    mutant('misaligned-command', 36, '<I', 71)
    mutant('command-overrun', 36, '<I', 368)
    mutant('dynamic-linker-command', 32, '<I', 0xE)
    mutant('unknown-command', 32, '<I', 0x7FFFFFFF)
    mutant('segment-overrun', 80, '<Q', 513)
    mutant('vm-overflow', 56, '<QQ', 0xFFFFFFFFFFFFFF00, 4096)
    mutant('filesize-over-vmsize', 64, '<Q', 1)
    mutant('section-count-mismatch', 96, '<I', 1)
    mutant('executable-permission-absent', 92, '<I', 1)
    mutant('entry-zero', 376, '<Q', 0)
    mutant('entry-in-bss', 376, '<Q', 0x100000201)
    mutant('entry-kernel-space', 376, '<Q', 0xFFFFFFF007004000)
    mutant('wrong-thread-flavor', 112, '<I', 1)
    mutant('wrong-thread-count', 116, '<I', 67)
    mutant('missing-thread', 104, '<I', 0x1B)
    for name, data in mutants.items():
        src = out / (name + '.macho')
        src.write_bytes(data)
        prov = dict(provenance, input_sha256=sha(src))
        pp = out / (name + '.provenance.json')
        pp.write_text(json.dumps(prov) + '\n')
        pack(name, src, out / ('package-' + name), 1, prov=pp)
    oversized = out / 'oversize.macho'
    with oversized.open('wb') as stream:
        stream.write(base)
        stream.truncate(16 * 1024 * 1024 + 1)
    pp = out / 'oversize.provenance.json'
    pp.write_text(json.dumps(dict(provenance, input_sha256=sha(oversized))) + '\n')
    pack('oversize', oversized, out / 'package-oversize', 1, prov=pp)

    # Corrupt each independently packaged result, preserving every failed artifact.
    with (out / 'one/root.ramdisk').open('r+b') as stream:
        stream.seek(512)
        stream.write(b'X')
    run('nonzero-padding', prefix + ['verify', '--package', str(out / 'one')], 1)
    with (out / 'two/root.ramdisk').open('r+b') as stream:
        stream.truncate(16383)
    run('truncated-image', prefix + ['verify', '--package', str(out / 'two')], 1)
    pack('pack-prefix-control', out / 'synthetic.macho', out / 'three')
    with (out / 'three/root.ramdisk').open('r+b') as stream:
        stream.seek(400)
        stream.write(b'X')
    run('changed-executable', prefix + ['verify', '--package', str(out / 'three')], 1)
    summary = {'outcome': 'pass' if all(r['pass'] for r in results) else 'fail',
               'scope': 'synthetic structural host controls only', 'controls': results,
               'checker_proc_VmHWM_bytes': hwm(os.getpid()),
               'tool_sha256': sha(TOOL), 'checker_sha256': sha(Path(__file__)),
               'guest_executed': False, 'compiler_executed': False}
    (out / 'report.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({'outcome': summary['outcome'], 'controls': len(results),
                      'report': str(out / 'report.json')}))
    return 0 if summary['outcome'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
