#!/usr/bin/env python3
"""Inspect the accepted board-neutral runtime and bounded guest driver lookup.

This does not build objects, execute a linker, or qualify a complete guest link.
The existing qualified runtime parser is reused rather than reimplemented.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import signal
import struct
import subprocess
import sys
import time
import traceback

WORK = Path(__file__).resolve().parents[2]
LIMIT = 256 * 1024 * 1024
MIN_AVAILABLE = 4 * 1024 * 1024 * 1024


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def require(value, message):
    if not value:
        raise ValueError(message)


def proc_memory(pid):
    try:
        text = Path(f'/proc/{pid}/status').read_text()
        values = {line.split(':')[0]: int(line.split()[1]) * 1024
                  for line in text.splitlines() if line.startswith(('VmRSS:', 'VmHWM:'))}
        return dict(pid=pid, **values)
    except (FileNotFoundError, ProcessLookupError):
        return dict(pid=pid, VmRSS=0, VmHWM=0)


def available():
    return next(int(line.split()[1]) * 1024 for line in Path('/proc/meminfo').read_text().splitlines()
                if line.startswith('MemAvailable:'))


def namespace(argv, target, link_root):
    require(argv.count('-target') == 1 and argv[argv.index('-target') + 1] == target,
            'Exact guest compiler target required')
    require('-mkernel' in argv and '-DARM64_BOARD_CONFIG_BCM2837' in argv,
            'Genuine BCM2837 kernel recipe required')
    require('-DXNU_NO_TYPE_BUILTINS=0' in argv, 'Real compiler allocator builtins required')
    require(not any(str(link_root) in token for token in argv),
            'Link-only runtime resource tree must not enter compiler header recipes')


def rejected(action, label):
    try:
        action()
    except ValueError as error:
        return dict(control=label, rejected=True, error=str(error))
    raise ValueError('Negative control unexpectedly accepted: ' + label)


def driver_run(argv, out, name):
    """Only one compiler driver process; sample current executable HWM and RSS."""
    pressure = []
    for index in range(3):
        value = available()
        pressure.append(dict(at=datetime.now(timezone.utc).isoformat(), MemAvailable=value))
        require(value >= MIN_AVAILABLE, 'Stable 4GiB MemAvailable admission failed')
        if index < 2:
            time.sleep(1)
    stdout, stderr = out / (name + '.stdout.txt'), out / (name + '.stderr.txt')
    row = dict(argv=argv, cwd=str(WORK), timeout_seconds=15, pressure_admission=pressure,
               stdout=str(stdout), stderr=str(stderr), samples=[], exit_code=None,
               stop_reason=None, compiler_executable_observed=False)
    start = time.monotonic()
    env = os.environ.copy()
    env.update(LC_ALL='C', PYTHONUTF8='1', PYTHONNOUSERSITE='1',
               GIT_NO_LAZY_FETCH='1', GIT_OPTIONAL_LOCKS='0')
    with stdout.open('wb') as so, stderr.open('wb') as se:
        process = subprocess.Popen(argv, cwd=WORK, env=env, stdout=so, stderr=se,
                                   start_new_session=True)
        try:
            while True:
                try:
                    image = Path(f'/proc/{process.pid}/exe').resolve(strict=True)
                except (FileNotFoundError, ProcessLookupError):
                    image = None
                current = image == Path(argv[0]).resolve()
                # Read this first: a cached driver -### can finish before a host-wide /proc scan.
                child = proc_memory(process.pid)
                own = proc_memory(os.getpid())
                try:
                    descendants = Path(f'/proc/{process.pid}/task/{process.pid}/children').read_text().split()
                except (FileNotFoundError, ProcessLookupError):
                    descendants = []
                live = ([process.pid] if current else []) + [int(pid) for pid in descendants]
                row['compiler_executable_observed'] |= current
                row['samples'].append(dict(elapsed_seconds=round(time.monotonic() - start, 4),
                                           controller=own, child=child if current else None,
                                           child_executable=str(image), live_owned_pids=live,
                                           MemAvailable=available()))
                # VmHWM is read only after /proc/exe identifies the current compiler image.
                if len(live) > 1:
                    row['stop_reason'] = 'Unexpected child process from driver-only invocation'
                elif own.get('VmHWM', 0) + (child.get('VmHWM', 0) if current else 0) > LIMIT:
                    row['stop_reason'] = 'Owned controller plus current driver HWM exceeded 256MiB'
                elif time.monotonic() - start > 15:
                    row['stop_reason'] = 'Finite driver-only timeout'
                elif available() < MIN_AVAILABLE:
                    row['stop_reason'] = 'MemAvailable fell below 4GiB'
                if row['stop_reason']:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=2)
                    break
                if process.poll() is not None:
                    break
                time.sleep(.001)
            row['exit_code'] = process.wait(timeout=2)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=2)
    row['elapsed_seconds'] = round(time.monotonic() - start, 4)
    row['remaining_live_owned_children'] = []
    for path in Path('/proc').iterdir():
        if path.name.isdigit():
            try:
                stat = (path / 'stat').read_text().rsplit(')', 1)[1].split()
                if int(stat[2]) == process.pid and stat[0] != 'Z':
                    row['remaining_live_owned_children'].append(int(path.name))
            except (FileNotFoundError, ProcessLookupError, PermissionError):
                pass
    row['stdout_sha256'], row['stderr_sha256'] = sha(stdout), sha(stderr)
    dump(out / (name + '.command.json'), row)
    require(row['stop_reason'] is None and row['exit_code'] == 0,
            f'{name} failed; preserved command evidence')
    require(not row['remaining_live_owned_children'], 'Driver-only group still has a live process')
    require(row['compiler_executable_observed'], 'Current compiler executable HWM was not observed')
    commands = [shlex.split(line) for line in stderr.read_text().splitlines()
                if line.startswith(' "')]
    require(len(commands) == 1, 'Exactly one emitted linker command required')
    require('-cc1' not in commands[0], 'Driver-only lookup must have no compilation job')
    row['emitted_backend_argv'] = commands[0]
    return row


def run(args, report):
    main = args.main.resolve()
    pins = json.loads((WORK / 'fixtures/public/avf-guest-compiler-runtime/inputs.json').read_text())
    paths = {}
    for key, pin in pins['inputs'].items():
        path = main / pin['path']
        require(path.resolve().is_relative_to(main), 'Input escapes MAIN')
        require(path.stat().st_size == pin['size'] and sha(path) == pin['sha256'], 'Changed pinned input: ' + key)
        paths[key] = path
    report['input_pins'] = pins
    report['controller_before'] = proc_memory(os.getpid())
    require(report['controller_before'].get('VmHWM', 0) <= LIMIT, 'Controller exceeded light budget')
    descriptor = json.loads(paths['descriptor'].read_text())
    require(descriptor['archive_sha256'] == pins['inputs']['archive']['sha256'] and
            descriptor['target'] == pins['target'] and descriptor['archive_members'] == 287 and
            descriptor['compiler_sha256'] == pins['inputs']['compiler']['sha256'] and
            descriptor['source_revision'] == pins['runtime_revision'], 'Descriptor pin/profile mismatch')
    link_root = main / descriptor['resource_dir']
    spec = importlib.util.spec_from_file_location('qualified_cc_kext_parser', paths['parser'])
    parser = importlib.util.module_from_spec(spec)
    sys.dont_write_bytecode = True
    spec.loader.exec_module(parser)
    # The archive is pinned at 219448 bytes; do not use this for unbounded files.
    with paths['archive'].open('rb') as stream:
        archive = stream.read(1024 * 1024)
        require(not stream.read(1), 'Archive exceeds bounded parser input')
    members = parser.archive_members(archive)
    expected = json.loads(paths['members'].read_text())
    require(len(members) == len(expected) == 287, 'Archive member count changed')
    definitions, imports, rows = set(), set(), []
    for (name, body), pin in zip(members, expected):
        defined, undefined = parser.object_symbols(body)
        row = dict(name=name, sha256=hashlib.sha256(body).hexdigest(), defined=sorted(defined), undefined=sorted(undefined))
        require(row == pin, 'Archive bytes/symbols differ from qualified member: ' + name)
        definitions.update(defined)
        imports.update(undefined)
        rows.append(row)
    external = sorted(imports - definitions)
    accepted = json.loads(paths['controls_report'].read_text())
    require(external == accepted['runtime_symbols']['external_imports'], 'Archive import boundary changed')
    require(accepted['outcome'] == 'pass', 'Accepted controls parent must pass')
    report['archive'] = dict(members=len(rows), architecture='plain ARM64 Mach-O objects',
                            platform='iOS16.5', external_imports=external,
                            scope='All members inspected; unresolved kernel/libc/section-magic dependencies remain explicit')
    dump(args.out / 'archive-members.json', rows)
    original = json.loads(paths['original_report'].read_text())
    corrected = json.loads(paths['corrected_report'].read_text())
    dependencies = json.loads(paths['original_dependencies'].read_text())
    recipes = {}
    for witness in (original, corrected):
        for command in witness['commands']:
            argv = command['argv']
            if '-c' in argv and '-o' in argv:
                output = Path(argv[argv.index('-o') + 1])
                if output.parent.name == 'objects':
                    require(command['exit_code'] == 0, 'Runtime member compile witness failed')
                    source = Path(argv[argv.index('-c') + 1])
                    source_digest = sha(source)
                    if witness is corrected:
                        require(source_digest == descriptor['source_correction']['patched_sha256'],
                                'Changed corrected genuine source')
                        source_pin = dict(derivative_of=descriptor['source_correction']['base_sha256'])
                    else:
                        if '/source/' in str(source):
                            source_key = str(source).split('/source/', 1)[1]
                            source_pin = original['runtime_source_inputs'][source_key]
                        else:
                            source_key = str(source.relative_to(main))
                            source_pin = dict(sha256=dependencies[source_key],
                                              generated_by='Accepted compiler-rt CMake outline-atomic helper recipe')
                        require(source_digest == source_pin['sha256'], 'Changed original genuine source: ' + source_key)
                    recipes[output.name] = dict(argv=argv, cwd=command['cwd'], exit_code=command['exit_code'],
                                               source_sha256=source_digest, source_pin=source_pin)
    require(set(recipes) == {row['name'] for row in rows}, 'Exact runtime member recipe coverage missing')
    dump(args.out / 'runtime-recipes.json', recipes)
    report['source_provenance'] = dict(runtime_revision=pins['runtime_revision'],
                                      driver_revision=pins['driver_revision'],
                                      member_compile_witnesses=len(recipes),
                                      original_build_outcome=original['outcome'],
                                      original_build_error=original.get('error'),
                                      corrected_outcome=corrected['outcome'],
                                      correction=descriptor['source_correction'])
    report['source_facts'] = [
        dict(input='driver_Driver.cpp', line=494,
             fact='Reserved -lcc_kext is rewritten unconditionally, including with -nostdlib'),
        dict(input='driver_Driver.cpp', line=1358,
             fact='Explicit -resource-dir overrides driver ResourceDir'),
        dict(input='driver_ToolChains_Darwin.cpp', line=2845,
             fact='Darwin support library is resolved under ResourceDir/lib/darwin'),
        dict(input='driver_ToolChains_Darwin.cpp', line=2853,
             fact='iPhoneOS selects libclang_rt.cc_kext_ios.a'),
        dict(input='driver_ToolChains_Darwin.cpp', line=2867,
             fact='Missing resource library is silently omitted by the driver existence check'),
    ]
    guest = json.loads(paths['guest_manifest'].read_text())
    require(len(guest) == 1080, 'Immutable guest graph size changed')
    for row in guest:
        namespace(row['next_owned_compile_argv_template'], pins['target'], link_root)
    report['guest_recipe_namespace'] = dict(count=len(guest), manifest_sha256=sha(paths['guest_manifest']),
                                            link_resource_in_compile_headers=False,
                                            namespace_acceptance_claimed=False)
    bad_arch = bytearray(members[0][1])
    struct.pack_into('<I', bad_arch, 4, 0x1000007)
    bad_platform = bytearray(members[0][1])
    at = 32
    while at < len(bad_platform):
        command, size = struct.unpack_from('<II', bad_platform, at)
        if command in (0x25, 0x32):
            struct.pack_into('<I', bad_platform, at + (8 if command == 0x25 else 12), 0x000e0000)
            break
        at += size
    template = guest[0]['next_owned_compile_argv_template']
    report['negative_controls'] = [
        rejected(lambda: parser.archive_members(archive[:-1]), 'truncated actual archive'),
        rejected(lambda: parser.object_symbols(bad_arch), 'actual member with foreign CPU'),
        rejected(lambda: parser.object_symbols(bad_platform), 'actual member with wrong iOS version'),
        rejected(lambda: namespace([*template, '-resource-dir', str(link_root)], pins['target'], link_root),
                 'link-only resource root in compile namespace'),
        rejected(lambda: namespace(template, 'arm64-apple-macos14', link_root), 'wrong guest target'),
    ]
    if args.driver_lookup:
        report['root_admission'] = pins['root_driver_only_admission']
        require(args.admission == 'root-driver-only-20261106', 'Explicit root driver-only admission required')
        # /dev/null is a declared non-provider input for driver -### expansion only.
        # No compiler frontend, assembler or linker consumes it; no link success is claimed.
        for name, root in [('positive', link_root), ('missing-resource', args.out / 'absent-link-resource')]:
            output = args.out / ('never-built-' + name)
            argv = [str(paths['compiler']), '-target', pins['target'], '-mkernel', '-nostdlib', '-static',
                    '-resource-dir', str(root), '--ld-path=' + str(paths['linker']),
                    '-x', 'object', '/dev/null', '-lcc_kext', '-o', str(output), '-###']
            row = driver_run(argv, args.out, name)
            backend = row['emitted_backend_argv']
            expected_library = str(paths['archive'])
            require(backend[0] == str(paths['linker']), 'Qualified linker must be selected in emitted recipe')
            require(backend.count(expected_library) == (1 if name == 'positive' else 0),
                    'Actual compiler resource lookup differs from expected positive/negative boundary')
            require('-lcc_kext' not in backend, 'Reserved cc_kext name must be interpreted by compiler driver')
            require(not output.exists(), 'Driver-only command unexpectedly built output')
            report['commands'].append(row)
        report['driver_lookup_measured'] = True
    report['controller_after'] = proc_memory(os.getpid())
    require(report['controller_after'].get('VmHWM', 0) <= LIMIT, 'Controller exceeded light budget')
    for key, path in paths.items():
        require(sha(path) == pins['inputs'][key]['sha256'], 'Input changed during qualification: ' + key)
    report['outcome'] = 'pass'


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--main', type=Path, required=True)
    cli.add_argument('--out', type=Path, required=True)
    cli.add_argument('--driver-lookup', action='store_true')
    cli.add_argument('--admission')
    args = cli.parse_args()
    args.out = args.out.resolve()
    require(args.out.is_relative_to(WORK / 'artifacts/avf-guest-compiler-runtime'), 'Owned worktree output required')
    args.out.mkdir(parents=True, exist_ok=False)
    report = dict(task='VM-023', owner='codex-guest-exec-20261106-de', kind='host-test', origin='local-host',
                  recorded_at=datetime.now(timezone.utc).isoformat(), outcome='fail', commands=[],
                  tool_sha256=sha(__file__), driver_lookup_measured=False, runtime_rebuilt=False,
                  linker_executed=False, guest_objects_compiled=False, guest_executed=False,
                  complete_kernel_link_qualified=False, full_runtime_behavior_qualified=False,
                  physical_phone_operations=False)
    try:
        run(args, report)
    except Exception as error:
        report['error'] = repr(error)
        report['traceback'] = traceback.format_exc()
    finally:
        report['controller_final'] = proc_memory(os.getpid())
        dump(args.out / 'report.json', report)
    print(json.dumps(dict(outcome=report['outcome'], report=str(args.out / 'report.json'), error=report.get('error'))))
    return 0 if report['outcome'] == 'pass' else 1


if __name__ == '__main__':
    sys.exit(main())
