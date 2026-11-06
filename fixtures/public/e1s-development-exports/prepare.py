#!/usr/bin/env python3
"""Query genuine native export declarations and copy their raw source bytes only."""
import argparse
from collections import deque
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shlex
import shutil
import subprocess
import time

OWNER = 'codex-e1s-development-exports-20261106-sr11'
KEYS = ['COMPONENT', 'EXPDIR', 'EXPINC_SUBDIRS', 'EXPINC_SUBDIRS_ARM64',
        'EXPORT_MI_LIST', 'EXPORT_MI_DIR', 'EXPORT_MD_LIST', 'EXPORT_MD_DIR',
        'EXPORT_MI_GEN_LIST', 'EXPORT_MD_GEN_LIST', 'COMP_SUBDIRS', 'COMP_FILES',
        'MIGFLAGS', 'MIGKUFLAGS', 'MIGKSFLAGS', 'MIG_UUHDRS', 'MIG_USHDRS',
        'MIG_KUHDRS', 'MIG_KSHDRS', 'MIG_KUSRC', 'MIG_KSSRC', 'DEVICE_FILES']


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + '\n')


def below(root, relative):
    rel = Path(relative)
    if rel.is_absolute() or '..' in rel.parts:
        raise ValueError('Escaped relative namespace: ' + relative)
    path = root / rel
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Escaped physical namespace: ' + relative)
    return path


class Preparation:
    def __init__(self, main, out):
        self.main = main.resolve()
        self.out = out.absolute()
        if self.out != self.out.resolve() or self.out.exists():
            raise ValueError('Use an absent canonical owned output')
        owned = Path(__file__).resolve().parents[3]
        if not self.out.is_relative_to(owned / 'artifacts/e1s-development-exports'):
            raise ValueError('Output must remain inside the owning worktree artifact root')
        self.inputs = {}
        self.commands = []
        self.cache = {}
        self.rows = []
        self.by_output = {}
        self.source_files = {}

    def pin(self, path, expected=None):
        path = Path(path)
        if path.is_symlink() or not path.is_file():
            raise ValueError('Expected ordinary file: ' + str(path))
        digest = sha(path)
        if expected is not None and digest != expected:
            raise ValueError('Changed input: ' + str(path))
        if self.inputs.setdefault(str(path), digest) != digest:
            raise ValueError('Input changed during preparation: ' + str(path))
        return digest

    def source_pin(self, path):
        path = Path(path)
        rel = str(path.relative_to(self.source))
        return self.pin(path, self.manifest[rel])

    def load(self):
        descriptor = self.main / 'fixtures/public/e1s-development-configs/generated-development.json'
        self.pin(descriptor, '6b0ac2c8e82b2837a94f628ee5c291105559a0607e3febac56fc7e7b6527cf9a')
        self.parent = json.loads(descriptor.read_text())
        if tuple(self.parent[k] for k in ['machine', 'architecture', 'kernel', 'platform']) != ('E1S', 'ARM64', 'DEVELOPMENT', 'iPhoneOS'):
            raise ValueError('Wrong native configuration selection')
        self.source = Path(self.parent['source_root'])
        manifest = self.source.parent / 'prepared-source-manifest.json'
        self.pin(manifest, 'f884bf7fa08afdffd2f4ba0840ae44d666f1b9848700aaa8f5f88e4dcbe42ba2')
        self.manifest = json.loads(manifest.read_text())
        self.pin(self.source.parent / 'e1s-profile.json', self.parent['source_profile_sha256'])
        self.pin(Path(__file__))
        self.out.mkdir(parents=True)
        self.configs = {}
        for component, data in self.parent['components'].items():
            target = self.out / 'configuration' / component / 'DEVELOPMENT'
            target.mkdir(parents=True)
            for name, digest in data['generated_files'].items():
                original = below(Path(data['root']), name)
                self.pin(original, digest)
                copied = below(target, name)
                copied.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(original, copied)
                self.pin(copied, digest)
            self.configs[component] = target
            self.pin(target / 'Makefile', data['makefile_sha256'])
            actual = re.findall(r'^export CONFIG_DEFINES = (.*)$', (target / 'Makefile').read_text(), re.M)
            if len(actual) != 1 or '-DDEVELOPMENT' not in shlex.split(actual[0]):
                raise ValueError('Missing actual DEVELOPMENT flags')
        if set(self.configs) != {'osfmk', 'bsd', 'libkern', 'iokit', 'pexpert', 'libsa', 'security', 'san'}:
            raise ValueError('Incomplete eight-component context')
        oldshim = self.main / 'artifacts/xnu-kernel-objects/compile-session2/host-commands.mk'
        expected = '# Explicit standalone Linux query inputs; no SDK contents.\nTR = tr\nBASH = bash\nECHO = echo\nPRINTF = printf\nSUPPORTED_EMBEDDED_PLATFORMS = iPhoneOS AppleTVOS WatchOS tvOS BridgeOS\n_v =\n'
        if oldshim.read_text() != expected:
            raise ValueError('Historical native Linux query shim changed')
        self.pin(oldshim)
        self.shim = self.out / 'host-commands.mk'
        self.shim.write_text(expected)
        self.pin(self.shim)
        self.compiler = self.main / 'artifacts/xnu-compiler-cxx-storage/source-build-session2/clang'
        self.pin(self.compiler, '7972eb2820ae25b5bedff1ea954cef9e9a0e4a15c7a8e440628e8b6540fafc82')
        for command in ['/usr/bin/make', '/bin/bash', '/usr/bin/tr']:
            self.pin(Path(command).resolve())
        self.host = self.main / 'artifacts/xnu-host-tools/generators-session2/prefix/bin'
        # BOUND_CHECKS is query-only, avoiding MakeInc.def's parse-time CC probe.
        # Both values are queried below; no compiler feature/capability is inferred.
        self.query_context = {'BOUND_CHECKS': 'explicit query-only 0 and 1; selections must match',
                              'compiler_or_generator_execution': False,
                              'CFLAGS_or_compiler_capability_qualified': False}

    def query(self, component, directory):
        key = (component, str(directory))
        if key in self.cache:
            return self.cache[key]
        relative = directory.relative_to(self.source)
        self.source_pin(directory / 'Makefile')
        makefile = self.configs[component] / 'Makefile' if directory == self.source / component else directory / 'Makefile'
        if makefile.is_relative_to(self.source):
            self.source_pin(makefile)
        else:
            self.pin(makefile)
        cwd = self.out / 'query-build' / relative
        cwd.mkdir(parents=True, exist_ok=True)
        query = self.out / 'queries' / (str(relative).replace('/', '-') + '.mk')
        query.parent.mkdir(exist_ok=True)
        query.write_text('include ' + str(makefile) + '\n' + ''.join('$(info E1SEXPORT|' + k + '|$(' + k + '))\n' for k in KEYS) +
                         '$(info E1SMAKEFILES|$(MAKEFILE_LIST))\n.PHONY: e1s_exports_query\ne1s_exports_query: ;\n')
        self.pin(query)
        defines = re.findall(r'^export CONFIG_DEFINES = (.*)$', (self.configs[component] / 'Makefile').read_text(), re.M)[0]
        args = ['SRCROOT=' + str(self.source), 'OBJROOT=' + str(self.out), 'OBJPATH=' + str(self.out / 'build'),
                'TARGET=' + str(cwd), 'SOURCE=' + str(directory) + '/', 'RELATIVE_SOURCE_PATH=./' + str(relative),
                'CURRENT_ARCH_CONFIG=ARM64', 'CURRENT_ARCH_CONFIG_LC=arm64',
                'CURRENT_KERNEL_CONFIG=DEVELOPMENT', 'CURRENT_KERNEL_CONFIG_LC=development',
                'CURRENT_MACHINE_CONFIG=E1S', 'CURRENT_MACHINE_CONFIG_LC=e1s', 'PLATFORM=iPhoneOS',
                'SDKROOT=' + str(self.out / 'unavailable-sdk'), 'CC=' + str(self.compiler), 'CXX=' + str(self.compiler),
                'MIG=' + str(self.host / 'mig'), 'MIGCOM=' + str(self.host / 'migcom'), 'MIGCC=' + str(self.compiler),
                'MakeInc_cmd=' + str(self.shim), 'MakeInc_def=' + str(self.source / 'makedefs/MakeInc.def'),
                'MakeInc_rule=' + str(self.source / 'makedefs/MakeInc.rule'), 'MakeInc_dir=' + str(self.source / 'makedefs/MakeInc.dir'),
                'ARCH_STRING_FOR_CURRENT_MACHINE_CONFIG=arm64', 'BUILD_WERROR=0', 'BUILD_LTO=0',
                'DEPLOYMENT_TARGET_FLAGS=-target arm64-apple-ios16.5 -DXNU_TARGET_OS_IOS',
                'SEED_DEFINES=-DXNU_NO_TYPE_BUILTINS=0', 'CONFIG_DEFINES=' + defines, 'SHELL=/bin/bash', 'LOGCOLORS=n']
        alternatives = []
        for bounds in [0, 1]:
            argv = ['/usr/bin/make', '--no-print-directory', '-rR', '-f', str(query), *args,
                    'BOUND_CHECKS=' + str(bounds), 'e1s_exports_query']
            env = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'}
            before = time.monotonic()
            p = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=20)
            label = str(relative).replace('/', '-') + '-bounds' + str(bounds)
            (self.out / 'queries' / (label + '.stdout.txt')).write_text(p.stdout)
            (self.out / 'queries' / (label + '.stderr.txt')).write_text(p.stderr)
            self.commands.append({'argv': argv, 'cwd': str(cwd), 'env': env, 'exit_code': p.returncode,
                                  'wall_seconds': time.monotonic() - before, 'target_tool_executed': False})
            if p.returncode or p.stderr.strip():
                raise ValueError('Read-only Make query failed: ' + label + ': ' + p.stderr[-2000:])
            values = {a[1]: a[2] for line in p.stdout.splitlines() if line.startswith('E1SEXPORT|') and len(a := line.split('|', 2)) == 3}
            if set(values) != set(KEYS) or values['COMPONENT'] != component or values['EXPDIR'] != 'EXPORT_HDRS/' + component:
                raise ValueError('Wrong query component or incomplete native selection: ' + label)
            includes = [line.split('|', 1)[1] for line in p.stdout.splitlines() if line.startswith('E1SMAKEFILES|')]
            if len(includes) != 1:
                raise ValueError('Missing actual Make include provenance')
            for name in includes[0].split():
                included = Path(name) if Path(name).is_absolute() else cwd / name
                if included.is_relative_to(self.source):
                    self.source_pin(included)
                elif str(included) not in self.inputs:
                    raise ValueError('Unqualified Make include: ' + name)
            alternatives.append(values)
        if alternatives[0] != alternatives[1]:
            raise ValueError('Export/MIG selections depend on query-only bounds setting')
        self.cache[key] = alternatives[0]
        return alternatives[0]

    def export_row(self, component, directory, mode, values, name, generated):
        destdir = values['EXPORT_' + mode + '_DIR']
        destination = str(Path('EXPORT_HDRS') / component / Path(destdir) / name)
        output = below(self.out, destination)
        row = {'component': component, 'mode': mode, 'directory': str(directory.relative_to(self.source)),
               'list': 'EXPORT_' + mode + ('_GEN_LIST' if generated else '_LIST'),
               'destination': destination, 'name': name, 'generated': generated,
               'declaration': str((directory / 'Makefile').relative_to(self.source)),
               'query_makefile': str(self.configs[component] / 'Makefile') if directory == self.source / component else str(directory / 'Makefile')}
        if generated:
            row['status'] = 'requires_actual_generated_producer'
        else:
            original = below(directory, name)
            row.update(source=str(original.relative_to(self.source)), sha256=self.source_pin(original), status='raw_source_exported')
            if output.exists() and sha(output) != row['sha256']:
                raise ValueError('Conflicting raw exports: ' + destination)
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, output)
            if sha(output) != row['sha256']:
                raise ValueError('Raw export copy mismatch')
            self.source_files[destination] = row['sha256']
        old = self.by_output.setdefault(destination, row)
        if old['generated'] != row['generated'] or (not generated and old['sha256'] != row['sha256']):
            raise ValueError('Raw/generated or content export collision: ' + destination)
        self.rows.append(row)

    def exports(self):
        visits = []
        for mode in ['MI', 'MD']:
            pending = deque((component, self.source / component) for component in self.configs)
            seen = set()
            while pending:
                component, directory = pending.popleft()
                if (component, directory) in seen:
                    continue
                seen.add((component, directory))
                values = self.query(component, directory)
                traversal = 'EXPINC_SUBDIRS' if mode == 'MI' else 'EXPINC_SUBDIRS_ARM64'
                visits.append({'component': component, 'mode': mode, 'directory': str(directory.relative_to(self.source)),
                               'recursion_variable': traversal, 'children': values[traversal].split()})
                for child in values[traversal].split():
                    childpath = below(directory, child)
                    if not childpath.is_relative_to(self.source / component):
                        raise ValueError('Export recursion escaped component')
                    pending.append((component, childpath))
                for generated in [False, True]:
                    key = 'EXPORT_' + mode + ('_GEN_LIST' if generated else '_LIST')
                    for name in values[key].split():
                        self.export_row(component, directory, mode, values, name, generated)
        write(self.out / 'traversal.json', visits)
        write(self.out / 'source-export-manifest.json', self.rows)

    def mig_prerequisites(self):
        root = self.query('osfmk', self.source / 'osfmk')
        rows = []
        for child in root['COMP_SUBDIRS'].split():
            directory = below(self.source / 'osfmk', child)
            values = self.query('osfmk', directory)
            selected = {key: values[key] for key in KEYS if key.startswith('MIG') or key in ['COMP_FILES', 'DEVICE_FILES']}
            if any(value for key, value in selected.items() if key.startswith('MIG')):
                rows.append({'directory': str(directory.relative_to(self.source)), 'selection': selected,
                             'internal_and_export_outputs_must_remain_separate': True, 'actual_generation': False})
        write(self.out / 'mig-prerequisites.json', rows)
        return rows

    def finish(self, mig):
        for path, digest in self.inputs.items():
            if sha(path) != digest:
                raise ValueError('Input changed before finalization: ' + path)
        generated = [row for row in self.rows if row['generated']]
        descriptor = {'schema': 'e1s-development-source-exports-v1', 'kind': 'host-test', 'origin': 'local-host',
                      'outcome': 'pass', 'task': 'STR-011', 'owner': OWNER,
                      'source_root': str(self.source), 'source_manifest_sha256': self.parent['source_manifest_sha256'],
                      'source_profile_sha256': self.parent['source_profile_sha256'],
                      'configuration_descriptor_sha256': '6b0ac2c8e82b2837a94f628ee5c291105559a0607e3febac56fc7e7b6527cf9a',
                      'machine': 'E1S', 'architecture': 'ARM64', 'kernel': 'DEVELOPMENT', 'platform': 'iPhoneOS',
                      'raw_export_root': str(self.out / 'EXPORT_HDRS'), 'raw_export_files': self.source_files,
                      'raw_export_count': len(self.source_files), 'generated_required': generated,
                      'query_context': self.query_context, 'query_directories': len(self.cache),
                      'configuration_roots': {k: str(v) for k, v in self.configs.items()},
                      'mig_prerequisites': str(self.out / 'mig-prerequisites.json'), 'mig_directory_count': len(mig),
                      'generated_producers_imported': False, 'coherent_full_header_route_complete': False,
                      'SDK_or_private37_ABI_or_full_kernel_or_hardware_qualified': False}
        write(self.out / 'generated-development.json', descriptor)
        write(self.out / 'input-bindings.json', self.inputs)
        write(self.out / 'commands.json', self.commands)
        write(self.out / 'preparation-result.json', {'outcome': 'pass', 'commands': len(self.commands),
              'raw_exports': len(self.source_files), 'generated_required': len(generated),
              'query_directories': len(self.cache), 'VmHWM_source': '/proc/self/status',
              'proc_status': [line for line in Path('/proc/self/status').read_text().splitlines() if line.startswith(('VmHWM:', 'VmRSS:'))]})
        return descriptor


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--main', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    a = parser.parse_args()
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024**2, 256 * 1024**2))
    available = int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))) * 1024
    if available < 4 * 1024**3:
        raise ValueError('Source-query admission requires at least 4 GiB MemAvailable')
    started = time.monotonic()
    p = Preparation(a.main, a.out)
    try:
        p.load()
        p.exports()
        mig = p.mig_prerequisites()
        result = p.finish(mig)
        print(json.dumps({'outcome': 'pass', 'raw_exports': result['raw_export_count'],
                          'descriptor_sha256': sha(p.out / 'generated-development.json'), 'wall_seconds': time.monotonic() - started}))
    except Exception as error:
        if p.out.exists():
            write(p.out / 'commands.json', p.commands)
            write(p.out / 'preparation-result.json', {'outcome': 'fail', 'error': type(error).__name__ + ': ' + str(error),
                                                     'wall_seconds': time.monotonic() - started})
        raise


if __name__ == '__main__':
    main()
