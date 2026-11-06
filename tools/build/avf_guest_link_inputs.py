#!/usr/bin/env python3
"""Prepare genuine AVF guest archive/link rules without producing target code."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import re
import resource
import shutil
import shlex
import signal
import subprocess
import struct
import sys
import time

HEADERS_SHA = '058451939894bd48ccc2ad1fe8b8d85c515f2176d21c8025daa034be8e98abe7'
GRAPH_SHA = 'afc5cd206965de7e36a0aa17c4eb86a1f305689f386ccb22c55bd983567dd1dd'
LINK_TOOLS_SHA = '00f56086d206e6c470f9c5622d8be4832f24cdccbb044689fa8894c3d3a8d1dd'
HOST_INPUTS_SHA = '10f7c68ba08d2c72226d4f6b37d0f09e8755c8bca9e8dae9af0c7e3f08da3cf8'
LIMIT = 256 * 1024 * 1024
RUNNER_SHA = 'af193e91ef5a7c24cbba0f797415cc1f2944673e62aadc6d4ace4511810582e0'
TAILS = ('nonlto.o', 'version.o', 'lastkerneldataconst.o', 'lastkernelconstructor.o')
OWNER = 'codex-guest-exec-20261106-cu'
CONTRACT_SHA = '125a7627c1178d3812f3e618c8f8bcc125cb77520be100013cbcc710b84c9d3a'
TEXT_SHA = '1b630006261b7a00ba111cf5bb1b242faaf53514e26c50574da41ce043cfbc00'
NAMESPACE_DESCRIPTOR_SHA = '3343a382452d05c382a15ea54e3835c3125c67c451cb586a1c3ed5a939b37174'
# Exact accepted VM038 artifact-index entry; this is a source sanitizer policy.
SANITIZER_SHA = '8032fef3c05dc51b16f1b1dffe3ce11db686c6abedd382843a5e2415fa52a1d2'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def proc_status(pid='self'):
    result = {}
    try:
        for line in Path(f'/proc/{pid}/status').read_text().splitlines():
            if line.startswith(('VmRSS:', 'VmHWM:')):
                key, value, _ = line.split()
                result[key[:-1] + '_bytes'] = int(value) * 1024
    except FileNotFoundError:
        pass
    return result


def require_profile(values):
    expected = {'CURRENT_ARCH_CONFIG': 'ARM64', 'CURRENT_KERNEL_CONFIG': 'DEVELOPMENT',
                'CURRENT_MACHINE_CONFIG': 'BCM2837', 'USE_LTO': '0'}
    if any(values.get(k) != v for k, v in expected.items()):
        raise ValueError('Exact ARM64/DEVELOPMENT/BCM2837 non-LTO profile required')
    if '-exported_symbols_list' in values.get('LDFLAGS_KERNEL_ONLY', ''):
        raise ValueError('RELEASE exports cannot be imposed on DEVELOPMENT')
    if '-undefined' in values.get('LDFLAGS_KERNEL', ''):
        raise ValueError('Unresolved symbols may not be suppressed')


def require_order(objects, expected):
    if objects != expected or len(objects) != len(set(objects)):
        raise ValueError('Exact genuine guest object order required')


def session_rss(session):
    total = 0
    for entry in Path('/proc').iterdir():
        if entry.name.isdigit():
            try:
                fields = (entry / 'stat').read_text().rsplit(')', 1)[1].split()
                if int(fields[3]) == session:
                    total += proc_status(entry.name).get('VmRSS_bytes', 0)
            except (FileNotFoundError, ProcessLookupError):
                pass
    return total


class Preparation:
    def __init__(self, args):
        self.args = args
        self.main = args.main.resolve()
        self.vm = args.vm008.resolve()
        self.h = self.vm / 'artifacts/avf-kernel-headers'
        self.kernel = self.h / 'prepare-2/source/xnu'
        self.out = args.out.absolute()
        owned = Path(__file__).resolve().parents[2] / 'artifacts/avf-guest-link-inputs'
        if self.out != self.out.resolve() or not self.out.is_relative_to(owned):
            raise ValueError('Fresh canonical owned output outside immutable VM008 required')
        self.out.mkdir(parents=True, exist_ok=False)
        shutil.copyfile(__file__, self.out / 'builder.py')
        self.report = dict(kind='host-test', origin='local-host', outcome='inconclusive',
                           recorded_at=datetime.now(timezone.utc).isoformat(),
                           argv=sys.argv, builder_sha256=sha(__file__), commands=[], checks=[],
                           source_only=True, compiler_executed=False, generator_executed=False,
                           linker_executed=False, guest_executed=False, native_objects_reused=False,
                           full_kernel_qualified=False, private_apple_abi_qualified=False,
                           initial_process=proc_status(),
                           initial_raw_ru_maxrss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
                           input_bindings={})
        ledger = json.load((self.main / 'state/lab.json').open())
        experiment = args.experiment or ('AVFLINKTEXT-001' if args.mode == 'metadata' else 'AVFLINKPREP-001')
        plan = next((e for e in ledger['experiments'] if e['id'] == experiment), None)
        if not plan or plan['status'] != 'planned' or plan['task'] != 'VM-022' or plan['owner'] != 'codex-guest-exec-20261106-cu':
            raise ValueError('An active original-owner VM022 experiment plan is required')
        self.report['experiment'] = experiment

    def bind(self, path, expected=None):
        path = Path(path)
        actual = sha(path)
        if expected is not None and actual != expected:
            raise ValueError('Input hash mismatch: ' + str(path))
        self.report['input_bindings'][str(path)] = actual
        return actual

    def inputs(self):
        descriptor = self.vm / 'fixtures/public/avf-kernel-headers/qualified-component.json'
        self.bind(descriptor, HEADERS_SHA)
        desc = json.load(descriptor.open())
        index = self.main / desc['artifact_index']
        self.bind(index, desc['artifact_index_sha256'])
        self.index = json.load(index.open())['files']
        self.bind(self.h / 'handoff-1/next-full-object-manifest.json', GRAPH_SHA)
        self.graph = json.load((self.h / 'handoff-1/next-full-object-manifest.json').open())
        if len(self.graph) != 1080 or len({r['id'] for r in self.graph}) != 1080:
            raise ValueError('Exact genuine 1080-row graph required')
        self.prepared = json.load((self.h / 'prepare-2/prepared-component.json').open())
        self.bind_index(self.h / 'prepare-2/prepared-component.json')
        self.parent = json.load((self.h / 'handoff-1/report.json').open())
        self.bind_index(self.h / 'handoff-1/report.json')
        self.base = next(c['argv'] for c in self.parent['commands']
                         if any('query-objects-osfmk.mk' in a for a in c['argv']))
        self.compiler = Path(next(a.split('=', 1)[1] for a in self.base if a.startswith('CC=')))
        self.bind_index(self.compiler)
        self.shim = Path(next(a.split('=', 1)[1] for a in self.base if a.startswith('MakeInc_cmd=')))
        self.bind_index(self.shim)
        tool_descriptor = self.main / 'fixtures/public/xnu-kernel-link-inputs/qualified-component.json'
        self.bind(tool_descriptor, LINK_TOOLS_SHA)
        self.tools = json.load(tool_descriptor.open())['tools']
        for name in ['linker', 'libtool', 'setsegname']:
            self.bind(self.main / self.tools[name], self.tools[name + '_sha256'])
        host_descriptor = self.main / 'fixtures/public/xnu-host-tools/qualified-inputs.json'
        self.bind(host_descriptor, HOST_INPUTS_SHA)
        host_inputs = json.load(host_descriptor.open())
        for relative, expected in host_inputs['dependency_files_sha256'].items():
            self.bind(self.main / host_inputs['dependency_prefix'] / relative, expected)
        # Freeze genuine rules, producer sources and every export/plist data input.
        for p in sorted((self.kernel / 'makedefs').glob('MakeInc.*')):
            self.bind_index(p)
        self.bind_index(self.kernel / 'Makefile')
        for p in sorted((self.kernel / 'config').rglob('*')):
            if p.is_file():
                self.bind_index(p)
        for name in ['nonlto.c', 'lastkerneldataconst.c', 'lastkernelconstructor.c']:
            self.bind_index(self.kernel / 'libsa' / name)
        self.bind_index(self.kernel / 'SETUP/setsegname/setsegname.c')
        self.bind(self.kernel / 'SETUP/setsegname/setsegname.c',
                  'e02a92537a4a14de6c8719cb87ac272d5fb1b4b5f5c9dd4a63d385b9a89e420d')
        self.bind(self.main / 'artifacts/xnu-kernel-direct-tail/build-session3/host-compat.h',
                  'aa377a67bdb81f56135f73cd42123861768ebccad9cab7f7196e4c236b8bca28')
        self.component_defines = {}
        for component, row in self.prepared['configurations'].items():
            self.bind(Path(row['root']) / 'Makefile', row['makefile_sha256'])
            definitions = re.findall(r'^export CONFIG_DEFINES = (.*)$',
                                     (Path(row['root']) / 'Makefile').read_text(), re.M)
            if len(definitions) != 1:
                raise ValueError('One genuine guest CONFIG_DEFINES declaration required')
            self.component_defines[component] = definitions[0]
        self.report['tools'] = self.tools
        self.report['configuration_context'] = dict(
            component_CONFIG_DEFINES=self.component_defines,
            kernel_and_config_CONFIG_DEFINES='',
            reason='Each doconf Makefile declares its own export; genuine top-level/config Makefiles declare no CONFIG_DEFINES. The isolated environment prevents unrelated inherited Make variables.')
        self.report['guest_graph'] = dict(path=str(self.h / 'handoff-1/next-full-object-manifest.json'),
                                          sha256=GRAPH_SHA, objects=1080)

    def bind_index(self, path):
        path = Path(path)
        key = str(path.relative_to(self.main)) if path.is_relative_to(self.main) else str(path)
        if key not in self.index:
            raise ValueError('Source missing immutable VM008 index binding: ' + str(path))
        return self.bind(path, self.index[key])

    def query(self, label, includes, keys, component='osfmk', extra='', overrides=None, prelude=''):
        cwd = self.out / 'queries' / label
        cwd.mkdir(parents=True)
        query = cwd / 'query.mk'
        query.write_text(''.join('include ' + str(p) + '\n' for p in includes) + prelude +
                         ''.join('$(info AVFLINK|' + k + '|$(' + k + '))\n' for k in keys) + extra +
                         '\n.PHONY: avflink_query\navflink_query: ;\n')
        source = self.kernel if component == 'kernel' else self.kernel / component
        replace = {'TARGET': str(cwd), 'OBJROOT': str(self.out), 'OBJPATH': str(self.out / 'stage'),
                   'SOURCE': str(source) + '/', 'RELATIVE_SOURCE_PATH': '.' if component == 'kernel' else './' + component,
                   'DSTROOT': str(self.out / 'installtree'),
                   'CONFIG_DEFINES': self.component_defines.get(component, '')}
        replace.update(overrides or {})
        argv = self.base.copy()
        argv[argv.index('-f') + 1] = str(query)
        argv = [next((k + '=' + v for k, v in replace.items() if a.startswith(k + '=')), a) for a in argv]
        argv[-1] = 'avflink_query' if '=' not in argv[-1] else argv[-1]
        if argv[-1] != 'avflink_query':
            argv.append('avflink_query')
        env = {'PATH': '/usr/bin:/bin'}
        env.update(LC_ALL='C', PYTHONUTF8='1', PYTHONNOUSERSITE='1', GIT_NO_LAZY_FETCH='1',
                   GIT_OPTIONAL_LOCKS='0', HAKIOS_VERSION_SUFFIX='-vm022', GIT_CEILING_DIRECTORIES=str(self.out))
        start = time.monotonic()
        with (cwd / 'stdout.txt').open('w') as stdout, (cwd / 'stderr.txt').open('w') as stderr:
            process = subprocess.Popen(argv, cwd=cwd, env=env, stdout=stdout, stderr=stderr, start_new_session=True)
            peak = 0
            try:
                while process.poll() is None:
                    peak = max(peak, session_rss(process.pid))
                    if peak + proc_status().get('VmRSS_bytes', 0) > LIMIT or time.monotonic() - start > 20:
                        raise RuntimeError('Bounded source query exceeded RSS/deadline')
                    time.sleep(.025)
            except BaseException:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                raise
        record = dict(argv=argv, cwd=str(cwd), exit_code=process.returncode,
                      elapsed_seconds=time.monotonic()-start, peak_query_session_rss_bytes=peak,
                      stdout=str(cwd / 'stdout.txt'), stdout_sha256=sha(cwd / 'stdout.txt'),
                      stderr=str(cwd / 'stderr.txt'), stderr_sha256=sha(cwd / 'stderr.txt'),
                      query_sha256=sha(query))
        self.report['commands'].append(record)
        if process.returncode:
            raise ValueError('Genuine source query failed: ' + label)
        text = (cwd / 'stdout.txt').read_text()
        values = {r[1]: r[2] for line in text.splitlines() if line.startswith('AVFLINK|') and len(r := line.split('|', 2)) == 3}
        if set(values) != set(keys):
            raise ValueError('Incomplete genuine query variables: ' + label)
        for p in values.get('MAKEFILE_LIST', '').split():
            if Path(p) != query:
                self.bind_index(Path(p))
        return values

    def admit(self):
        samples = []
        for _ in range(3):
            available = int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines()
                                 if line.startswith('MemAvailable:'))) * 1024
            samples.append(available)
            time.sleep(1)
        self.report['MemAvailable_admission_bytes'] = samples
        if min(samples) < 4 * 1024 ** 3:
            raise RuntimeError('Three stable MemAvailable >=4GiB samples required')

    def prepare(self):
        self.inputs()
        self.bind('/usr/bin/make')
        self.admit()
        components = {}
        common = ['CURRENT_ARCH_CONFIG', 'CURRENT_KERNEL_CONFIG', 'CURRENT_MACHINE_CONFIG', 'USE_LTO', 'MAKEFILE_LIST']
        for component, cfg in self.prepared['configurations'].items():
            keys = common + ['OBJS', 'LIBOBJS', 'HIB_FILES', 'KLD_FILES', 'LAST_FILES']
            values = self.query(component, [Path(cfg['root']) / 'Makefile'], keys, component)
            require_profile(values)
            objects = values['OBJS'].split()
            expected = [r['target'] for r in self.graph if r['component'] == component]
            require_order(objects, expected)
            components[component] = dict(variables=values, linked_ids=[component + '/' + n for n in objects],
                                         filelist_template=['@GUEST_OBJECT_ROOT@/' + component + '/DEVELOPMENT/' + n for n in objects],
                                         library_only_unbuilt=[n for n in values['LIBOBJS'].split() if n not in objects])
            text = (Path(cfg['root']) / 'Makefile').read_text()
            begin = text.index('$(COMPONENT).filelist:')
            end = text.index('$(COMPONENT).libfilelist:', begin)
            components[component]['genuine_filelist_rule'] = text[begin:end]
        topkeys = common + ['COMPONENT_LIST', 'BUILD_STATIC_LINK', 'BUILD_XNU_LIBRARY', 'LDFLAGS_KERNEL',
                           'LDFLAGS_KERNEL_ONLY', 'LD_KERNEL_LIBS', 'LD_KERNEL_ARCHIVES', 'LDFILES_KERNEL_ONLY',
                           'EXTRA_KC_LINKARGS', 'KERNEL_FILE_NAME', 'ARM64_LINK_ADDR', 'ARM64_PLKSEG_ADDR',
                           'C_RULE_1A', 'CFLAGS_NOLTO_FLAG', 'LAST_FILES', 'LD']
        top = self.query('kernel', [self.shim, self.kernel / 'makedefs/MakeInc.def', self.kernel / 'makedefs/MakeInc.rule', self.kernel / 'makedefs/MakeInc.kernel'], topkeys, 'kernel')
        require_profile(top)
        tail_prelude = ''
        tail_keys = []
        for target, source in [('nonlto.o', 'libsa/nonlto.c'), ('version.o', '@FRESH_VERSION_C@'),
                               ('lastkerneldataconst.o', 'libsa/lastkerneldataconst.c'),
                               ('lastkernelconstructor.o', 'libsa/lastkernelconstructor.c')]:
            key = 'TAIL_' + target
            tail_keys.append(key)
            source_path = source if source.startswith('@') else str(self.kernel / source)
            tail_prelude += '$(eval @ := ' + target + ')\n$(eval < := ' + source_path + ')\n'
            flags = ' $(CFLAGS_NOLTO_FLAG)' if target in ['nonlto.o', 'lastkernelconstructor.o'] else ''
            tail_prelude += key + ' := $(C_RULE_1A) $<' + flags + '\n'
        tails = self.query('tails', [self.shim, self.kernel / 'makedefs/MakeInc.def',
                           self.kernel / 'makedefs/MakeInc.rule', self.kernel / 'makedefs/MakeInc.kernel'],
                           tail_keys, 'kernel', prelude=tail_prelude)
        if set(top['COMPONENT_LIST'].split()) != set(components):
            raise ValueError('Genuine eight-component order required')
        configkeys = common + ['EXPORTS_FILES', 'SYMBOL_COMPONENT_LIST', 'SYMBOL_SET_PLIST_COMPONENT_LIST',
                               'Kasan_EXPORTS', 'Kcov_EXPORTS', 'EXPORT_SOURCE_ARCH_CONFIG_LC', 'KEXT_PLIST_LIST']
        config = self.query('config', [self.kernel / 'config/Makefile'], configkeys, 'config')
        require_profile(config)
        controls = []
        release = self.query('negative-release', [self.shim, self.kernel / 'makedefs/MakeInc.def',
                            self.kernel / 'makedefs/MakeInc.rule', self.kernel / 'makedefs/MakeInc.kernel'],
                            topkeys, 'kernel', overrides={'CURRENT_KERNEL_CONFIG': 'RELEASE', 'CURRENT_KERNEL_CONFIG_LC': 'release'})
        try:
            require_profile(release)
        except ValueError as error:
            controls.append(dict(name='actual RELEASE source selection rejected', error=str(error)))
        else:
            raise ValueError('Wrong-profile negative control accepted')
        try:
            self.bind(self.main / self.tools['linker'], '0' * 64)
        except ValueError as error:
            controls.append(dict(name='changed tool binding rejected', error=str(error)))
        else:
            raise ValueError('Changed-tool negative control accepted')
        selected = components['osfmk']['linked_ids']
        try:
            require_order(list(reversed(selected)), selected)
        except ValueError as error:
            controls.append(dict(name='same object set with incorrect order rejected', error=str(error)))
        else:
            raise ValueError('Wrong-order negative control accepted')
        self.report['negative_controls'] = controls
        order = top['COMPONENT_LIST'].split()
        flat = [identifier for c in order for identifier in components[c]['linked_ids']]
        if len(flat) != 1080 or Counter(flat) != Counter(r['id'] for r in self.graph):
            raise ValueError('Complete guest ordered link filelist required')
        rules = {str(p.relative_to(self.kernel)): p.read_text() for p in [self.kernel / 'makedefs/MakeInc.kernel', self.kernel / 'config/Makefile']}
        dump(self.out / 'genuine-rules.json', rules)
        archive_recipe = next(line.strip() for line in rules['makedefs/MakeInc.kernel'].splitlines()
                              if '$(LIBTOOL) -ca -filelist link.filelist version.o' in line)
        link_recipe = next(line.strip() for line in rules['makedefs/MakeInc.kernel'].splitlines()
                           if '$(LD) $(LDFLAGS_KERNEL)' in line and '-filelist link.filelist version.o' in line)
        target_root = str(self.out / 'queries/kernel')
        source_context = next(a.split('=', 1)[1] for a in self.base if a.startswith('SDKROOT='))
        def placeholder(value):
            return value.replace(target_root, '@GUEST_LINK_ROOT@').replace(source_context, '@GUEST_PROVIDER_CONTEXT@')
        link_argv = shlex.split(top['LD']) + ['--ld-path=' + str(self.main / self.tools['linker'])]
        link_argv += shlex.split(placeholder(top['LDFLAGS_KERNEL'])) + shlex.split(placeholder(top['LDFLAGS_KERNEL_ONLY']))
        link_argv += ['-filelist', '@GUEST_LINK_ROOT@/link.filelist', '@GUEST_LINK_ROOT@/version.o',
                      '@GUEST_LINK_ROOT@/lastkerneldataconst.o', '@GUEST_LINK_ROOT@/lastkernelconstructor.o',
                      '@GUEST_LINK_ROOT@/nonlto.o', '-o', '@GUEST_LINK_ROOT@/' + top['KERNEL_FILE_NAME'] + '.unstripped']
        link_argv += shlex.split(placeholder(top['LD_KERNEL_LIBS'])) + shlex.split(placeholder(top['LD_KERNEL_ARCHIVES']))
        contract = dict(schema_version=1, task='VM-022', profile='ARM64/DEVELOPMENT/BCM2837',
                        graph_sha256=GRAPH_SHA, component_order=order, components=components, ordered_link_ids=flat,
                        top_level_variables=top, symbolset_variables=config, tools=self.tools,
                        archive_recipe=archive_recipe, link_recipe=link_recipe,
                        link_driver=top['LD'], linker_selection_requires_qualification=True,
                        next_owned_link_argv_template=link_argv,
                        next_owned_archive_argv_template=[str(self.main/self.tools['libtool']), '-ca', '-filelist',
                            '@GUEST_LINK_ROOT@/link.filelist', '@GUEST_LINK_ROOT@/version.o',
                            '@GUEST_LINK_ROOT@/lastkerneldataconst.o', '@GUEST_LINK_ROOT@/lastkernelconstructor.o',
                            '-o', '@GUEST_LINK_ROOT@/' + top['KERNEL_FILE_NAME'] + '.link/' + top['KERNEL_FILE_NAME'] + '.a'],
                        placeholder_contract={'@GUEST_LINK_ROOT@':'fresh coherent accepted staging directory',
                            '@GUEST_PROVIDER_CONTEXT@':'fresh guest source-built provider library context; no SDK identity implied'},
                        tail_compile_recipe_templates=tails,
                        tail_compile_cwd_template='@GUEST_LINK_ROOT@',
                        archive_member_count_if_complete=1083, direct_link_extra_objects=['version.o', 'lastkerneldataconst.o', 'lastkernelconstructor.o', 'nonlto.o'],
                        unresolved_symbols_must_fail=True, target_production_executed=False,
                        execution_requires=['accepted VM008 namespace', 'accepted fresh component objects and providers', 'registered experiment', 'root resource lease'],
                        unmeasured=['all1080 guest objects', 'fresh guest tail/version/nonlto products', 'firehose pthread cc_kext providers', 'private IIG ABI', 'all required definitions and exports', 'archive member bytes', 'linker compatibility with final graph', 'final image entry/layout', 'guest console and stopping'])
        dump(self.out / 'prepared-link-inputs.json', contract)
        for path, expected in self.report['input_bindings'].copy().items():
            self.bind(path, expected)
        self.report['checks'] += ['all1080 exact ordered object IDs', 'eight genuine component filelist queries', 'DEVELOPMENT export selection retained', 'source-built tool hashes', 'symbolset and alias rules retained']
        self.report['prepared_contract'] = dict(path=str(self.out / 'prepared-link-inputs.json'), sha256=sha(self.out / 'prepared-link-inputs.json'))
        self.report['outcome'] = 'pass'

    def source_command(self, argv, label):
        allowed = {'generate_linker_exports.sh', 'generate_linker_aliases.sh',
                   'generate_symbolset_plist.sh', 'generate_combined_symbolsets_plist.sh', 'newvers.pl'}
        argv = [str(a) for a in argv]
        if argv[0] not in ['sh', 'perl'] or Path(argv[1]).parent != self.kernel / 'config' or Path(argv[1]).name not in allowed:
            raise ValueError('Only exact genuine source-text producers are permitted')
        output = Path(argv[2])
        if not output.is_relative_to(self.out):
            raise ValueError('Text producer output must be owned')
        log = self.out / 'text-commands' / label
        log.mkdir(parents=True)
        env = dict(PATH='/usr/bin:/bin', LC_ALL='C', PYTHONUTF8='1', PYTHONNOUSERSITE='1',
                   SRCROOT=str(self.kernel), OBJROOT=str(self.out), TARGET=str(self.out / 'stage'),
                   CURRENT_KERNEL_CONFIG_LC='development', HAKIOS_VERSION_SUFFIX='-vm022',
                   GIT_NO_LAZY_FETCH='1', GIT_OPTIONAL_LOCKS='0', GIT_CEILING_DIRECTORIES=str(self.out))
        start = time.monotonic()
        with (log / 'stdout.txt').open('w') as stdout, (log / 'stderr.txt').open('w') as stderr:
            child = subprocess.Popen(argv, cwd=self.out, env=env, stdout=stdout, stderr=stderr, start_new_session=True)
            peak = 0
            try:
                while child.poll() is None:
                    peak = max(peak, session_rss(child.pid))
                    if peak + proc_status().get('VmRSS_bytes', 0) > LIMIT or time.monotonic() - start > 20:
                        raise RuntimeError('Source-text production exceeded owned RSS/deadline')
                    time.sleep(.025)
            except BaseException:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
                raise
        self.report['commands'].append(dict(argv=argv, cwd=str(self.out), environment=env,
            exit_code=child.returncode, elapsed_seconds=time.monotonic()-start,
            peak_session_rss_bytes=peak, stdout=str(log/'stdout.txt'), stdout_sha256=sha(log/'stdout.txt'),
            stderr=str(log/'stderr.txt'), stderr_sha256=sha(log/'stderr.txt')))
        if child.returncode:
            raise ValueError('Genuine source-text producer failed: ' + label)
        self.report['generator_executed'] = True

    def metadata(self):
        self.inputs()
        self.bind('/usr/bin/make')
        self.admit()
        if self.args.prepared is None:
            raise ValueError('Passing owned source-query preparation required')
        prior_path = self.args.prepared.resolve()
        if not prior_path.is_relative_to(Path(__file__).resolve().parents[2] / 'artifacts/avf-guest-link-inputs'):
            raise ValueError('Prior preparation must belong to this worktree')
        prior = json.load((prior_path / 'evidence.json').open())
        if prior.get('outcome') != 'pass' or not prior.get('source_only'):
            raise ValueError('Passing source-only preparation required')
        contract_path = prior_path / 'prepared-link-inputs.json'
        self.bind(contract_path, prior['prepared_contract']['sha256'])
        self.bind(prior_path / 'evidence.json')
        contract = json.load(contract_path.open())
        require_profile(contract['top_level_variables'])
        names = contract['symbolset_variables']['SYMBOL_SET_PLIST_COMPONENT_LIST'].split()
        keys = ['CURRENT_ARCH_CONFIG', 'CURRENT_KERNEL_CONFIG', 'CURRENT_MACHINE_CONFIG', 'USE_LTO',
                'MAKEFILE_LIST', 'EXPORTS_FILES', 'SYMBOL_COMPONENT_LIST', 'SYMBOL_SET_PLIST_COMPONENT_LIST',
                'Kasan_EXPORTS', 'Kcov_EXPORTS'] + [name + '_EXPORTS' for name in names]
        values = self.query('metadata-config', [self.kernel / 'config/Makefile'], keys, 'config')
        require_profile(values)
        stage = self.out / 'stage'
        stage.mkdir()
        exports = [self.kernel / 'config' / name for name in values['EXPORTS_FILES'].split()]
        exports += [Path(name) for key in ['Kasan_EXPORTS', 'Kcov_EXPORTS'] for name in values[key].split()]
        for path in exports:
            self.bind_index(path)
        for output, script in [('all-kpi.exp', 'generate_linker_exports.sh'), ('all-alias.exp', 'generate_linker_aliases.sh')]:
            self.source_command(['sh', self.kernel/'config'/script, stage/output, *exports], output)
        generated = []
        for name in names:
            original = self.kernel / 'config/System.kext/PlugIns' / (name + '.kext') / 'Info.plist'
            self.bind_index(original)
            info = stage / (name + '-Info.plist')
            shutil.copyfile(original, info)
            self.source_command(['perl', self.kernel/'config/newvers.pl', info], 'newvers-'+name)
            output = stage / (name + '.symbolset.plist')
            selected = [Path(n) for n in values[name + '_EXPORTS'].split()]
            for path in selected:
                self.bind_index(path)
            self.source_command(['sh', self.kernel/'config/generate_symbolset_plist.sh', output, info, *selected], 'symbolset-'+name)
            plistlib.loads(output.read_bytes())
            generated.append(output)
        xml = stage / 'symbolsets.xml.plist'
        self.source_command(['sh', self.kernel/'config/generate_combined_symbolsets_plist.sh', xml, *generated], 'combined-symbolsets')
        value = plistlib.loads(xml.read_bytes())
        binary = stage / 'symbolsets.plist'
        binary.write_bytes(plistlib.dumps(value, fmt=plistlib.FMT_BINARY, sort_keys=False))
        if plistlib.loads(binary.read_bytes()) != value or len(value['SymbolsSets']) != 9 or value['WeakRefFallbackSymbol'] != {'SymbolName': '_gOSKextUnresolved'}:
            raise ValueError('Exact nine symbolsets and genuine fallback required')
        version = stage / 'version.c'
        shutil.copyfile(self.kernel / 'config/version.c', version)
        self.source_command(['perl', self.kernel/'config/newvers.pl', version], 'newvers-version-source')
        if '###KERNEL_VERSION' in version.read_text():
            raise ValueError('Unresolved genuine version template marker')
        metadata = dict(schema_version=1, task='VM-022', prior_contract=str(contract_path),
            prior_contract_sha256=sha(contract_path), source_query=values, symbolsets=names,
            outputs={str(p):sha(p) for p in sorted(stage.iterdir()) if p.is_file()},
            export_lines=len((stage/'all-kpi.exp').read_text().splitlines()),
            alias_lines=len((stage/'all-alias.exp').read_text().splitlines()),
            symbol_entries=sum(len(item['Symbols']) for item in value['SymbolsSets']),
            binary_converter='Python stdlib plistlib with semantic roundtrip; native plutil oracle unqualified',
            object_or_archive_or_image_produced=False, unresolved_symbols_not_assessed=True)
        dump(self.out / 'prepared-text-inputs.json', metadata)
        for path, expected in self.report['input_bindings'].copy().items():
            self.bind(path, expected)
        self.report['prepared_text_inputs'] = dict(path=str(self.out/'prepared-text-inputs.json'), sha256=sha(self.out/'prepared-text-inputs.json'))
        self.report['outcome'] = 'pass'

    def finish(self):
        self.report['final_process'] = proc_status()
        self.report['final_raw_ru_maxrss_bytes'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
        self.report['rss_gate_counter'] = '/proc/self/status VmHWM for this executable image; raw getrusage may retain pre-exec history'
        if self.report['final_process'].get('VmHWM_bytes', 0) > LIMIT:
            self.report['outcome'] = 'inconclusive'
            self.report['resource_error'] = 'Current executable image exceeded256MiB'
        dump(self.out / 'evidence.json', self.report)

    def link_plan(self):
        """Read-only admission and a finite proposed command chain, never execution."""
        self.inputs()
        self.admit()
        fixture = Path(__file__).resolve().parents[2] / 'fixtures/public/avf-guest-link-inputs'
        spec_path = fixture / 'link-plan-inputs.json'
        self.bind(spec_path)
        spec = json.load(spec_path.open())
        selected = spec['selectors']
        self.bind(self.main / selected['path'], selected['sha256'])
        selectors = json.load((self.main / selected['path']).open())['shards']
        parent_path = fixture / 'prepared-component.json'
        self.bind(parent_path)
        parent = json.load(parent_path.open())
        contract_path = self.main / parent['source_query_contract']['path']
        self.bind(contract_path, parent['source_query_contract']['sha256'])
        contract = json.load(contract_path.open())
        require_profile(contract['top_level_variables'])
        text_path = self.main / parent['text_inputs']['path']
        self.bind(text_path, parent['text_inputs']['sha256'])
        text = json.load(text_path.open())
        for path, expected in text['outputs'].items():
            self.bind(path, expected)
        for path, expected in spec['pinned_context'].items():
            self.bind(self.main / path, expected)
        by_id = {row['id']:row for row in self.graph}
        owner = {}
        for shard, ids in selectors.items():
            if shard not in spec['producers']:
                raise ValueError('Every genuine shard needs a producer path contract')
            for identifier in ids:
                if identifier in owner:
                    raise ValueError('Overlapping shard ownership')
                owner[identifier] = shard
        if set(owner) != set(by_id):
            raise ValueError('Exact disjoint full1080 ownership required')
        actual = {}
        for shard, producer in spec['producers'].items():
            if 'raw_evidence' not in producer:
                continue
            raw_path = self.main / producer['raw_evidence']
            self.bind(raw_path, producer['raw_evidence_sha256'])
            raw = json.load(raw_path.open())
            if raw['outcome'] != 'pass' or raw.get('provenance', {}).get('manifest_sha256') != GRAPH_SHA:
                raise ValueError('Exact passing genuine guest raw capsule required')
            if set(row['id'] for row in raw['objects']) != set(selectors[shard]):
                raise ValueError('Raw capsule does not cover its exact assigned shard')
            execution_plan_path = self.main/producer['execution_root']/'execution-plan.json'
            expected_plan_sha = raw['artifact_hashes'][str(execution_plan_path)]
            self.bind(execution_plan_path, expected_plan_sha)
            execution_plan = json.load(execution_plan_path.open())
            planned = {row['id']:row for row in execution_plan['selected']}
            for item in raw['objects']:
                record_path = Path(item['record'])
                self.bind(record_path, item['record_sha256'])
                record = json.load(record_path.open())
                identifier = item['id']
                original = by_id[identifier]
                obj = self.main / producer['execution_root'] / 'objects' / identifier
                dep = self.main / producer['execution_root'] / 'dependencies' / (identifier + '.d')
                if (record['id'] != identifier or record['outcome'] != 'pass' or record['command']['exit_code'] != 0 or
                    Path(record['object']) != obj or Path(record['dependency_file']) != dep or
                    record['source_sha256'] != original['bound_source_sha256']):
                    raise ValueError('Object record differs from exact source/output contract: ' + identifier)
                if (record['command']['argv'] != planned[identifier]['argv'] or
                    record['input_key'] != planned[identifier]['input_key']):
                    raise ValueError('Actual compiler argv/input key differ from saved expanded execution plan')
                self.bind(obj, record['object_sha256'])
                self.bind(dep, record['dependency_file_sha256'])
                self.bind(record['source'], original['bound_source_sha256'])
                with obj.open('rb') as stream:
                    header = stream.read(32)
                if len(header) != 32 or struct.unpack_from('<II',header) != (0xfeedfacf, 0x100000c) or struct.unpack_from('<I',header,12)[0] != 1:
                    raise ValueError('Actual ARM64 MH_OBJECT bytes required: ' + identifier)
                actual[identifier] = dict(object=str(obj), object_sha256=record['object_sha256'],
                    dependency_file=str(dep), dependency_file_sha256=record['dependency_file_sha256'],
                    record=str(record_path), record_sha256=item['record_sha256'],
                    raw_evidence=str(raw_path), raw_evidence_sha256=producer['raw_evidence_sha256'],
                    execution_plan=str(execution_plan_path),execution_plan_sha256=expected_plan_sha,
                    input_key=record['input_key'], actual_bytes_verified=True,
                    private_IIG_ABI_qualified=False)
        if len(actual) != spec['expected_actual_objects']:
            raise ValueError('Expected exact194 current verified outputs')
        future = self.main / spec['owned_future_execution_root']
        if future.exists():
            raise ValueError('Proposed final execution root must remain fresh and unexecuted')
        mapped = []
        for identifier in contract['ordered_link_ids']:
            shard = owner[identifier]
            producer = spec['producers'][shard]
            producer_root = producer['execution_root']
            future_template = (str(self.main/producer_root) if producer_root else producer['execution_root_placeholder']) + '/objects/' + identifier
            row = dict(id=identifier, shard=shard, producer_task=producer['task'],
                source=by_id[identifier]['bound_source'], source_sha256=by_id[identifier]['bound_source_sha256'],
                producer_object=str(self.main/producer_root/'objects'/identifier) if producer_root else None,
                future_object_path_template=future_template,
                producer_root_status=producer['root_status'],
                owned_staged_object=str(future/'objects'/identifier.split('/')[0]/'DEVELOPMENT'/identifier.split('/')[1]),
                status='verified actual bytes' if identifier in actual else 'missing accepted producer capsule',
                exists_at_snapshot=(self.main/producer_root/'objects'/identifier).is_file() if producer_root else None)
            if identifier in actual:
                row.update(actual[identifier])
            mapped.append(row)
        runtime_spec = json.load((self.main/'worktrees/vm-023-20261106/fixtures/public/avf-guest-compiler-runtime/inputs.json').open())
        for key in ['archive', 'members', 'descriptor', 'compiler', 'linker']:
            row = runtime_spec['inputs'][key]
            self.bind(self.main/row['path'], row['sha256'])
        runtime = json.load((self.main/'worktrees/vm-023-20261106/artifacts/avf-guest-compiler-runtime/final-0e44b04/report.json').open())
        runtime_members = json.load((self.main/'worktrees/vm-023-20261106/artifacts/avf-guest-compiler-runtime/final-0e44b04/archive-members.json').open())
        if runtime['outcome'] != 'pass' or runtime['archive']['members'] != 287 or len(runtime_members) != 287:
            raise ValueError('Exact qualified287-member runtime route required')
        resource_root = str((self.main/runtime_spec['inputs']['archive']['path']).parents[2])
        provider_rows = {}
        for name, row in spec['providers'].items():
            path = self.main/row['archive']
            provider_rows[name] = dict(row, path=str(path), exists_at_snapshot=path.is_file(),
                admitted=False, required_checks=['genuine DEVELOPMENT BCM2837/MAX_CPUS8/MAX_CPU_CLUSTERS1 profile',
                    'reviewed component executor and explicit root lease', 'actual source/object/depfile hashes',
                    'ARM64 types and allocator metadata', 'exact archive member bytes/order',
                    'actual imports and selected guest definitions/layout/aliases'])
        donor = self.h/'prepare-2/source/scion'
        chain_sources = ['avf/README.md','avf/qemu-avf.sh','avf/shim/avfboot.c','xnuloader/mkpayload.py']
        for name in chain_sources:
            self.bind_index(donor/name)
        shim_report = json.load((self.main/'worktrees/vm-002-20261105/artifacts/vm-002/shim-20261105/report.json').open())
        shim_matches = []
        for row in shim_report['sources']:
            path = donor/row['path']
            self.bind_index(path)
            shim_matches.append(dict(path=str(path), current_sha256=sha(path),
                                     compiled_source_sha256=row['sha256'], matches=sha(path)==row['sha256']))
        replacement = {'@GUEST_LINK_ROOT@':str(future/'stage'), '@GUEST_PROVIDER_CONTEXT@':str(future/'providers')}
        def expand(value):
            for old, new in replacement.items():
                value = value.replace(old,new)
            return value
        link_argv = [expand(value) for value in contract['next_owned_link_argv_template']]
        link_argv[1:1] = ['-resource-dir',resource_root]
        stage = future/'stage'
        command_plan = [dict(stage='create fresh owned production directories only after admission',
            argv=['mkdir','-p',str(stage),str(stage/(contract['top_level_variables']['KERNEL_FILE_NAME']+'.link')),
                str(future/'providers/usr/local/lib/kernel/platform'),
                *[str(future/'objects'/component/'DEVELOPMENT') for component in contract['component_order']]],timeout_seconds=15)]
        object_copy_plan = [dict(id=row['id'],argv_template=['cp','--reflink=auto',
            row['producer_object'] or row['future_object_path_template'],row['owned_staged_object']],
            required_source_sha256=row.get('object_sha256'),
            blocked=row['id'] not in actual,original_is_immutable=True) for row in mapped]
        for name in ['all-kpi.exp','all-alias.exp','symbolsets.plist','version.c']:
            source = next(path for path in text['outputs'] if Path(path).name == name)
            command_plan.append(dict(stage='copy exact genuine text input',
                argv=['cp','--reflink=auto',source,str(stage/name)],required_source_sha256=text['outputs'][source],timeout_seconds=15))
        for component in contract['component_order']:
            query_report = json.load((contract_path.parent/'evidence.json').open())
            query = next(c for c in query_report['commands'] if c['cwd'].endswith('/queries/'+component))
            args = query['argv'].copy()
            rewrite = {'TARGET':str(future/'objects'/component), 'OBJROOT':str(future), 'OBJPATH':str(stage)}
            args = [next((key+'='+value for key,value in rewrite.items() if item.startswith(key+'=')), item) for item in args]
            args[-1] = component+'.filelist'
            args += ['-j1','SEG_HACK='+str(self.main/self.tools['setsegname']), 'LOG_LDFILELIST=:']
            args += [part for target in contract['components'][component]['variables']['OBJS'].split()+['.CFLAGS','.CXXFLAGS','.SFLAGS'] for part in ['-o',target]]
            command_plan.append(dict(stage='genuine staged component filelist and HIB/KLD transforms',component=component,
                argv=args,cwd=str(future/'objects'/component/'DEVELOPMENT'), timeout_seconds=120,
                logging_port='LOG_LDFILELIST=: changes only cosmetic logging',
                requires='fresh copies of every accepted component object; originals remain immutable'))
        command_plan.append(dict(stage='genuine component-order filelist concatenation',
            argv=['cat',*[str(future/'objects'/component/'DEVELOPMENT'/(component+'.filelist')) for component in contract['component_order']]],
            stdout_path=str(stage/'link.filelist'),timeout_seconds=15,expected_lines=1080))
        for key, recipe in contract['tail_compile_recipe_templates'].items():
            target = key.removeprefix('TAIL_')
            args = shlex.split(recipe.replace('@FRESH_VERSION_C@',str(stage/'version.c')))
            args += ['-o',str(stage/target)]
            command_plan.append(dict(stage='fresh genuine top-level tail compilation',target=target,argv=args,
                cwd=str(stage),timeout_seconds=120,requires='accepted namespace, separate new compiler lease; preserve all genuine flags'))
        command_plan.append(dict(stage='genuine last constructor segment transform',
            argv=[str(self.main/self.tools['setsegname']),'-s','__DATA','-n','__LASTDATA_CONST','-o',str(stage/'lastkernelconstructor.o__'),str(stage/'lastkernelconstructor.o')],
            rename_after_success=[str(stage/'lastkernelconstructor.o__'),str(stage/'lastkernelconstructor.o')],timeout_seconds=30))
        command_plan.append(dict(stage='genuine DEVELOPMENT direct image link',argv=link_argv,cwd=str(stage),timeout_seconds=180,
            requires='all1080 staged/transformed objects, four fresh tails, accepted providers/imports and independent plan review/root link lease'))
        command_plan.append(dict(stage='optional genuine static link archive after successful image, as original Make dependency requires',
            argv=[expand(value) for value in contract['next_owned_archive_argv_template']],cwd=str(stage),timeout_seconds=120,
            expected_members=1083,nonlto_outside_archive=True))
        image = stage/(contract['top_level_variables']['KERNEL_FILE_NAME']+'.unstripped')
        payload = future/'payload-console.xnup'
        command_plan.append(dict(stage='source-supported console-only XNUP package',
            argv=['python3','-s',str(donor/'xnuloader/mkpayload.py'),'-o',str(payload),'--no-version','kernel='+str(image),'--cmdline=-v avf_exit=1'],
            timeout_seconds=30,requires='actual complete genuine Mach-O passes independent entry/segment/memory layout checks and packaging admission',
            ramdisk='optional in source; absence cannot qualify PID1/VM002 full acceptance'))
        command_plan.append(dict(stage='separate bounded guest proposal only',
            argv=['timeout','--signal=TERM','--kill-after=5s','60s',str(self.main/'worktrees/vm-004-20261105/artifacts/qemu-host/build-6/build/qemu-system-aarch64'),
                  '-M','virt,gic-version=3','-accel','tcg','-cpu','cortex-a76','-smp','1','-m','256',
                  '-kernel',str(self.main/'worktrees/vm-002-20261105/artifacts/vm-002/shim-20261105/Image'),'-initrd',str(payload),
                  '-nographic','-serial','stdio','-monitor','none','-no-reboot'],
            requires='exclusive root QEMU lease plus reviewed runtime console/timer/MMU/DT/PSCI/stop gates; owned process accounting and preserved logs',
            timeout_is_boot_success=False,source_wrapper_default_2GiB_not_used=True))
        plan = dict(schema_version=1,task='VM-022',profile='ARM64/DEVELOPMENT/BCM2837',executed=False,
            ready_for_link=False,explicit_root_lease_present=False,
            ordered_object_map=mapped,verified_actual_objects=len(actual),missing_accepted_objects=1080-len(actual),
            providers=provider_rows,runtime=dict(archive=runtime_spec['inputs']['archive'],resource_root=resource_root,
                members=287,driver_route_measured_by_VM023=True,link_only_resource_override=True,
                archive_wide_import_candidates=runtime['archive']['external_imports'],actual_pulled_member_imports_unmeasured=True),
            shim_source_comparison=shim_matches,all_compiled_shim_source_hashes_match=all(row['matches'] for row in shim_matches),
            source_supported_route='genuine uncompressed ARM64 Mach-O -> XNUP kernel entry -> existing source-built AVF shim Image; no kernelcache/IM4P conversion in this route',
            future_execution_root=str(future),command_plan=command_plan,object_copy_plan=object_copy_plan,
            macho_image_admission_required=dict(format='little-endian ARM64 MH_EXECUTE Mach-O, not ELF/fat/compressed/kernelcache',
                bounded_load_commands=True,segments='LC_SEGMENT_64 file extents within actual image; vmsize>=filesize; nonwrapping ranges',
                minimum_nonempty_segment_vmaddr='0xfffffff007000000',
                entry='nonzero PC in bounded LC_UNIXTHREAD; executable mapped range; selected __start definition',
                layout='actual segment order/protections/aliases/metadata and complete definitions verified after real link',
                physical_extent='same matched shim source RAM/slide/payload/ramdisk/panic-region formula must fit the root-leased256MiB guest',
                payload='XNUP u32 lengths/16-byte entry alignment and total extents; no oversized-host-memory packager run',
                validation_executed=False),
            source_chain_scope='The old shim/QEMU evidence is synthetic CPU handoff only; it is not genuine XNU runtime evidence.',
            missing_required_inputs=['886 accepted object outputs','four freshly compiled top-level tails','accepted fresh firehose archive/profile/imports',
                'accepted fresh pthread archive/profile/imports/aliases','actual final symbol and pulled-runtime-member closure',
                'independent link plan review and explicit root leases','actual Mach-O entry/segment/extent image validation'],
            unresolved_queued_owner_roots=[row for row in spec['producers'].values() if row['execution_root'] is None],
            full_runtime_additional_gate='accepted owned PID1/mockfs root and its actual runtime ABI; console-only route cannot satisfy PID1 acceptance',
            staging_actions_required=['copy accepted194 and future886 original objects into new owned component/DEVELOPMENT paths',
                'copy hash-bound all-kpi.exp/all-alias.exp/symbolsets.plist/version.c into owned stage',
                'concatenate genuine component filelists in exact eight-component order into stage/link.filelist',
                'record fresh HIB/KLD/constructor postprocessing output hashes; preserve original objects',
                'stage accepted fresh provider archives as providers/usr/local/lib/kernel/libfirehose_kernel.a and libpthread_kext.a',
                'validate all input hashes/leases again immediately before every production step'])
        dump(self.out/'final-link-execution-plan.json',plan)
        self.report['checks'] = ['exact1080 disjoint producer mapping','194 actual raw sidecar/object/depfile/source bindings',
            '194 actual ARM64 MH_OBJECT headers','real287-member cc_kext descriptor/archive/driver resource route',
            'fresh providers stay unadmitted','Mach-O/XNUP/shim source route retained; no commands executed']
        self.report['plan_summary'] = dict(verified_actual_objects=len(actual),missing_accepted_objects=886,
            command_count=len(command_plan),executed=False,shim_sources_match=plan['all_compiled_shim_source_hashes_match'])
        self.report['prepared_final_plan'] = dict(path=str(self.out/'final-link-execution-plan.json'),sha256=sha(self.out/'final-link-execution-plan.json'))
        self.report['outcome'] = 'pass'


def accepted_runner(main):
    """Reuse the reviewed supervisor, write confinement, and root project budget."""
    path = main / 'tools/build/avf_kernel_objects.py'
    if sha(path) != RUNNER_SHA:
        raise ValueError('Exact accepted AF193 common executor required')
    spec = importlib.util.spec_from_file_location('vm022_accepted_objects', path)
    module = importlib.util.module_from_spec(spec)
    sys.dont_write_bytecode = True
    spec.loader.exec_module(module)
    return module


def resolve_tail_argv(recipe, target, query_root, actual_root, old_root, new_root, out):
    """Only resolve Make OBJROOT, the accepted namespace transition, and outputs."""
    if target not in TAILS:
        raise ValueError('Unknown top-level tail')
    original = shlex.split(recipe)
    if (original.count('-MF') != 1 or original.count('-c') != 1 or '-o' in original or
        original[original.index('-MF') + 1] != target[:-2] + '.d'):
        raise ValueError('Exact genuine one-output -MD/-MF tail recipe required')
    if '-MD' not in original or '-nostdinc' not in original or '-flto' in original:
        raise ValueError('Genuine non-LTO dependency-producing tail flags required')
    result, changes = [], []
    for number, token in enumerate(original):
        replacement = token
        # The two paths come from the same source MakeInc.def OBJROOT variable.
        for suffix in ['/EXPORT_HDRS', '/san/']:
            prefix = str(query_root) + suffix
            if token.startswith('-I' + prefix) or token.startswith('-fsanitize-ignorelist=' + prefix):
                replacement = token.replace(str(query_root), str(actual_root), 1)
        if token == '-I' + old_root:
            replacement = '-I' + new_root
        if token == '@FRESH_VERSION_C@':
            replacement = str(out / 'source-context/version.c')
        if number == original.index('-MF') + 1:
            replacement = str(out / 'dependencies' / token)
        if replacement != token:
            changes.append(dict(position=number, original=token, resolved=replacement))
        result.append(replacement)
    if (sum(item['original'] == '-I' + old_root for item in changes) != 1 or
        any(str(query_root) in token or '@' in token for token in result)):
        raise ValueError('Unresolved query path or missing exact namespace substitution')
    return result + ['-o', str(out / 'objects' / target)], changes


def tail_plan(args, common):
    """Derive a deterministic executable plan without scanning/hash-repeating the corpus."""
    main, out = args.main.resolve(), common.canonical_output_path(args.execute_out)
    owned = Path(__file__).resolve().parents[2] / 'artifacts/avf-guest-link-inputs'
    if not out.is_relative_to(owned) or out.exists():
        raise ValueError('Tail execution root must be a fresh canonical original-owner artifact path')
    bindings = {str(Path(__file__).resolve()): sha(__file__),
                str(main / 'tools/build/avf_kernel_objects.py'): RUNNER_SHA}
    def bound(path, expected):
        path = Path(path)
        value = common.load_project(path, expected)
        bindings[str(path)] = expected
        return value
    parent = main / 'worktrees/vm-022-20261106/artifacts/avf-guest-link-inputs'
    contract_path = parent / 'preparation-4/prepared-link-inputs.json'
    contract = bound(contract_path, CONTRACT_SHA)
    require_profile(contract['top_level_variables'])
    text = bound(parent / 'text-1/prepared-text-inputs.json', TEXT_SHA)
    descriptor_path = main / ('worktrees/vm-038-20261106/docs/procedures/'
        'avf-firehose-namespace/qualification-session1/qualified-component.json')
    descriptor = bound(descriptor_path, NAMESPACE_DESCRIPTOR_SHA)
    if (descriptor['namespace_digest'] != common.FIREHOSE_NAMESPACE or
        descriptor['namespace_version'] != common.FIREHOSE_SCHEMA):
        raise ValueError('Accepted new guest namespace required')
    receipt = bound(descriptor['namespace_receipt']['path'], descriptor['namespace_receipt']['sha256'])
    if common.canonical({k: receipt[k] for k in ['roots', 'absent_search_roots', 'files']}) != descriptor['namespace_digest']:
        raise ValueError('Exact same-byte namespace receipt required')
    h = args.vm008.resolve() / 'artifacts/avf-kernel-headers'
    # Original successful VM008 query supplies actual OBJROOT, not an invented -I.
    report_path = h / 'handoff-1/report.json'
    query_evidence = bound(parent / 'preparation-4/evidence.json',
        '03af641f495e521c291b4e0f7dfbdf3231d42159e434687a1a4ff7e44d30c750')
    expected_report = query_evidence['input_bindings'].get(str(report_path))
    if not expected_report:
        raise ValueError('Original query evidence must bind the producing VM008 report')
    report = bound(report_path, expected_report)
    base = next(row['argv'] for row in report['commands']
                if any('query-objects-osfmk.mk' in token for token in row['argv']))
    actual_root = Path(next(token.split('=', 1)[1] for token in base if token.startswith('OBJROOT=')))
    if actual_root != h / 'handoff-1':
        raise ValueError('Unexpected original source-query OBJROOT')
    query_root = contract_path.parent
    source_root = h / 'prepare-2/source/xnu'
    commands = []
    version_path = next(path for path in text['outputs'] if Path(path).name == 'version.c')
    bindings[version_path] = text['outputs'][version_path]
    for target in TAILS:
        recipe = contract['tail_compile_recipe_templates']['TAIL_' + target]
        argv, changes = resolve_tail_argv(recipe, target, query_root, actual_root,
            descriptor['old_root']['path'], descriptor['new_root']['path'], out)
        expected_source = str(out / 'source-context/version.c') if target == 'version.o' else str(source_root / 'libsa' / (target[:-2] + '.c'))
        if argv[-3] != expected_source:
            raise ValueError('Tail source position differs from genuine recipe')
        source_hash = (text['outputs'][version_path] if target == 'version.o' else
                       query_evidence['input_bindings'][expected_source])
        bindings[str(Path(shlex.split(recipe)[0]))] = common.COMPILER
        if target != 'version.o':
            bindings[expected_source] = source_hash
        ignorelist = next(token.split('=', 1)[1] for token in argv if token.startswith('-fsanitize-ignorelist='))
        bindings[ignorelist] = SANITIZER_SHA
        commands.append(dict(target=target, source=expected_source, source_sha256=source_hash,
            original_argv=shlex.split(recipe), argv=argv, substitutions=changes,
            cwd=str(out / 'source-context'), object=str(out / 'objects' / target),
            dependency_file=str(out / 'dependencies' / (target[:-2] + '.d')), timeout_seconds=120))
    # Bind the exact source rules that emitted the templates and transform.
    for path, digest in query_evidence['input_bindings'].items():
        if path.startswith(str(source_root / 'makedefs/')):
            bindings[path] = digest
    tool = main / contract['tools']['setsegname']
    bindings[str(tool)] = contract['tools']['setsegname_sha256']
    return dict(schema='avf-guest-link-tails-v1', resource_profile='project-budget-v1',
        task='VM-022', owner=OWNER, shard='guest-link-tails', executor_sha256=sha(__file__),
        common_executor_sha256=RUNNER_SHA, profile='ARM64/DEVELOPMENT/BCM2837',
        actual_output=str(out), commands=commands, input_bindings=bindings,
        namespace_receipt=descriptor['namespace_receipt'], namespace_digest=descriptor['namespace_digest'],
        sanitizer_source_index=descriptor['artifact_index'],
        original_query_root=str(query_root), resolved_OBJROOT=str(actual_root),
        original_OBJROOT_assignment=next(token for token in base if token.startswith('OBJROOT=')),
        fresh_version_source=dict(path=version_path, sha256=text['outputs'][version_path]),
        constructor_transform=dict(argv=[str(tool), '-s', '__DATA', '-n', '__LASTDATA_CONST',
            '-o', str(out / 'objects/lastkernelconstructor.o__'), str(out / 'objects/lastkernelconstructor.o')],
            temporary=str(out / 'objects/lastkernelconstructor.o__'),
            final=str(out / 'objects/lastkernelconstructor.o')),
        target_production_executed=False, archive_executed=False, link_executed=False,
        runtime_executed=False, private_apple_abi_qualified=False)


def tail_ownership(args, common):
    args.main = args.main.resolve()
    args.out = common.canonical_output_path(args.out)
    ledger = common.load_project(args.main / 'state/lab.json')
    task = next(item for item in ledger['tasks'] if item['id'] == 'VM-022')
    experiment = next((item for item in ledger['experiments'] if item['id'] == args.experiment), None)
    worktree = Path(__file__).resolve().parents[2]
    if (args.task != 'VM-022' or args.owner != OWNER or args.shard != 'guest-link-tails' or
        task['owner'] != OWNER or task['status'] != 'in_progress' or
        common.canonical_output_path(args.main / task['worktree']) != worktree or
        not args.out.is_relative_to(worktree / 'artifacts/avf-guest-link-inputs') or args.out.exists() or
        not experiment or experiment['task'] != 'VM-022' or experiment['owner'] != OWNER or experiment['status'] != 'planned'):
        raise ValueError('Fresh original-owner VM022 output, owned worktree and planned experiment required')


def verify_constructor_transform(raw, transformed):
    """Compare every actual byte; only eligible section segment names may change."""
    if raw.stat().st_size > 16 * 1024**2:
        raise ValueError('Unexpectedly oversized constructor object')
    data = bytearray(raw.read_bytes())
    count, size = struct.unpack_from('<II', data, 16)
    cursor, changed = 32, []
    for unused in range(count):
        command, extent = struct.unpack_from('<II', data, cursor)
        if command == 25:
            sections = struct.unpack_from('<I', data, cursor + 64)[0]
            for number in range(sections):
                at = cursor + 72 + number * 80
                name = data[at:at+16].split(b'\0')[0].decode('ascii')
                segment = data[at+16:at+32].split(b'\0')[0].decode('ascii')
                flags = struct.unpack_from('<I', data, at+64)[0]
                if segment == '__DATA' and not flags & 0x02000000:
                    data[at+16:at+32] = b'__LASTDATA_CONST'[:16].ljust(16, b'\0')
                    changed.append(name)
        cursor += extent
    if cursor != 32 + size or '__mod_init_func' not in changed or data != transformed.read_bytes():
        raise ValueError('Actual constructor output differs from genuine eligible-section rename')
    return changed


def execute_tails(args, common):
    """Only the separately admitted four-tail phase; never link or package here."""
    tail_ownership(args, common)
    supplied = common.load_project(args.source_plan, args.source_plan_sha256)
    args.execute_out = args.out
    expected = tail_plan(args, common)
    if supplied != expected:
        raise ValueError('Production must exactly reconstruct the reviewed source-derived tail plan')
    approval = common.load_project(args.approval, args.approval_sha256)
    if approval['source_plan_sha256'] != args.source_plan_sha256:
        raise ValueError('Root approval must bind this exact source plan')
    budget = common.project_approval(args, approval, executor_path=Path(__file__))
    report = dict(kind='host-test', origin='local-host', outcome='inconclusive', commands=[], objects={},
        recorded_at=datetime.now(timezone.utc).isoformat(), resource_profile='project-budget-v1',
        task=args.task, owner=args.owner, experiment=args.experiment, shard=args.shard,
        executor_sha256=sha(__file__), source_plan_sha256=args.source_plan_sha256,
        compiler_started=False, archive_executed=False, link_executed=False, guest_executed=False,
        initial_process=proc_status(), initial_raw_ru_maxrss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024)
    args.out.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(__file__, args.out / 'builder.py')
    reserved = False
    try:
        budget.reserve()
        reserved = True
        supervise = common.supervisor(args.main)
        cache = common.Digests()
        for path, digest in expected['input_bindings'].items():
            if cache.get(path) != digest:
                raise ValueError('Changed source/tool/recipe input: ' + path)
        for directory in ['source-context', 'objects', 'dependencies', 'commands', 'raw']:
            (args.out / directory).mkdir()
        version = expected['fresh_version_source']
        shutil.copyfile(version['path'], args.out / 'source-context/version.c')
        receipt = common.load_project(expected['namespace_receipt']['path'], expected['namespace_receipt']['sha256'])
        index = dict(receipt['files'])
        index[str(args.out / 'source-context/version.c')] = version['sha256']
        rows = [dict(cwd=row['cwd'], bound_source=row['source'], next_owned_compile_argv_template=row['argv']) for row in expected['commands']]
        # Shared namespace validator rejects new shadows, deleted files and directory symlinks.
        before = common.namespace(rows, index, cache)
        report['recipe_namespace_sha256'] = before['sha256']
        report['accepted_parent_namespace_sha256'] = expected['namespace_digest']
        dump(args.out / 'input-bindings.json', before)
        dump(args.out / 'execution-plan.json', expected)
        for number, row in enumerate(expected['commands']):
            budget.sample()
            if common.namespace(rows, index, cache) != before:
                raise ValueError('Tail include/source namespace changed before compilation')
            command = common.run_child(row['argv'], Path(row['cwd']), args.out,
                'commands/' + str(number) + '-' + row['target'], supervise, timeout=row['timeout_seconds'], budget=budget)
            report['commands'].append(command)
            report['compiler_started'] |= command.get('child_started', False)
            if command['outcome'] != 'pass':
                raise ValueError('Actual bounded tail compiler failed: ' + row['target'])
            obj, dep = Path(row['object']), Path(row['dependency_file'])
            measured = common.macho(obj)
            dependencies = common.dependencies(dep, row['cwd'], obj)
            if row['source'] not in dependencies:
                raise ValueError('Actual compiler dependencies omit the genuine tail source')
            dep_hashes = {path: cache.get(path) for path in dependencies}
            if any(index.get(path) != digest for path, digest in dep_hashes.items()):
                raise ValueError('Compiler used an unbound or changed header/source')
            report['objects'][row['target']] = dict(measured, object=str(obj),
                source=row['source'], source_sha256=row['source_sha256'], dependency_file=str(dep),
                dependency_file_sha256=sha(dep), dependencies=dep_hashes)
        transform = expected['constructor_transform']
        raw = args.out / 'raw/lastkernelconstructor.o'
        shutil.copyfile(transform['final'], raw)
        command = common.run_child(transform['argv'], args.out / 'source-context', args.out,
            'commands/4-constructor-segment', supervise, timeout=30, budget=budget)
        report['commands'].append(command)
        if command['outcome'] != 'pass':
            raise ValueError('Genuine last-constructor transform failed')
        report['constructor_before_transform'] = report['objects']['lastkernelconstructor.o']['sha256']
        common.macho(transform['temporary'])
        report['constructor_renamed_sections'] = verify_constructor_transform(raw, Path(transform['temporary']))
        Path(transform['temporary']).replace(transform['final'])
        report['objects']['lastkernelconstructor.o'].update(common.macho(transform['final']))
        if common.namespace(rows, index, cache) != before:
            raise ValueError('Tail namespace changed during production')
        for path, digest in expected['input_bindings'].items():
            if cache.get(path) != digest:
                raise ValueError('Bound production input changed')
        report['outcome'] = 'pass'
    except Exception as error:
        report.update(outcome='fail', error=repr(error))
    finally:
        try:
            report['budget_release'] = budget.release() if reserved else 'not reserved'
        except Exception as error:
            report.update(outcome='fail', budget_release_error=repr(error))
        report['final_process'] = proc_status()
        report['final_raw_ru_maxrss_bytes'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
        dump(args.out / 'evidence.json', report)
    return 0 if report['outcome'] == 'pass' else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--main', type=Path, required=True)
    parser.add_argument('--vm008', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--mode', choices=['prepare', 'metadata', 'link-plan', 'tail-plan', 'execute-tails'], default='prepare')
    parser.add_argument('--prepared', type=Path)
    parser.add_argument('--experiment')
    parser.add_argument('--task', default='VM-022')
    parser.add_argument('--owner', default=OWNER)
    parser.add_argument('--shard', default='guest-link-tails')
    parser.add_argument('--execute-out', type=Path)
    parser.add_argument('--source-plan', type=Path)
    parser.add_argument('--source-plan-sha256')
    parser.add_argument('--approval', type=Path)
    parser.add_argument('--approval-sha256')
    args = parser.parse_args()
    if args.mode in ['tail-plan', 'execute-tails']:
        common = accepted_runner(args.main.resolve())
        if args.mode == 'execute-tails':
            if not args.source_plan or not args.source_plan_sha256 or not args.approval or not args.approval_sha256 or not args.experiment:
                parser.error('execute-tails requires exact plan hash, approval and planned experiment')
            return execute_tails(args, common)
        if not args.execute_out:
            parser.error('tail-plan requires the distinct future --execute-out')
        tail_ownership(args, common)
        initial = proc_status()
        plan = tail_plan(args, common)
        args.out.mkdir(parents=True, exist_ok=False)
        dump(args.out / 'execution-plan.json', plan)
        shutil.copyfile(__file__, args.out / 'builder.py')
        dump(args.out / 'evidence.json', dict(kind='host-test', origin='local-host', outcome='pass',
            task=args.task, owner=args.owner, experiment=args.experiment, source_only=True,
            argv=sys.argv, builder_sha256=sha(__file__), compiler_executed=False,
            archive_executed=False, linker_executed=False, guest_executed=False,
            plan_sha256=sha(args.out / 'execution-plan.json'), initial_process=initial,
            final_process=proc_status(), raw_ru_maxrss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024))
        print(json.dumps(dict(outcome='pass', source_only=True, plan=str(args.out / 'execution-plan.json'), sha256=sha(args.out / 'execution-plan.json'))))
        return 0
    run = Preparation(args)
    try:
        if args.mode == 'link-plan':
            run.link_plan()
        elif args.mode == 'metadata':
            run.metadata()
        else:
            run.prepare()
    except Exception as error:
        run.report['error'] = repr(error)
        run.report['outcome'] = 'inconclusive'
    finally:
        run.finish()
    print(json.dumps(dict(outcome=run.report['outcome'], evidence=str(run.out / 'evidence.json'), error=run.report.get('error'))))
    return 0 if run.report['outcome'] == 'pass' else 2


if __name__ == '__main__':
    raise SystemExit(main())
