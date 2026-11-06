#!/usr/bin/env python3
"""Inventory genuine native E1S Make vectors; never invoke a target tool."""
import argparse
from collections import Counter
import hashlib
import json
from itertools import zip_longest
from pathlib import Path
import re
import resource
import shlex
import shutil
import subprocess
import time

OWNER = 'codex-e1s-development-body-graph-20261106-sr16'
KEYS = ['OBJS', 'LIBOBJS', 'CFILES', 'COBJS', 'CXXFILES', 'CXXOBJS', 'SFILES', 'SOBJS',
        'HIB_FILES', 'KLD_FILES', 'GENASSYM_LOCATION', 'CFLAGS', 'CXXFLAGS', 'SFLAGS',
        'CWARNFLAGS', 'CXXWARNFLAGS', 'INCFLAGS', 'INCFLAGS_EXTERN', 'CFLAGS_BOUND_CHECKS',
        'LD_KERNEL_LIBS', 'LD_KERNEL_ARCHIVES', 'LDFILES_KERNEL_ONLY', 'SEG_HACK']


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w') as f:
        json.dump(value, f, indent=2)
        f.write('\n')


def within(root, relative):
    r = Path(relative)
    if r.is_absolute() or '..' in r.parts:
        raise ValueError('Invalid owned relative path: ' + relative)
    p = root / r
    if not p.resolve().is_relative_to(root.resolve()):
        raise ValueError('Physical namespace escape: ' + relative)
    return p


def recipe_blocks(text):
    """Keep literal generated target prerequisites and all tabbed recipe lines."""
    blocks = {}
    target = None
    for line in text.splitlines():
        match = re.match(r'^([^\s:]+\.(?:o|co|cpo)):[ \t]*(.*)$', line)
        if match:
            target = match[1]
            row = blocks.setdefault(target, {'prerequisites': [], 'recipe': []})
            row['prerequisites'].append(match[2])
        elif line.startswith('\t') and target:
            blocks[target]['recipe'].append(line.strip())
        elif line and not line.startswith(('#', '-include')):
            target = None
    return blocks


class Graph:
    def __init__(self, main, out, reuse=None):
        self.main = main.resolve()
        self.report_out = out.absolute()
        self.out = reuse.absolute() if reuse else self.report_out
        self.reuse = reuse is not None
        owned = Path(__file__).resolve().parents[3]
        artifact_root = owned / 'artifacts/e1s-development-body-graph'
        if self.report_out != self.report_out.resolve() or self.report_out.exists() or not self.report_out.is_relative_to(artifact_root):
            raise ValueError('Use fresh canonical owned artifact output')
        if self.reuse and (self.out != self.out.resolve() or not self.out.is_relative_to(artifact_root) or not self.out.is_dir()):
            raise ValueError('Reuse only a retained owned component-stage directory')
        self.inputs = {}
        self.commands = json.loads((self.out / 'commands.json').read_text()) if self.reuse else []
        self.rows = []
        self.components = {}
        self.actual_generated = {}
        self.memory_samples = []
        self.memory_checks = 0

    def memory(self, phase):
        fields = {}
        for line in Path('/proc/self/status').read_text().splitlines():
            if line.startswith(('VmRSS:', 'VmHWM:', 'VmPeak:', 'VmSize:')):
                key, value, _ = line.split()
                fields[key.rstrip(':')] = int(value) * 1024
        self.memory_checks += 1
        if not self.memory_samples or fields != self.memory_samples[-1]['bytes']:
            self.memory_samples.append({'phase': phase, 'bytes': fields})
        if fields['VmRSS'] > 256 * 1024**2 or fields['VmHWM'] > 256 * 1024**2:
            raise ValueError('Actual parent RSS exceeded256MiB source-query budget')

    def pin(self, path, expected=None):
        path = Path(path)
        if path.is_symlink() or not path.is_file():
            raise ValueError('Expected ordinary input: ' + str(path))
        h = sha(path)
        if expected is not None and h != expected:
            raise ValueError('Input identity mismatch: ' + str(path))
        if self.inputs.setdefault(str(path), h) != h:
            raise ValueError('Input changed: ' + str(path))
        return h

    def load_json(self, path, digest):
        self.pin(path, digest)
        return json.loads(path.read_text())

    def load(self):
        self.memory('load-start')
        self.context = self.load_json(self.main / 'fixtures/public/e1s-native-source-ports/source-context.json',
                                     '3b87fdab0a2953438c7fd78f420e138604c258b5d09b97c444187737347df8dc')
        self.source = Path(self.context['source_root'])
        self.manifest = self.load_json(Path(self.context['source_manifest']), self.context['source_manifest_sha256'])
        self.base_manifest = self.load_json(Path(self.context['base_manifest']), self.context['base_manifest_sha256'])
        self.config = self.load_json(self.main / 'fixtures/public/e1s-development-configs/generated-development.json',
                                    '6b0ac2c8e82b2837a94f628ee5c291105559a0607e3febac56fc7e7b6527cf9a')
        self.namespace = self.load_json(self.main / 'fixtures/public/e1s-development-exports/qualified-namespace.json',
                                       '96694dccbb3723199ea0f27893ee7e40b33373a916c4a500a91af5e89e87d5a5')
        raw_binding = self.namespace['raw_namespace_descriptor']
        self.raw = self.load_json(Path(raw_binding['path']), raw_binding['sha256'])
        producer_binding = self.namespace['producer_map']
        self.producers = self.load_json(Path(producer_binding['path']), producer_binding['sha256'])
        if self.config['source_manifest_sha256'] != self.context['base_manifest_sha256'] or self.raw['source_manifest_sha256'] != self.context['base_manifest_sha256']:
            raise ValueError('Native producer base context mismatch')
        changed = {p for p in self.manifest if self.manifest[p] != self.base_manifest.get(p)}
        if changed != set(self.context['changed_files']) or len(self.manifest) != len(self.base_manifest):
            raise ValueError('Derived source composition differs from accepted port set')
        if tuple(self.config[k] for k in ['machine', 'architecture', 'kernel', 'platform']) != ('E1S', 'ARM64', 'DEVELOPMENT', 'iPhoneOS'):
            raise ValueError('Wrong native selection')
        self.compiler = self.main / 'artifacts/xnu-compiler-cxx-storage/source-build-session2/clang'
        self.pin(self.compiler, '7972eb2820ae25b5bedff1ea954cef9e9a0e4a15c7a8e440628e8b6540fafc82')
        feature_path = self.main / 'worktrees/str-013-e1s-development-assym-20261106/artifacts/e1s-development-assym/generate-1/compiler-feature-probe.json'
        self.feature = self.load_json(feature_path, '01d70064392c72114d1ee10a9a5c55ceaa2b7bd3ce1a735a9b4fc06fe47f8332')
        feature = self.feature
        if (feature['schema'] != 'e1s-native-compiler-feature-probe-v1'
                or feature['compiler'] != {'path': str(self.compiler), 'sha256': sha(self.compiler)}
                or feature['argv'] != [str(self.compiler), '-E', '-fbounds-attributes', '/dev/null']
                or feature['source_rule']['sha256'] != self.manifest['makedefs/MakeInc.def']
                or not feature['normal_exit'] or not feature['measured'] or feature['stop_reason'] is not None
                or feature['BOUND_CHECKS'] != int(feature['exit_code'] == 0)):
            raise ValueError('Unqualified shared native compiler feature receipt')
        for name in ['stdout', 'stderr']:
            self.pin(Path(feature[name]['path']), feature[name]['sha256'])
        self.feature_binding = {'path': str(feature_path), 'sha256': sha(feature_path)}
        self.pin(Path(__file__))
        self.report_out.mkdir(parents=True)
        if self.reuse:
            self.pin(self.out / 'prepare.py')
        self.config_roots = {}
        for component, data in self.config['components'].items():
            root = self.out / 'configuration' / component / 'DEVELOPMENT'
            root.mkdir(parents=True, exist_ok=self.reuse)
            for name, digest in data['generated_files'].items():
                original = within(Path(data['root']), name)
                self.pin(original, digest)
                copied = within(root, name)
                copied.parent.mkdir(parents=True, exist_ok=True)
                if not self.reuse:
                    shutil.copyfile(original, copied)
                self.pin(copied, digest)
                self.actual_generated[str(copied)] = {'kind': 'actual-config-product', 'producer': 'STR-009/STR-004', 'sha256': digest}
            self.config_roots[component] = root
        for destination, digest in self.raw['raw_export_files'].items():
            original = Path(self.raw['raw_export_root']).parent / destination
            self.pin(original, digest)
            copied = within(self.out, destination)
            copied.parent.mkdir(parents=True, exist_ok=True)
            if not self.reuse:
                shutil.copyfile(original, copied)
            self.pin(copied, digest)
        # Import actual generated header bytes by their typed producer identities,
        # not as raw source. Missing producers remain absent.
        self.generated_header_imports = []
        for row in self.producers['rows']:
            if 'product' not in row:
                continue
            product = row['product']
            original = Path(product['path'])
            self.pin(original, product['sha256'])
            copied = within(self.out, row['destination'])
            if copied.exists() and not self.reuse:
                raise ValueError('Generated/raw header collision')
            copied.parent.mkdir(parents=True, exist_ok=True)
            if not self.reuse:
                shutil.copyfile(original, copied)
            self.pin(copied, product['sha256'])
            self.generated_header_imports.append({'destination': str(copied), 'producer': row})
        self.pending_headers = [r for r in self.producers['rows'] if 'product' not in r]
        self.generated_sources = {}
        separate = self.producers['separate_generated_TUs']
        for product in [separate['version'], *separate['syscalls']]:
            path = Path(product['path'])
            self.pin(path, product['sha256'])
            self.generated_sources[path.name] = product
        oldshim = self.main / 'artifacts/xnu-kernel-objects/compile-session2/host-commands.mk'
        expected = '# Explicit standalone Linux query inputs; no SDK contents.\nTR = tr\nBASH = bash\nECHO = echo\nPRINTF = printf\nSUPPORTED_EMBEDDED_PLATFORMS = iPhoneOS AppleTVOS WatchOS tvOS BridgeOS\n_v =\n'
        if oldshim.read_text() != expected:
            raise ValueError('Native Linux query shim changed')
        self.pin(oldshim)
        self.shim = self.out / 'host-commands.mk'
        if self.reuse:
            if self.shim.read_text() != expected:
                raise ValueError('Retained component-stage shim changed')
        else:
            self.shim.write_text(expected)
        self.pin(self.shim)
        for tool in ['/usr/bin/make', '/bin/bash', '/usr/bin/tr']:
            self.pin(Path(tool).resolve())
        for name in ['makedefs/MakeInc.def', 'makedefs/MakeInc.rule', 'makedefs/MakeInc.kernel']:
            self.pin(self.source / name, self.manifest[name])
        self.sanitizer_setup()
        tool_descriptor = self.main / 'fixtures/public/xnu-kernel-direct-tail/qualified-component.json'
        self.pin(tool_descriptor)
        tool = json.loads(tool_descriptor.read_text())['tool']
        self.seg_hack = self.main / tool['tool']
        self.pin(self.seg_hack, tool['sha256'])
        self.pin(self.main / tool['source'], tool['source_sha256'])
        self.pin(self.source / 'SETUP/setsegname/setsegname.c', tool['original_sha256'])
        self.segment_tool = {'path': str(self.seg_hack), 'sha256': tool['sha256'],
                             'source_sha256': tool['original_sha256'], 'executed': False}

    def sanitizer_setup(self):
        makefile = self.source / 'san/memory/Makefile'
        text = makefile.read_text()
        if '$(SOURCE)/kasan-blacklist $(SOURCE)/ubsan-blacklist $(SOURCE)/kasan-blacklist-%' not in text:
            raise ValueError('Genuine sanitizer setup prerequisites changed')
        self.pin(makefile, self.manifest['san/memory/Makefile'])
        sources = [self.source / 'san/memory' / n for n in ['kasan-blacklist', 'ubsan-blacklist', 'kasan-blacklist-arm64']]
        validator = self.source / 'san/tools/validate_blacklist.sh'
        for p in [*sources, validator]:
            self.pin(p, self.manifest[str(p.relative_to(self.source))])
        target = self.out / 'san/kasan-blacklist-arm64'
        target.parent.mkdir(exist_ok=self.reuse)
        argv = ['/usr/bin/sed', '-e', 's,^src:\\./,src:' + str(self.source) + '/,', *map(str, sources)]
        self.pin(Path('/usr/bin/sed'))
        if self.reuse:
            if self.commands[0]['argv'] != argv or self.commands[0]['exit_code'] != 0:
                raise ValueError('Retained actual sanitizer command context differs')
            expected = re.sub(rb'^src:\./', ('src:' + str(self.source) + '/').encode(), b''.join(p.read_bytes() for p in sources), flags=re.M)
            if target.read_bytes() != expected or self.commands[1]['exit_code'] != 0:
                raise ValueError('Retained actual sanitizer body/validation differs')
            self.pin(target)
            self.sanitizer = {'path': str(target), 'sha256': sha(target), 'source_rule': str(makefile),
                              'source_rule_sha256': sha(makefile), 'derived_source_path_rewrite': str(self.source),
                              'source_order': list(map(str, sources)), 'actual_generator_exits': [0, 0],
                              'reused_actual_setup_from': str(self.out), 'generator_reexecuted': False}
            return
        generated = subprocess.run(argv, capture_output=True, timeout=10)
        self.commands.append({'argv': argv, 'cwd': str(self.out), 'exit_code': generated.returncode,
                              'stdout_saved_as': str(target)})
        if generated.returncode:
            raise ValueError('Genuine sanitizer sed rule failed')
        target.write_bytes(generated.stdout)
        argv = ['/bin/bash', str(validator), str(target)]
        checked = subprocess.run(argv, cwd=self.out, env={'PATH': '/usr/bin:/bin'}, capture_output=True, timeout=10)
        log = self.out / 'san/validation.log'
        log.write_bytes(checked.stdout + checked.stderr)
        self.commands.append({'argv': argv, 'cwd': str(self.out), 'env': {'PATH': '/usr/bin:/bin'},
                              'exit_code': checked.returncode, 'diagnostics': str(log)})
        if checked.returncode:
            raise ValueError('Genuine sanitizer validation failed')
        self.pin(target)
        self.sanitizer = {'path': str(target), 'sha256': sha(target), 'source_rule': str(makefile),
                          'source_rule_sha256': sha(makefile), 'derived_source_path_rewrite': str(self.source),
                          'source_order': list(map(str, sources)), 'actual_generator_exits': [generated.returncode, checked.returncode]}

    def args(self, component):
        parent = self.out / 'configuration' / component
        return ['SRCROOT=' + str(self.source), 'SOURCE_DIR=' + str(self.source),
                'OBJROOT=' + str(self.out), 'OBJPATH=' + str(self.out / 'configuration'),
                'TARGET=' + str(parent), 'SOURCE=' + str(self.source / component) + '/',
                'RELATIVE_SOURCE_PATH=./' + component,
                'CURRENT_ARCH_CONFIG=ARM64', 'CURRENT_ARCH_CONFIG_LC=arm64',
                'CURRENT_KERNEL_CONFIG=DEVELOPMENT', 'CURRENT_KERNEL_CONFIG_LC=development',
                'CURRENT_MACHINE_CONFIG=E1S', 'CURRENT_MACHINE_CONFIG_LC=e1s', 'PLATFORM=iPhoneOS',
                'SDKROOT=' + str(self.out / 'unavailable-sdk'), 'CC=' + str(self.compiler), 'CXX=' + str(self.compiler),
                'SEG_HACK=' + str(self.seg_hack),
                'MakeInc_cmd=' + str(self.shim), 'ARCH_STRING_FOR_CURRENT_MACHINE_CONFIG=arm64',
                'BUILD_WERROR=0', 'BUILD_LTO=0', 'DEPLOYMENT_TARGET_FLAGS=-target arm64-apple-ios16.5 -DXNU_TARGET_OS_IOS',
                'SEED_DEFINES=-DXNU_NO_TYPE_BUILTINS=0', 'SHELL=/bin/bash', 'LOGCOLORS=n']

    def run_query(self, query, component, variant, label, cwd):
        self.memory('before-Make-' + label)
        argv = ['/usr/bin/make', '--no-print-directory', '-rR', '-f', str(query), *self.args(component),
                'BOUND_CHECKS=' + str(variant), 'e1s_body_query']
        env = {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'LANG': 'C'}
        start = time.monotonic()
        stdout = self.report_out / 'queries' / (label + '-bounds' + str(variant) + '.stdout.txt')
        stdout.parent.mkdir(parents=True, exist_ok=True)
        stderr = stdout.with_suffix('.stderr.txt')
        command = {'argv': argv, 'cwd': str(cwd), 'env': env, 'exit_code': None,
                   'stdout': str(stdout), 'stderr': str(stderr)}
        self.commands.append(command)
        def make_limits():
            resource.setrlimit(resource.RLIMIT_AS, (256 * 1024**2, 256 * 1024**2))
        with stdout.open('w') as out, stderr.open('w') as err:
            p = subprocess.run(argv, cwd=cwd, env=env, stdout=out, stderr=err, timeout=30, preexec_fn=make_limits)
        self.memory('after-Make-' + label)
        command.update(exit_code=p.returncode, wall_seconds=time.monotonic() - start)
        diagnostic = stderr.read_text()
        if p.returncode or diagnostic.strip():
            raise ValueError('Source-only Make query failed: ' + label + ': ' + diagnostic[-2000:])
        with stdout.open() as f:
            includes = [line.strip().split('|', 1)[1] for line in f if line.startswith('E1SBODY_INCLUDES|')]
        if len(includes) != 1:
            raise ValueError('Missing Make include provenance')
        for name in includes[0].split():
            path = Path(name) if Path(name).is_absolute() else cwd / name
            if path.is_relative_to(self.source):
                self.pin(path, self.manifest[str(path.relative_to(self.source))])
            elif str(path) not in self.inputs:
                raise ValueError('Unqualified Make include: ' + str(path))
        return stdout

    @staticmethod
    def variables(path):
        values = {}
        with path.open() as f:
            for line in f:
                if line.startswith('E1SBODY_VAR|'):
                    _, key, value = line.rstrip('\n').split('|', 2)
                    values[key] = value
        if set(values) != set(KEYS):
            raise ValueError('Incomplete component variable inventory')
        return values

    @staticmethod
    def records(path):
        current = None
        with path.open() as f:
            for line in f:
                if line.startswith('E1SBODY_SOURCE|'):
                    if current is not None:
                        yield current
                    _, target, source = line.rstrip('\n').split('|', 2)
                    current = {'target': target, 'source': source, 'steps': {}}
                elif line.startswith('E1SBODY_STEP|'):
                    _, target, index, value = line.rstrip('\n').split('|', 3)
                    if current is None or target != current['target']:
                        raise ValueError('Interleaved actual Make recipe stream')
                    current['steps'][index] = value
        if current is not None:
            yield current

    def inventory_component(self, component, root):
        makefile = root / 'Makefile'
        text = makefile.read_text()
        blocks = recipe_blocks(text)
        source_expressions = {}
        recipes = {}
        for target, block in blocks.items():
            compiles = [line for line in block['recipe'] if re.match(r'^\$[({][CPS]_RULE_1A', line)]
            if not compiles:
                continue
            if len(compiles) != 1:
                raise ValueError('Multiple primary recipes: ' + component + '/' + target)
            candidates = [p for expression in block['prerequisites'] for p in expression.split()
                          if re.search(r'\.(?:c|cpp|cp|s|S)$', p)]
            if len(candidates) != 1:
                raise ValueError('Ambiguous genuine source prerequisite: ' + component + '/' + target)
            source_expressions[target] = candidates[0]
            recipes[target] = block
        query = self.out / 'queries' / (component + '.mk')
        query.parent.mkdir(exist_ok=True)
        lines = ['include ' + str(makefile)]
        lines += ['$(info E1SBODY_VAR|' + key + '|$(' + key + '))' for key in KEYS]
        for target, expression in source_expressions.items():
            lines.append('$(info E1SBODY_SOURCE|' + target + '|' + expression + ')')
            basename = Path(expression).name
            lines += ['$(eval @ := ' + target + ')', '$(eval <F := ' + basename + ')']
            for index, recipe in enumerate(recipes[target]['recipe']):
                expanded_recipe = re.sub(r'\$[({][CPS]_RULE_1B(?:_[A-Z]+)?[)}]', basename, recipe)
                lines.append('$(info E1SBODY_STEP|' + target + '|' + str(index) + '|' + expanded_recipe + ')')
        lines += ['$(info E1SBODY_INCLUDES|$(MAKEFILE_LIST))', '.PHONY: e1s_body_query', 'e1s_body_query: ;']
        query.write_text('\n'.join(lines) + '\n')
        self.pin(query)
        variants = {}
        outputs = {}
        for bounds in [0, 1]:
            outputs[str(bounds)] = self.run_query(query, component, bounds, component, root)
            variants[str(bounds)] = {'values': self.variables(outputs[str(bounds)]),
                                    'actual_recipe_stream': str(outputs[str(bounds)])}
        selection_keys = ['OBJS', 'LIBOBJS', 'CFILES', 'COBJS', 'CXXFILES', 'CXXOBJS', 'SFILES', 'SOBJS', 'HIB_FILES', 'KLD_FILES']
        if any(variants['0']['values'][k] != variants['1']['values'][k] for k in selection_keys):
            raise ValueError('Source graph selection depends on compiler-query feature variant')
        selected = variants['0']['values']['OBJS'].split()
        if len(selected) != len(set(selected)):
            raise ValueError('Duplicate selected object name')
        self.components[component] = {'makefile': str(makefile), 'makefile_sha256': sha(makefile),
                                      'ordered_OBJS': selected, 'ordered_LIBOBJS': variants['0']['values']['LIBOBJS'].split(),
                                      'query_variants': variants, 'source_selection_equal_between_variants': True,
                                      'filelist_recipe_source': text[text.index('$(COMPONENT).filelist:'):text.index('ifeq ($(RC_ProjectName)')],
                                      'selected_feature_BOUND_CHECKS': self.feature['BOUND_CHECKS']}
        selected_set = set(selected)
        rows_by_target = {}
        for zero, one in zip_longest(self.records(outputs['0']), self.records(outputs['1'])):
            self.memory('recipe-' + component)
            if zero is None or one is None or (zero['target'], zero['source']) != (one['target'], one['source']):
                raise ValueError('Source/target recipe selection differs between actual query variants')
            target = zero['target']
            if target not in selected_set:
                continue
            if target not in recipes or target in rows_by_target:
                raise ValueError('Selected object has no genuine source/recipe: ' + component + '/' + target)
            expression = zero['source']
            source = Path(expression) if Path(expression).is_absolute() else root / expression
            source = source.resolve()
            row = {'id': component + '/' + target, 'component': component, 'target': target,
                   'selection_index': selected.index(target), 'original_source_expression': source_expressions[target],
                   'source': str(source), 'original_recipe_lines': recipes[target]['recipe'],
                   'expanded_steps_by_query_BOUND_CHECKS': {'0': zero['steps'], '1': one['steps']},
                   'selected_expanded_steps': (zero if self.feature['BOUND_CHECKS'] == 0 else one)['steps'],
                   'compiler_feature_decision_qualified': True, 'compiler_vector_input_closure_complete': False, 'object_compiled': False}
            row['language'] = 'c++' if source.suffix in ('.cp', '.cpp') else 'asm' if source.suffix in ('.s', '.S') else 'c'
            compiles = []
            for step in row['selected_expanded_steps'].values():
                argv = shlex.split(step)
                if argv and argv[0] == str(self.compiler):
                    compiles.append(argv)
            if len(compiles) != 1 or '-c' not in compiles[0]:
                raise ValueError('Selected recipe has no unique genuine compiler vector: ' + row['id'])
            if not any((Path(word) if Path(word).is_absolute() else root / word).resolve() == source for word in compiles[0] if not word.startswith('-')):
                raise ValueError('Compiler vector does not name selected source: ' + row['id'])
            row['selected_compiler_argv'] = compiles[0]
            if source.is_relative_to(self.source):
                relative = str(source.relative_to(self.source))
                row.update(source_kind='actual-native-derived-source', source_sha256=self.pin(source, self.manifest[relative]),
                           accepted_source_port=relative in self.context['changed_files'])
            elif str(source) in self.actual_generated:
                row.update(source_kind='actual-config-product', source_sha256=self.actual_generated[str(source)]['sha256'])
            elif source.name in self.generated_sources:
                row.update(source_kind='actual-separate-producer-needs-placement', actual_producer=self.generated_sources[source.name],
                           expected_Make_path_not_materialized=True)
            else:
                row.update(source_kind='pending-genuine-generated-producer', source_sha256=None)
            recipe_path = self.out / 'recipes' / component / (target + '.json')
            write(recipe_path, row)
            light = {k: v for k, v in row.items() if k not in ['expanded_steps_by_query_BOUND_CHECKS', 'selected_expanded_steps', 'selected_compiler_argv', 'original_recipe_lines']}
            light['recipe'] = {'path': str(recipe_path), 'sha256': sha(recipe_path)}
            rows_by_target[target] = light
        if set(rows_by_target) != selected_set:
            raise ValueError('Missing selected recipe records in actual Make stream')
        self.rows.extend(rows_by_target[target] for target in selected)

    def restore_components(self):
        """Consume completed actual component facts; never rerun their Make queries."""
        for component, root in self.config_roots.items():
            self.memory('restore-' + component)
            variants = {}
            for bounds in [0, 1]:
                path = self.out / 'queries' / (component + '-bounds' + str(bounds) + '.stdout.txt')
                self.pin(path)
                variants[str(bounds)] = {'values': self.variables(path), 'actual_recipe_stream': str(path)}
            for key in ['OBJS', 'LIBOBJS', 'CFILES', 'COBJS', 'CXXFILES', 'CXXOBJS', 'SFILES', 'SOBJS', 'HIB_FILES', 'KLD_FILES']:
                if variants['0']['values'][key] != variants['1']['values'][key]:
                    raise ValueError('Retained actual source selection is inconsistent')
            selected = variants['0']['values']['OBJS'].split()
            if len(selected) != len(set(selected)):
                raise ValueError('Duplicate retained selected object')
            text = (root / 'Makefile').read_text()
            self.components[component] = {'makefile': str(root / 'Makefile'), 'makefile_sha256': sha(root / 'Makefile'),
                'ordered_OBJS': selected, 'ordered_LIBOBJS': variants['0']['values']['LIBOBJS'].split(),
                'query_variants': variants, 'source_selection_equal_between_variants': True,
                'filelist_recipe_source': text[text.index('$(COMPONENT).filelist:'):text.index('ifeq ($(RC_ProjectName)')],
                'selected_feature_BOUND_CHECKS': self.feature['BOUND_CHECKS'], 'Make_requery_performed': False}
            for index, target in enumerate(selected):
                recipe = self.out / 'recipes' / component / (target + '.json')
                self.pin(recipe)
                row = json.loads(recipe.read_text())
                if (row['id'], row['selection_index']) != (component + '/' + target, index):
                    raise ValueError('Retained recipe selection/order differs')
                if row['selected_expanded_steps'] != row['expanded_steps_by_query_BOUND_CHECKS'][str(self.feature['BOUND_CHECKS'])]:
                    raise ValueError('Retained recipe selected wrong actual compiler feature')
                if row['source_kind'] == 'actual-native-derived-source':
                    source = Path(row['source'])
                    self.pin(source, self.manifest[str(source.relative_to(self.source))])
                    if row['source_sha256'] != sha(source):
                        raise ValueError('Retained source identity differs')
                light = {k: v for k, v in row.items() if k not in ['expanded_steps_by_query_BOUND_CHECKS', 'selected_expanded_steps', 'selected_compiler_argv', 'original_recipe_lines']}
                light['recipe'] = {'path': str(recipe), 'sha256': sha(recipe)}
                self.rows.append(light)

    def tails(self):
        path = self.source / 'makedefs/MakeInc.kernel'
        text = path.read_text()
        matches = re.findall(r'(?m)^([A-Za-z_][A-Za-z0-9_]*\.o):[ \t]*(\$\((?:SRCROOT|OBJPATH)\)/[^\s]+\.c)[ \t]*$', text)
        if {name for name, _ in matches} != {'version.o', 'nonlto.o', 'lastkerneldataconst.o', 'lastkernelconstructor.o'}:
            raise ValueError('Actual direct-tail source rule changed')
        output = []
        for name, expression in matches:
            header = next(line for line in text.splitlines() if re.match(re.escape(name) + r':[ \t]*' + re.escape(expression) + r'$', line))
            following = text.split(header, 1)[1].splitlines()[1:]
            recipe = []
            for line in following:
                if not line.startswith('\t'):
                    break
                recipe.append(line.strip())
            source = expression.replace('$(SRCROOT)', str(self.source)).replace('$(OBJPATH)', str(self.out / 'configuration'))
            row = {'id': 'kernel/' + name, 'target': name, 'original_source_expression': expression,
                   'prospective_Make_source': source, 'original_recipe_lines': recipe,
                   'source_rule': str(path), 'source_rule_sha256': sha(path), 'compiler_or_postprocessor_executed': False}
            if name == 'version.o':
                row['actual_separate_producer'] = self.generated_sources['version.c']
            else:
                row['source_sha256'] = self.pin(Path(source), self.manifest[str(Path(source).relative_to(self.source))])
            if name == 'lastkernelconstructor.o':
                row['original_profile_removal'] = 'lastkernelconstructor.o_CFLAGS_RM = -fprofile-instr-generate'
                if row['original_profile_removal'] not in text:
                    raise ValueError('Constructor source policy changed')
            output.append(row)
        write(self.report_out / 'direct-tails.json', output)
        self.query_tails_and_link(output, text)
        return output

    def query_tails_and_link(self, tails, kernel_text):
        root = self.out / 'configuration/kernel/DEVELOPMENT'
        root.mkdir(parents=True, exist_ok=self.reuse)
        query = self.report_out / 'queries/kernel.mk'
        query.parent.mkdir(parents=True, exist_ok=True)
        cmdfile = self.source / 'makedefs/MakeInc.cmd'
        self.pin(cmdfile, self.manifest['makedefs/MakeInc.cmd'])
        platform = re.findall(r'^SUPPORTED_PLATFORMS :=.*$', cmdfile.read_text(), re.M)
        if len(platform) != 1:
            raise ValueError('Genuine platform support expression changed')
        lines = ['include ' + str(self.shim), platform[0],
                 'include ' + str(self.source / 'makedefs/MakeInc.def'),
                 'include ' + str(self.source / 'makedefs/MakeInc.rule'),
                 'include ' + str(self.source / 'makedefs/MakeInc.kernel')]
        for row in tails:
            lines += ['$(eval @ := ' + row['target'] + ')', '$(eval < := ' + row['prospective_Make_source'] + ')']
            for i, recipe in enumerate(row['original_recipe_lines']):
                lines.append('$(info E1STAIL|' + row['target'] + '|' + str(i) + '|' + recipe + ')')
        link = next(line.strip() for line in kernel_text.splitlines()
                    if '$(LD) $(LDFLAGS_KERNEL) $(LDFLAGS_KERNEL_ONLY) -filelist link.filelist version.o' in line)
        prerequisite = next(line.split(':', 1)[1].strip() for line in kernel_text.splitlines()
                            if line.startswith('$(TARGET)/$(KERNEL_FILE_NAME).unstripped:'))
        lines += ['$(eval @ := ' + str(root / 'kernel.unstripped') + ')', '$(eval + := ' + prerequisite + ')',
                  '$(info E1SLINK|DRIVER|' + link + ')', '$(info E1SLINK|PREREQUISITES|' + prerequisite + ')']
        for key in ['LDFLAGS_KERNEL', 'LDFLAGS_KERNEL_ONLY', 'LD_KERNEL_LIBS', 'LD_KERNEL_ARCHIVES', 'LDFILES_KERNEL_ONLY', 'USE_LTO']:
            lines.append('$(info E1SLINK|' + key + '|$(' + key + '))')
        lines += ['$(info E1SBODY_INCLUDES|$(MAKEFILE_LIST))', '.PHONY: e1s_body_query', 'e1s_body_query: ;']
        query.write_text('\n'.join(lines) + '\n'); self.pin(query)
        variants = {}
        for bounds in [0, 1]:
            stdout = self.run_query(query, 'kernel', bounds, 'kernel', root)
            steps, link_values = {}, {}
            with stdout.open() as stream:
                for line in stream:
                    if line.startswith('E1STAIL|'):
                        _, target, index, value = line.rstrip('\n').split('|', 3)
                        steps.setdefault(target, {})[index] = value
                    elif line.startswith('E1SLINK|'):
                        _, key, value = line.rstrip('\n').split('|', 2); link_values[key] = value
            if set(steps) != {r['target'] for r in tails} or link_values['USE_LTO'] == '1':
                raise ValueError('Incomplete native direct-tail/non-LTO linker query')
            variants[str(bounds)] = {'direct_tail_steps': steps, 'link': link_values}
        for row in tails:
            row['expanded_steps_by_query_BOUND_CHECKS'] = {str(b): variants[str(b)]['direct_tail_steps'][row['target']] for b in [0, 1]}
            row['selected_expanded_steps'] = variants[str(self.feature['BOUND_CHECKS'])]['direct_tail_steps'][row['target']]
            compiles = [shlex.split(step) for step in row['selected_expanded_steps'].values()
                        if step.lstrip().startswith(str(self.compiler) + ' ')]
            if len(compiles) != 1:
                raise ValueError('Incomplete selected direct-tail compiler vector')
            row['selected_compiler_argv'] = compiles[0]
            row['postprocess_tool_binding'] = self.segment_tool if row['target'] == 'lastkernelconstructor.o' else None
        self.link = {'original_non_LTO_driver_recipe': link, 'original_prerequisite_expression': prerequisite,
                     'query_variants': variants, 'selected': variants[str(self.feature['BOUND_CHECKS'])]['link'],
                     'actual_linker_or_backend_probe_executed': False, 'link_input_closure_complete': False,
                     'private37_ABI_unchanged': True}
        write(self.report_out / 'direct-tails.json', tails)
        write(self.report_out / 'link-driver.json', self.link)

    def finish(self, tails):
        self.memory('finish')
        for path, digest in self.inputs.items():
            if sha(path) != digest:
                raise ValueError('Input changed during source query: ' + path)
        result = {'schema': 'e1s-native-development-body-graph-v1', 'kind': 'host-test', 'origin': 'local-host',
                  'outcome': 'pass', 'task': 'STR-016', 'owner': OWNER, 'source_root': str(self.source),
                  'source_manifest_sha256': self.context['source_manifest_sha256'],
                  'base_source_manifest_sha256': self.context['base_manifest_sha256'],
                  'base_source_profile_sha256': self.context['base_profile_sha256'],
                  'machine': 'E1S', 'architecture': 'ARM64', 'kernel': 'DEVELOPMENT', 'platform': 'iPhoneOS',
                  'component_count': len(self.components), 'selected_component_objects': len(self.rows),
                  'status_counts': dict(Counter(r['source_kind'] for r in self.rows)),
                  'components': self.components, 'objects': self.rows, 'direct_tails': tails,
                  'generated_header_imports': self.generated_header_imports, 'pending_generated_headers': self.pending_headers,
                  'feature_decision': {'status': 'consumed-shared-actual-SR13-receipt', 'receipt': self.feature_binding,
                                       'BOUND_CHECKS': self.feature['BOUND_CHECKS'], 'no_probe_executed_by_STR016': True,
                                       'both_query_variants_preserved': True, 'full_compiler_input_closure_qualified': False},
                  'mandatory_sanitizer_rule': self.sanitizer, 'link_driver': self.link,
                  'segment_postprocessor': self.segment_tool, 'component_context_root': str(self.out),
                  'reused_completed_component_stage': self.reuse, 'component_queries_reexecuted': not self.reuse,
                  'SDK_provided': False, 'target_tools_executed': False, 'old_objects_adopted': False,
                  'full_kernel_or_private37_ABI_or_runtime_or_hardware_qualified': False}
        write(self.report_out / 'body-graph.json', result)
        write(self.report_out / 'commands.json', self.commands)
        write(self.report_out / 'input-bindings.json', self.inputs)
        write(self.report_out / 'memory-samples.json', {'parent_RSS_cap_bytes': 256 * 1024**2,
              'parent_AS_cap': None, 'serial_Make_AS_cap_bytes': 256 * 1024**2,
              'work_boundary_checks': self.memory_checks, 'samples': self.memory_samples,
              'aggregate_child_RSS_peak_not_sampled': True})
        write(self.report_out / 'preparation-result.json', {'outcome': 'pass', 'objects': len(self.rows),
              'component_count': len(self.components), 'direct_tails': len(tails),
              'status_counts': result['status_counts'], 'actual_Make_commands': len(self.commands),
              'controller_status': [line for line in Path('/proc/self/status').read_text().splitlines() if line.startswith(('VmRSS:', 'VmHWM:'))]})
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--main', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--reuse-components', type=Path)
    args = parser.parse_args()
    available = int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:'))) * 1024
    if available < 4 * 1024**3:
        raise ValueError('Require at least4GiB MemAvailable for source queries')
    start = time.monotonic()
    g = Graph(args.main, args.out, args.reuse_components)
    try:
        g.load()
        if g.reuse:
            g.restore_components()
        else:
            for component, root in g.config_roots.items():
                g.inventory_component(component, root)
                print(json.dumps({'component': component, 'selected_objects': len(g.components[component]['ordered_OBJS']),
                                  'source_statuses': dict(Counter(r['source_kind'] for r in g.rows if r['component'] == component))}), flush=True)
        tails = g.tails()
        result = g.finish(tails)
        print(json.dumps({'outcome': 'pass', 'objects': result['selected_component_objects'],
                          'status_counts': result['status_counts'], 'wall_seconds': time.monotonic() - start}))
    except Exception as error:
        if g.report_out.exists():
            write(g.report_out / 'preparation-result.json', {'outcome': 'fail', 'error': type(error).__name__ + ': ' + str(error),
                                                     'wall_seconds': time.monotonic() - start})
            write(g.report_out / 'commands.json', g.commands)
            write(g.report_out / 'memory-samples.json', {'work_boundary_checks': g.memory_checks, 'samples': g.memory_samples})
        raise


if __name__ == '__main__':
    main()
