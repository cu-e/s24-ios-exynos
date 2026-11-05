#!/usr/bin/env python3
"""Prepare genuine pthread sources and a guest component plan; never compile."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / 'fixtures/public/avf-guest-pthread/source-policy.json'
EXECUTION_FREEZE = ROOT / 'fixtures/public/avf-guest-pthread/execution-plan-freeze.json'


def digest(path, algorithm='sha256', blob=False):
    h = hashlib.new(algorithm)
    if blob:
        h.update(('blob ' + str(path.stat().st_size) + '\0').encode())
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def load(path):
    with path.open() as stream:
        return json.load(stream)


def dump(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def require_hash(path, expected):
    if path.is_symlink() or not path.is_file() or digest(path) != expected:
        raise ValueError('Missing or changed pinned file: ' + str(path))


def fields(text):
    """Read declarations, without claiming preprocessed layout or ABI equality."""
    text = re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S)
    text = re.sub(r'^\s*#.*$', '', text, flags=re.M)
    result = {}
    for name in ['pthread_functions_s', 'pthread_callbacks_s']:
        match = re.search(r'typedef\s+const\s+struct\s+' + name + r'\s*\{(.*?)\}\s*\*\s*\w+\s*;', text, re.S)
        if match is None:
            raise ValueError('Missing genuine callback record: ' + name)
        rows = []
        for declaration in match.group(1).split(';'):
            declaration = declaration.strip()
            if not declaration:
                continue
            pointer = re.search(r'\(\s*\*\s*(\w+)\s*\)', declaration)
            last = re.search(r'(\w+)\s*(?:\[\s*\d+\s*\])?\s*$', declaration)
            if not (pointer or last):
                raise ValueError('Unrecognized genuine declaration: ' + declaration)
            rows.append({'name': (pointer or last).group(1), 'declaration': re.sub(r'\s+', '', declaration)})
        result[name] = rows
    return result


def validate_preparation_plan(plan):
    """Check source preparation structure; this does not admit execution."""
    if plan['qualification'] != 'source-preparation-only' or plan['compiled_objects'] != []:
        raise ValueError('Source plan cannot claim compiled objects')
    if len(plan['translation_units']) != 3:
        raise ValueError('Exactly three real pthread translation units required')
    for row in plan['translation_units']:
        argv = row['argv_template']
        if '-DARM64_BOARD_CONFIG_BCM2837' not in argv or any('ARM64_BOARD_CONFIG_E1S' in a for a in argv):
            raise ValueError('Guest BCM2837 component profile required')
        if any('/EXPORT_HDRS/' in a for a in argv):
            raise ValueError('Raw internal header fallback forbidden for kext')
        if any(a.endswith('.a') for a in argv):
            raise ValueError('Historical archive input forbidden')
        if '-DXNU_NO_TYPE_BUILTINS=0' not in argv:
            raise ValueError('Actual metadata builtins remain enabled')


def validate_plan(plan):
    """Admit only the independently frozen complete source plan and argv templates."""
    validate_preparation_plan(plan)
    expected = load(EXECUTION_FREEZE)['canonical_plan_sha256']
    canonical = json.dumps(plan, sort_keys=True, separators=(',', ':'),
                           ensure_ascii=True, allow_nan=False).encode('utf-8')
    if hashlib.sha256(canonical).hexdigest() != expected:
        raise ValueError('Complete plan differs from the independently frozen guest pthread recipe')


class Preparation:
    def __init__(self, args):
        self.started = time.monotonic()
        self.main = args.main.resolve(strict=True)
        self.out = args.out.absolute()
        if self.out != self.out.resolve() or not self.out.is_relative_to(ROOT / 'artifacts/avf-guest-pthread'):
            raise ValueError('Output must be a fresh canonical owned pthread artifact directory')
        self.out.mkdir(parents=True, exist_ok=False)
        self.policy = load(POLICY)
        self.report = {'kind': 'host-test', 'origin': 'local-host', 'outcome': 'fail',
                       'recorded_at': datetime.now(timezone.utc).isoformat(), 'argv': sys.argv,
                       'python_executable': sys.executable,
                       'builder_sha256': digest(Path(__file__)), 'policy_sha256': digest(POLICY),
                       'commands': [], 'checks': [], 'compiled_objects': [], 'guest_executed': False,
                       'archive_qualified': False, 'callback_ABI_qualified': False,
                       'kernel_provider_closure_qualified': False, 'namespace_accepted_by_this_tool': False}
        self.report['host_tools'] = {}
        for name, path in [('git', Path(shutil.which('git')).resolve()),
                           ('python', Path(sys.executable).resolve())]:
            self.report['host_tools'][name] = {'path': str(path), 'sha256': digest(path)}

    def command(self, argv, cwd, label):
        """Only finite Git text/source preparation; compiler execution uses VM009 later."""
        if Path(str(argv[0])).name != 'git':
            raise ValueError('Preparation may execute Git only')
        env = dict(os.environ, GIT_NO_LAZY_FETCH='1', GIT_OPTIONAL_LOCKS='0',
                   GIT_TERMINAL_PROMPT='0', LC_ALL='C', PYTHONNOUSERSITE='1')
        started = time.monotonic()
        argv = [self.report['host_tools']['git']['path'], *argv[1:]]
        result = subprocess.run([str(a) for a in argv], cwd=cwd, env=env, capture_output=True, timeout=30)
        out, err = self.out / (label + '.stdout'), self.out / (label + '.stderr')
        out.write_bytes(result.stdout)
        err.write_bytes(result.stderr)
        self.report['commands'].append({'argv': [str(a) for a in argv], 'cwd': str(cwd),
                                       'exit_code': result.returncode, 'timeout_seconds': 30,
                                       'elapsed_seconds': time.monotonic() - started,
                                       'stdout': str(out), 'stdout_sha256': digest(out),
                                       'stderr': str(err), 'stderr_sha256': digest(err)})
        if result.returncode:
            raise ValueError('Git preparation failed: ' + label)
        return result.stdout.decode()

    def check(self, name, condition):
        self.report['checks'].append({'name': name, 'pass': bool(condition)})
        if not condition:
            raise ValueError(name)

    def git_file(self, repo, revision, relative):
        listing = self.command(['git', '-C', repo, 'ls-tree', revision, '--', relative], self.out,
                               'target-git-blob').strip().split()
        self.check('target-pinned-regular-Git-blob', len(listing) == 4 and listing[:2] == ['100644', 'blob'])
        source = repo / relative
        self.check('target-canonical-blob-SHA1', digest(source, 'sha1', blob=True) == listing[2])
        return {'git_blob_sha1': listing[2], 'sha256': digest(source)}

    def prepare(self):
        policy = self.policy
        handoff_path = self.main / policy['handoff_relative']
        require_hash(handoff_path, policy['handoff_sha256'])
        handoff = load(handoff_path)
        require_hash(Path(handoff['object_manifest']), policy['graph_sha256'])
        require_hash(Path(handoff['prepared']['path']), handoff['prepared']['sha256'])
        prepared = load(Path(handoff['prepared']['path']))
        headers_pin = handoff['parents']['headers']
        require_hash(Path(headers_pin['path']), headers_pin['sha256'])
        headers = load(Path(headers_pin['path']))
        require_hash(Path(headers['manifest']), headers['manifest_sha256'])
        header_rows = load(Path(headers['manifest']))
        for row in header_rows:
            if row['status'] == 'installed':
                require_hash(Path(row['output']), row['output_sha256'])
        self.check('all-genuine-guest-installed-headers-revalidated', sum(r['status'] == 'installed' for r in header_rows) == 1869)
        self.report['parents'] = {'handoff': {'path': str(handoff_path), 'sha256': digest(handoff_path)},
                                  'prepared': handoff['prepared'], 'headers': headers_pin}
        kernel = Path(prepared['kernel_root'])
        source_root = self.out / 'source/pthread'
        repo = self.main / 'references/xnu-kernel-pthread'
        entries = self.command(['git', '-C', repo, 'ls-tree', '-rz', policy['pthread_revision']], self.out, 'pthread-pinned-tree')
        source_rows = []
        for entry in entries.split('\0'):
            if not entry:
                continue
            info, name = entry.split('\t', 1)
            mode, kind, blob = info.split()
            self.check('regular-tracked-source-' + name, mode in ['100644', '100755'] and kind == 'blob')
            source = repo / name
            self.check('canonical-source-blob-' + name, not source.is_symlink() and digest(source, 'sha1', blob=True) == blob)
            destination = source_root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            self.check('copied-source-identity-' + name, digest(destination) == digest(source))
            source_rows.append({'path': name, 'git_blob_sha1': blob, 'base_sha256': digest(source), 'copied_sha256': digest(destination)})
        self.command(['git', '-c', 'core.hooksPath=/dev/null', '-c', 'init.defaultBranch=source',
                      '-C', source_root, 'init', '--quiet'], self.out, 'pthread-isolated-repository')
        for relative, expected in policy['patches'].items():
            require_hash(self.main / relative, expected)
        for number in ['0002', '0003']:
            patch = next(self.main / p for p in policy['patches'] if Path(p).name.startswith(number))
            for check in [True, False]:
                self.command(['git', '-c', 'core.hooksPath=/dev/null', '-C', source_root, 'apply',
                              *(['--check'] if check else []), patch], self.out, number + ('-check' if check else '-apply'))
        for name, expected in policy['expected_patched_pthread'].items():
            require_hash(source_root / name, expected)
        for row in source_rows:
            row['prepared_sha256'] = digest(source_root / row['path'])
        dump(self.out / 'source-manifest.json', source_rows)
        target_relative = 'src/Libraries/AvailabilityVersions/include/TargetConditionals.h'
        target_repo = self.main / 'references/puredarwin-build-inputs'
        target_pin = self.git_file(target_repo, policy['target_revision'], target_relative)
        target_tree = self.out / 'source/public-target'
        target_out = target_tree / target_relative
        target_out.parent.mkdir(parents=True)
        shutil.copyfile(target_repo / target_relative, target_out)
        self.command(['git', '-c', 'core.hooksPath=/dev/null', '-c', 'init.defaultBranch=source',
                      '-C', target_tree, 'init', '--quiet'], self.out, 'target-isolated-repository')
        target_patch = next(self.main / p for p in policy['patches'] if Path(p).name.startswith('0001'))
        for check in [True, False]:
            self.command(['git', '-C', target_tree, 'apply', *(['--check'] if check else []), target_patch], self.out,
                         'target-' + ('check' if check else 'apply'))
        require_hash(target_out, policy['expected_target_sha256'])
        public = self.out / 'public-headers'
        public.mkdir()
        shutil.copyfile(target_out, public / 'TargetConditionals.h')
        supplement = {}
        for name in ['Availability.h', 'AvailabilityInternal.h', 'AvailabilityMacros.h']:
            relative = 'EXTERNAL_HEADERS/' + name
            source = kernel / relative
            require_hash(source, prepared['prepared_source_files'][relative])
            shutil.copyfile(source, public / name)
            supplement[name] = {'source': str(source), 'sha256': digest(source)}
        raw_callbacks = kernel / 'bsd/sys/pthread_shims.h'
        require_hash(raw_callbacks, prepared['prepared_source_files']['bsd/sys/pthread_shims.h'])
        installed_callbacks = Path(headers['roots']['private']) / 'sys/pthread_shims.h'
        declaration_rows = fields(raw_callbacks.read_text())
        self.check('raw-and-installed-callback-declarations-match', declaration_rows == fields(installed_callbacks.read_text()))
        aliases = {}
        alias_inputs = []
        for name in ['Private.exports', 'Private.arm64.exports']:
            relative = 'config/' + name
            path = kernel / relative
            require_hash(path, prepared['prepared_source_files'][relative])
            alias_inputs.append({'path': str(path), 'sha256': digest(path)})
            for line in path.read_text().splitlines():
                pair = line.strip().split(':')
                if len(pair) == 2 and pair[0] in policy['native_aliases']:
                    aliases[pair[0]] = pair[1]
        self.check('all-three-genuine-native-VM-alias-declarations', aliases == policy['native_aliases'])
        witness = {'callback_declarations': declaration_rows, 'source': str(raw_callbacks),
                   'source_sha256': digest(raw_callbacks), 'installed': str(installed_callbacks),
                   'installed_sha256': digest(installed_callbacks), 'aliases': aliases, 'alias_inputs': alias_inputs,
                   'declarations_only': True, 'compiled_ABI_or_provider_closure_qualified': False}
        dump(self.out / 'callback-alias-source-witness.json', witness)
        native = (source_root / 'xcodescripts/kext.xcconfig').read_text()
        common = re.search(r'^GCC_PREPROCESSOR_DEFINITIONS_kext = (.+)$', native, re.M).group(1).split()
        development = re.search(r'^GCC_PREPROCESSOR_DEFINITIONS_kext_development = (.+)$', native, re.M).group(1).split()
        compiler = prepared['compiler']
        require_hash(Path(compiler['path']), compiler['sha256'])
        includes = [source_root / 'private', source_root / 'include', source_root,
                    Path(headers['roots']['private']), Path(headers['roots']['public']), public]
        flags = ['-target', 'arm64-apple-ios16.5', '-mkernel', '-nostdinc', '-fno-builtin', '-fno-common',
                 '-Os', '-std=gnu11', '-DKERNEL=1', '-DKERNEL_PRIVATE=1', '-DPRIVATE=1',
                 '-DARM64_BOARD_CONFIG_BCM2837', '-D__DARWIN_64_BIT_INO_T=1', '-DXNU_TARGET_OS_IOS=1',
                 '-DXNU_NO_TYPE_BUILTINS=0', '-Dpthread_kern=pthread_kext_kern',
                 '-Dcurrent_uthread=pthread_kext_current_uthread', '-Werror=implicit-function-declaration',
                 '-Werror=incompatible-pointer-types', *['-D' + d for d in common + development],
                 *[a for p in includes for a in ['-I', str(p)]]]
        plan = {'schema_version': 1, 'task': 'VM-021', 'qualification': 'source-preparation-only',
                'compiled_objects': [], 'pthread_revision': policy['pthread_revision'], 'compiler': compiler,
                'headers': headers_pin, 'source_manifest_sha256': digest(self.out / 'source-manifest.json'),
                'target_public_header': target_pin, 'availability_supplements': supplement,
                'source_patches': policy['patches'], 'variant': 'development', 'native_development_LTO': False,
                'namespace_remaps': {'pthread_kern': 'pthread_kext_kern', 'current_uthread': 'pthread_kext_current_uthread'},
                'native_definitions': common + development, 'translation_units': [],
                'execution_requires': ['independent accepted VM008 namespace', 'accepted VM009 process API',
                                       'explicit root resource lease', 'registered fresh compile experiment'],
                'archive': {'name': 'libpthread_kext.a', 'members': ['kern_init.o', 'kern_support.o', 'kern_synch.o'],
                            'produced': False, 'defined_symbols': None, 'undefined_symbols': None},
                'callback_alias_witness_sha256': digest(self.out / 'callback-alias-source-witness.json')}
        for name in policy['required_sources']:
            source = source_root / name
            stem = source.stem
            plan['translation_units'].append({'source': str(source), 'source_sha256': digest(source),
                                             'argv_template': [compiler['path'], *flags, '-MD', '-MF',
                                                               '@OWNED_OUT@/' + stem + '.d', '-c', str(source),
                                                               '-o', '@OWNED_OUT@/' + stem + '.o']})
        validate_preparation_plan(plan)
        dump(self.out / 'component-plan.json', plan)
        self.report['source_file_count'] = len(source_rows)
        self.report['callback_declaration_counts'] = {k: len(v) for k, v in declaration_rows.items()}
        self.report['qualification'] = 'source-preparation-only'
        self.report['outcome'] = 'pass'

    def finish(self):
        status = Path('/proc/self/status').read_text()
        self.report['current_process_VmHWM_KiB'] = int(re.search(r'^VmHWM:\s+(\d+)', status, re.M).group(1))
        self.report['elapsed_seconds'] = time.monotonic() - self.started
        self.report['finished_at'] = datetime.now(timezone.utc).isoformat()
        self.report['controller_exit_code'] = 0 if self.report['outcome'] == 'pass' else 1
        self.report['child_RSS_sampled'] = False
        self.report['outputs'] = {str(p): digest(p) for p in self.out.rglob('*') if p.is_file() and p.name != 'evidence.json'}
        dump(self.out / 'evidence.json', self.report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--main', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    run = Preparation(args)
    try:
        run.prepare()
    except Exception as error:
        run.report['error'] = type(error).__name__ + ': ' + str(error)
        print(run.report['error'], file=sys.stderr)
    finally:
        run.finish()
    return 0 if run.report['outcome'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
