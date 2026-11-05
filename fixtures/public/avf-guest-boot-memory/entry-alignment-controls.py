#!/usr/bin/env python3
"""Focused actual-byte regressions for reviewed ARM64 entry alignment."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import resource
import struct
import subprocess
import sys
import time
from datetime import datetime, timezone


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def memory():
    return {key: int(value) for key, value in re.findall(r'^(VmHWM|VmRSS):\s+(\d+) kB', Path('/proc/self/status').read_text(), re.M)}


def fixture(entry_offset):
    # Independently packed format-control bytes, never an XNU boot image.
    va = 0xfffffff007000000
    section = struct.pack('<16s16sQQIIIIIIII', b'__kalloc_type', b'__TEXT', va + 0x900,
                          16, 0x900, 3, 0, 0, 0, 0, 0, 0)
    segment = struct.pack('<II16sQQQQIIII', 0x19, 152, b'__TEXT', va, 0x4000, 0, 0x1000, 7, 5, 1, 0) + section
    registers = [0] * 34
    registers[32] = va + entry_offset
    thread = struct.pack('<IIII34Q', 5, 288, 6, 68, *registers)
    commands = segment + thread
    image = (struct.pack('<IIIIIIII', 0xfeedfacf, 0x100000c, 0, 2, 2, len(commands), 0, 0) + commands).ljust(0x1000, b'\0')
    body = struct.pack('<16sII', b'kernel', len(image), 0) + image + bytes(24)
    return struct.pack('<II', 0x50554e58, len(body)) + body


def parser_case(tool, payload, output):
    report = {'tool_sha256': sha(tool), 'payload_sha256': sha(payload)}
    started = time.monotonic()
    code = 0
    try:
        spec = importlib.util.spec_from_file_location('alignment_subject', tool)
        subject = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(subject)
        package = subject.payload(payload)
        image = subject.macho(payload, package['entries']['kernel'])
        report.update(outcome='pass', entry_va=image['entry_va'])
    except ValueError as error:
        report.update(outcome='fail', error=str(error)); code = 2
    report.update(exit_code=code, seconds=time.monotonic() - started, proc_status_memory_kib=memory())
    output.write_text(json.dumps(report, indent=2) + '\n')
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tool', type=Path, required=True)
    parser.add_argument('--payload', type=Path)
    parser.add_argument('--parser-report', type=Path)
    parser.add_argument('--baseline-tool', type=Path)
    parser.add_argument('--main', type=Path)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    resource.setrlimit(resource.RLIMIT_AS, (256 << 20, 256 << 20))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    if args.parser_report:
        return parser_case(args.tool, args.payload, args.parser_report)
    root = Path(__file__).resolve().parents[3]
    output_root = root / 'artifacts/avf-guest-boot-memory'
    assert args.out.resolve().is_relative_to(output_root.resolve())
    args.out.mkdir(parents=True, exist_ok=False)
    before = {str(path): sha(path) for path in (args.tool, args.baseline_tool)}
    env = dict(os.environ, LC_ALL='C', PYTHONUTF8='1', PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1', GIT_NO_LAZY_FETCH='1', GIT_OPTIONAL_LOCKS='0')
    plan = root / 'fixtures/public/avf-guest-boot-memory/console-plan.example.json'
    commands, cases = [], []
    def run(label, argv, expected, evidence):
        started = time.monotonic()
        proc = subprocess.run([str(arg) for arg in argv], env=env, capture_output=True, timeout=20)
        (args.out / (label + '.stdout')).write_bytes(proc.stdout)
        (args.out / (label + '.stderr')).write_bytes(proc.stderr)
        commands.append({'case': label, 'argv': [str(arg) for arg in argv], 'exit_code': proc.returncode,
                         'expected_exit_code': expected, 'seconds': time.monotonic() - started,
                         'stdout_sha256': hashlib.sha256(proc.stdout).hexdigest(), 'stderr_sha256': hashlib.sha256(proc.stderr).hexdigest()})
        assert proc.returncode == expected, (label, proc.stdout, proc.stderr)
        result = json.loads(evidence.read_text())
        if expected == 2:
            assert result['error'] == 'ARM64 thread entry must be four-byte aligned', (label, result)
            assert 'layout_preflight' not in result and 'layout' not in result
        cases.append({'case': label, 'evidence': str(evidence), 'evidence_sha256': sha(evidence), 'outcome': result['outcome'], 'proc_status_memory_kib': result['proc_status_memory_kib']})
        return result
    for offset in (0x800, 0x801, 0x802, 0x803, 0x804):
        payload = args.out / ('owned-entry-%x.xnup' % offset)
        payload.write_bytes(fixture(offset))
        for name, tool, expected in [('baseline-parser', args.baseline_tool, 0), ('corrected-parser', args.tool, 2 if offset % 4 else 0)]:
            label = '%s-%x' % (name, offset); evidence = args.out / (label + '.json')
            run(label, [sys.executable, '-s', __file__, '--tool', tool, '--payload', payload, '--parser-report', evidence], expected, evidence)
        label = 'corrected-cli-%x' % offset; cli_out = args.out / label
        result = run(label, [sys.executable, '-s', args.tool, '--main', args.main, '--payload', payload,
                            '--layout', plan, '--out', cli_out], 2 if offset % 4 else 0, cli_out / 'evidence.json')
        if offset % 4 == 0:
            assert result['layout']['entry_physical'] == 0x43000000 + offset
    assert before == {str(path): sha(path) for path in (args.tool, args.baseline_tool)}, 'Source witness changed'
    report = {'task': 'VM-026', 'experiment': 'VMBOOTMEM-002', 'kind': 'host-test', 'origin': 'local-host', 'outcome': 'pass',
              'recorded_at': datetime.now(timezone.utc).isoformat(), 'summary': 'Immutable baseline accepts five independently packed entries; corrected parser and actual CLI accept aligned800804 and reject unaligned801802803 before layout.',
              'implementation_commit': subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], env=env, text=True).strip(),
              'tools': {'runner_sha256': sha(__file__), 'python': {'path': sys.executable, 'sha256': sha(sys.executable)}},
              'source_witness_hashes_before_after': before, 'commands': commands, 'cases': cases, 'proc_status_memory_kib': memory(),
              'limitations': ['Owned synthetic format bytes only; no genuine kernel, compiler, QEMU, runtime MMU or RAM sufficiency measurement.', 'Original witness paths were read-only.'],
              'files': {str(path.relative_to(root)): sha(path) for path in sorted(args.out.rglob('*')) if path.is_file()}}
    (args.out / 'matrix.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'outcome': 'pass', 'parser_cases': 10, 'cli_cases': 5, 'matrix': str(args.out / 'matrix.json'), 'matrix_sha256': sha(args.out / 'matrix.json')}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
