#!/usr/bin/env python3
"""Prepare pinned firehose exports and guest recipes without running a compiler."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
NAMESPACE = 'worktrees/vm-008-20261105/artifacts/avf-kernel-headers'
MANIFEST = NAMESPACE + '/handoff-1/next-full-object-manifest.json'
MANIFEST_SHA256 = 'afc5cd206965de7e36a0aa17c4eb86a1f305689f386ccb22c55bd983567dd1dd'
# SHA256 of the complete selected 261-token VM008 argv JSON, compact ASCII.
# This is the source template; output substitutions happen only after admission.
GUEST_ARGV_SHA256 = 'cf737937e6e6c74f00302f2bebcc1ec6a08329fb48ab35b451dd226f590113ca'
REVISION = 'a641558f447659d90ad002ef0ee6f0212273fbfc'
EXPORT_FLAGS = ['-DKERNEL=1', '-DOS_FIREHOSE_SPI=1',
                '-DOS_VOUCHER_ACTIVITY_SPI_TYPES=1', '-UOS_VOUCHER_ACTIVITY_SPI']
BACKEND_FLAGS = ['-DDISPATCH_USE_DTRACE=0', '-DOS_ATOMIC_CONFIG_MEMORY_ORDER_DEPENDENCY=1',
                 '-DOS_ATOMIC_CONFIG_STARVATION_FREE_ONLY=0']


def digest(path, algorithm='sha256', git_blob=False):
    path = Path(path)
    h = hashlib.new(algorithm)
    if git_blob:
        h.update(('blob ' + str(path.stat().st_size) + '\0').encode())
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def bound(path):
    path = Path(path)
    return dict(path=str(path), sha256=digest(path), size_bytes=path.stat().st_size)


def validate_guest_row(row, main, compiler):
    argv = row['next_owned_compile_argv_template']
    frozen = json.dumps(argv, ensure_ascii=True, separators=(',', ':')).encode('ascii')
    if hashlib.sha256(frozen).hexdigest() != GUEST_ARGV_SHA256:
        raise ValueError('Complete frozen guest argv changed; extra, removed, reordered or overriding flags are forbidden')
    if (row['id'] != 'bsd/subr_log.o' or row['language'] != 'c' or
            argv[0] != str(compiler) or argv.count(row['bound_source']) != 1 or
            '-DARM64_BOARD_CONFIG_BCM2837' not in argv or
            '-DCURRENT_MACHINE_CONFIG_LC=bcm2837' not in argv or
            '-DDEVELOPMENT' not in argv or '-DXNU_NO_TYPE_BUILTINS=0' not in argv):
        raise ValueError('Guest source, compiler, board, configuration or allocator recipe changed')
    if any('E1S' in a or 'e1s-dependency' in a or 'xnu-kernel-objects/compile' in a for a in argv):
        raise ValueError('Native recipe or object namespace is forbidden')
    namespace = str(main / NAMESPACE) + '/'
    for field in ['bound_source', 'configuration', 'cwd']:
        if not row[field].startswith(namespace):
            raise ValueError('Guest input escaped the immutable VM008 namespace')
    for field in ['bound_source', 'configuration']:
        if digest(row[field]) != row[field + '_sha256']:
            raise ValueError('Guest bound input changed: ' + field)
    if argv[argv.index('-o') + 1] != '@NEXT_OBJECT_DIR@/bsd/subr_log.o':
        raise ValueError('Guest output template changed')
    if argv[argv.index('-MF') + 1] != '@NEXT_DEPENDENCY_DIR@/bsd/subr_log.o.d':
        raise ValueError('Guest dependency template changed')


def controls(row, main, compiler):
    results = []
    for name, mutate in [
        ('reject-native-board', lambda r: r['next_owned_compile_argv_template'].append('-DARM64_BOARD_CONFIG_E1S')),
        ('reject-source-mutation', lambda r: r.update(bound_source_sha256='0' * 64)),
        ('reject-old-namespace', lambda r: r.update(cwd=str(main / 'artifacts/xnu-kernel-objects/compile-session2'))),
        ('reject-shared-output', lambda r: r['next_owned_compile_argv_template'].__setitem__(r['next_owned_compile_argv_template'].index('-o') + 1, '/tmp/unowned.o')),
    ]:
        changed = copy.deepcopy(row)
        mutate(changed)
        try:
            validate_guest_row(changed, main, compiler)
        except ValueError as error:
            results.append(dict(name=name, rejected=True, diagnostic=str(error)))
        else:
            raise ValueError('Negative control was accepted: ' + name)
    return results


def prepare(args):
    main = args.main.resolve()
    out = args.output.absolute()
    # The task owns only this documentation directory for maintained output.
    allowed = ROOT / 'docs/procedures/avf-guest-firehose'
    if not out.is_relative_to(allowed) or out.resolve() != out:
        raise ValueError('Output must be a fresh canonical owned procedure subdirectory')
    out.mkdir(parents=True, exist_ok=False)
    report = dict(kind='host-test', origin='local-host', task='VM-020',
                  recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                  outcome='fail', commands=[], compiled=False, archive_created=False,
                  guest_executed=False, device_executed=False, sdk_used=False,
                  guest_layout_measured=False, accepted_for_execution=False,
                  builder=bound(__file__), argv=sys.argv)
    env = dict(os.environ, GIT_NO_LAZY_FETCH='1', GIT_OPTIONAL_LOCKS='0',
               LC_ALL='C', PYTHONUTF8='1', PYTHONNOUSERSITE='1')

    def run(argv, name, accepted=(0,)):
        start = time.monotonic()
        p = subprocess.run([str(x) for x in argv], capture_output=True, env=env, timeout=30)
        stdout, stderr = out / (name + '.stdout.txt'), out / (name + '.stderr.txt')
        stdout.write_bytes(p.stdout)
        stderr.write_bytes(p.stderr)
        report['commands'].append(dict(argv=[str(x) for x in argv], cwd=os.getcwd(),
            exit_code=p.returncode, elapsed_seconds=round(time.monotonic() - start, 3),
            stdout=bound(stdout), stderr=bound(stderr)))
        if p.returncode not in accepted:
            raise ValueError('Command failed: ' + name)
        return p.stdout.decode()

    try:
        pins = json.loads((ROOT / 'fixtures/public/avf-guest-firehose/inputs.json').read_text())
        source = main / 'references/xnu-kernel-firehose'
        revision = run(['git', '-C', source, 'rev-parse', 'HEAD'], 'source-revision').strip()
        if revision != REVISION:
            raise ValueError('Pinned firehose revision changed')
        report['source_revision'] = revision
        report['source_files'] = []
        listing = run(['git', '-C', source, 'ls-tree', REVISION, '--', *pins['source_sha256']], 'source-tree')
        blobs = {line.split('\t', 1)[1]: line.split()[2] for line in listing.splitlines()}
        for name, expected in pins['source_sha256'].items():
            p = source / name
            actual = digest(p)
            blob = digest(p, 'sha1', git_blob=True)
            if actual != expected or blobs.get(name) != blob:
                raise ValueError('Pinned source bytes differ from Git blob: ' + name)
            report['source_files'].append(dict(**bound(p), git_blob_sha1=blob))
        manifest = main / MANIFEST
        if digest(manifest) != MANIFEST_SHA256:
            raise ValueError('Immutable guest object manifest changed')
        report['guest_manifest'] = bound(manifest)
        rows = json.loads(manifest.read_text())
        if len(rows) != 1080 or len({r['id'] for r in rows}) != 1080:
            raise ValueError('Guest graph cardinality changed')
        row = next(r for r in rows if r['id'] == 'bsd/subr_log.o')
        compiler = main / pins['compiler']['path']
        for tool in [pins['compiler'], pins['unifdef']]:
            if digest(main / tool['path']) != tool['sha256']:
                raise ValueError('Pinned source-built tool changed: ' + tool['path'])
        report['tools'] = [bound(main / pins[k]['path']) for k in ['compiler', 'unifdef']]
        validate_guest_row(row, main, compiler)
        report['controls'] = controls(row, main, compiler)
        kernel = main / NAMESPACE / 'prepare-2/source/xnu'
        board = kernel / 'pexpert/pexpert/arm64/board_config.h'
        board_text = board.read_text().split('#ifdef ARM64_BOARD_CONFIG_BCM2837', 1)[1].split('#endif', 1)[0]
        macros = {name: int(re.search(r'^#define\s+' + name + r'\s+(\d+)', board_text, re.M)[1])
                  for name in ['MAX_CPUS', 'MAX_CPU_CLUSTERS']}
        if macros != dict(MAX_CPUS=8, MAX_CPU_CLUSTERS=1):
            raise ValueError('Guest board CPU limits changed')
        report['guest_board_source'] = dict(**bound(board), selected_text_macros=macros,
                                          compiled_layout_measured=False)
        config = (source / 'xcodeconfig/libfirehose_kernel.xcconfig').read_text()
        flags = shlex.split(re.search(r'^COPY_HEADERS_UNIFDEF_FLAGS = (.+)$', config, re.M)[1])
        definitions = re.search(r'^GCC_PREPROCESSOR_DEFINITIONS = (.+)$', config, re.M)[1].split()
        if flags != EXPORT_FLAGS or any(flag[2:] not in definitions for flag in BACKEND_FLAGS):
            raise ValueError('Genuine kernel export/backend configuration changed')
        project = (source / 'libdispatch.xcodeproj/project.pbxproj').read_text()
        phase = project.split('6E040C611C499B1B00411A2E /* Headers */ = {', 1)[1].split('\n\t\t};', 1)[0]
        if re.findall(r'/\* (\S+ in Headers) \*/', phase) != ['firehose_buffer_private.h in Headers']:
            raise ValueError('Genuine kernel exported-header selection changed')
        header_root = out / 'export/include/kernel'
        header = header_root / 'os/firehose_buffer_private.h'
        header.parent.mkdir(parents=True)
        run([main / pins['unifdef']['path'], *flags, '-o', header,
             source / 'os/firehose_buffer_private.h'], 'export-kernel-header', (0, 1))
        if digest(header) != pins['exported_header_sha256']:
            raise ValueError('Fresh genuine header export changed')
        report['header_export'] = dict(**bound(header), flags=flags, genuinely_regenerated=True)
        snapshots = out / 'probe-inputs'
        snapshots.mkdir()
        report['probe_inputs'] = []
        for filename in ['provider-layout.c', 'interface-contract.c']:
            original = ROOT / 'fixtures/public/avf-guest-firehose' / filename
            snapshot = snapshots / filename
            shutil.copyfile(original, snapshot)
            report['probe_inputs'].append(dict(original=bound(original), snapshot=bound(snapshot)))
        plans = []
        for name, actual_source in [('provider', source / 'src/firehose/firehose_buffer.c'),
                ('provider-layout', snapshots / 'provider-layout.c'),
                ('interface', snapshots / 'interface-contract.c')]:
            argv = row['next_owned_compile_argv_template'].copy()
            argv[argv.index(row['bound_source'])] = str(actual_source)
            argv[argv.index('-o') + 1] = '@OWNED_OUTPUT@/' + name + '.o'
            argv[argv.index('-MF') + 1] = '@OWNED_OUTPUT@/' + name + '.d'
            argv[1:1] = ['-I', str(header_root), '-I', str(source / 'src/firehose'),
                         '-I', str(kernel / 'libkern/firehose'), *BACKEND_FLAGS]
            # Source include roots remain within the same new guest namespace.
            for part in ['osfmk', 'bsd', 'libkern', 'iokit', 'pexpert', 'libsa', 'security', 'san', 'osfmk/libsa']:
                argv.extend(['-I', str(kernel / part)])
            plans.append(dict(id='firehose/' + name, argv_template=argv, cwd=row['cwd'],
                source=bound(actual_source), configuration=bound(row['configuration']),
                compiler=bound(compiler), execution_requires_new_plan_and_resource_lease=True))
        dump(out / 'compile-plan.json', dict(schema_version=1, task='VM-020',
             status='source_preparation_only_not_qualified', recipes=plans,
             guest_manifest=report['guest_manifest'], header_export=report['header_export'],
             archive_policy='Archive only provider.o; exclude layout and interface probes',
             required_gates=['VM008 independent acceptance', 'root resource admission',
                             'VM009 executor plan/admission and tool-runtime verification']))
        report['plan'] = bound(out / 'compile-plan.json')
        report['outcome'] = 'pass'
        report['summary'] = 'Pinned source and genuine fresh header export verified; three new guest recipes prepared without compilation'
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        report['proc_status'] = [line.strip() for line in Path('/proc/self/status').read_text().splitlines()
                                 if line.startswith(('VmRSS:', 'VmHWM:'))]
        report['limits'] = ['No compiler, archive, guest layout, full link, QEMU or native measurement',
                            'Compile plans require common executor adaptation and independent acceptance before execution']
        dump(out / 'evidence.json', report)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--main', type=Path, required=True, help='Canonical primary checkout; read-only inputs')
    parser.add_argument('--output', type=Path, required=True, help='Fresh owned procedure subdirectory')
    args = parser.parse_args()
    return prepare(args)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
