#!/usr/bin/env python3
"""Audit genuine selected export gaps without weakening export or feature policy."""
from __future__ import annotations
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shutil
import subprocess
import sys

PIN = 'c54f35ca767986246321eb901baf8f5ff7923f6a'
DONOR = 'c8860decc62c6d6180e609036d027a2997972420'
SOURCE = 'artifacts/xnu-prepare/e1s-dependency-source-session1/xnu'
NATIVE = 'worktrees/krn-024-20261105/artifacts/kernel-provider-link/native-session2/report.json'
CORRECTED = 'worktrees/krn-024-20261105/artifacts/kernel-provider-link/native-session3/report.json'
PROFILE = 'artifacts/xnu-compiler-cxx-storage/full-profile-session2/report.json'
NM = 'Android/Sdk/ndk/28.2.13676358/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-nm'
REQUIRED = {'CONFIG_PMAP_PPL': '1', 'NOS_ARM_PMAP': '1', 'XNU_TARGET_OS_IOS': '1',
            'XNU_NO_TYPE_BUILTINS': '0'}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def require(value, message):
    if not value:
        raise ValueError(message)


class Audit:
    def __init__(self, args):
        self.main = args.main_root.resolve()
        self.wt = Path(__file__).resolve().parents[2]
        require(args.run and Path(args.run).name == args.run, 'Fresh single-component run name required')
        self.out = self.wt / 'artifacts/kernel-export-gaps' / args.run
        self.out.mkdir(parents=True, exist_ok=False)
        self.kernel = self.main / SOURCE
        self.env = dict(os.environ, GIT_NO_LAZY_FETCH='1', GIT_OPTIONAL_LOCKS='0')
        self.fixture = read(self.wt / 'fixtures/public/kernel-export-gaps/inputs.json')
        self.report = dict(kind='host-test', origin='local-host', outcome='fail',
            recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), commands=[], checks=[],
            source_inputs={}, tools_sha256={}, device_executed=False, sdk_installed=False,
            full_kernel_qualified=False, apple_private_abi_qualified=False, native_device_qualified=False,
            production_exports_removed=[], production_flags_changed=[], replacement_objects=[],
            summary='Selected native export diagnosis; no required export or feature removed',
            startup_resource_maxrss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            startup_process_memory=[line for line in Path('/proc/self/status').read_text().splitlines() if line.startswith(('VmPeak:', 'VmHWM:', 'VmRSS:'))])

    def rel(self, p):
        return str(Path(p).resolve().relative_to(self.main))

    def save(self, name, data):
        p = self.out / name
        p.write_text(json.dumps(data, indent=2) + '\n')
        return p

    def check(self, name, valid, **detail):
        self.report['checks'].append(dict(name=name, pass_check=bool(valid), **detail))
        require(valid, name)

    def command(self, argv, name, cwd=None, expected=0):
        argv = list(map(str, argv))
        proc = subprocess.run(argv, cwd=cwd or self.main, env=self.env,
                              capture_output=True, timeout=90)
        out, err = self.out / (name + '.stdout.txt'), self.out / (name + '.stderr.txt')
        out.write_bytes(proc.stdout)
        err.write_bytes(proc.stderr)
        self.report['commands'].append(dict(argv=argv, cwd=str(cwd or self.main),
            exit_code=proc.returncode, stdout=self.rel(out), stderr=self.rel(err),
            max_child_rss_kib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss))
        require(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss <= 524288, 'Child RSS exceeded512MiB')
        if expected is not None:
            require(proc.returncode == expected, f'{name}: expected{expected}, observed{proc.returncode}')
        return proc.stdout.decode(errors='replace')

    def witness(self, path, expected=None):
        p = self.main / path
        actual = sha(p)
        if expected is not None:
            require(actual == expected, 'Changed input: ' + path)
        self.report['source_inputs'][path] = actual
        return p

    def reject(self, name, function):
        try:
            function()
        except ValueError as error:
            self.report.setdefault('negative_controls', []).append(dict(name=name, rejected=True, reason=str(error)))
        else:
            raise ValueError('Control unexpectedly accepted: ' + name)

    def parents(self):
        for name, digest in self.fixture['parents'].items():
            self.witness(name, digest)
        self.native = read(self.main / NATIVE)
        corrected = read(self.main / CORRECTED)
        self.check('actual-link-context-distinguishes-omitted-runtime',
            self.native['actual_link']['exit_code'] == 1 and not self.native['actual_link']['image_exists']
            and corrected['actual_link']['missing_cc_kext'] and not corrected['actual_link']['image_exists'])
        names = re.findall(r'^  "([^"]+)", referenced from:\n     -exported_symbol\[s_list\] command line option',
                           self.native['actual_link']['diagnostic'], re.M)
        self.names = set(self.fixture['observed_export_only_names'])
        self.check('exact37-observed-export-only-names', len(names) == 37 and set(names) == self.names)
        manifests = {}
        for name, value in self.native['graph'].items():
            manifests[name] = read(self.witness(value['path'], value['sha256']))
        rows = manifests['compiled-objects']
        deps = manifests['dependency-files']
        self.check('current-SGAP982-graph-and3156-dependencies', len(rows) == 982 and len(deps) == 3156)
        for row in rows:
            self.witness(row['output'], row['output_sha256'])
            self.witness(row['source'], row['source_sha256'])
        for name, digest in deps.items():
            self.witness(name, digest)
        self.check('all37-absent-from-actual-providers-and-consumers',
            not self.names.intersection(manifests['symbol-providers'])
            and not self.names.intersection(manifests['symbol-consumers']))
        self.rows = {r['id']: r for r in rows}
        self.report['graph'] = self.native['graph']
        self.report['actual_link_input'] = dict(path=NATIVE, sha256=sha(self.main / NATIVE),
            corrected_runtime_context=CORRECTED, missing_required_exports=sorted(self.names))
        ledger = read(self.main / 'state/lab.json')
        task = next(t for t in ledger['tasks'] if t['id'] == 'KRN-026')
        self.check('owned-task-and-preregistered-experiment', task['owner'] == 'codex-team-export-gaps-20261105-ba'
            and task['status'] == 'in_progress' and any(e['task'] == 'KRN-026' and e['status'] == 'planned'
            and e['owner'] == task['owner'] for e in ledger['experiments']))

    def select(self, name, extra=None):
        query = self.out / (name + '.mk')
        query.write_text('include ' + str(self.kernel / 'config/Makefile') + '\n'
            + ''.join('$(info EXPGAP|' + k + '|$(' + k + '))\n' for k in
                      ['EXPORTS_FILES', 'Kasan_EXPORTS', 'Kcov_EXPORTS', 'SYMBOL_COMPONENT_LIST'])
            + '\n.PHONY: s24_query\ns24_query: ;\n')
        args = self.native['link_query_argv'].copy()
        args[args.index('-f') + 1] = str(query)
        replacements = dict(OBJPATH=str(self.out / name), TARGET=str(self.out / name),
                            SOURCE=str(self.kernel / 'config') + '/', RELATIVE_SOURCE_PATH='./config')
        replacements.update(extra or {})
        args = [next((k + '=' + v for k, v in replacements.items() if a.startswith(k + '=')), a) for a in args]
        text = self.command(args, name + '-query')
        values = {line.split('|', 2)[1]: line.split('|', 2)[2].split() for line in text.splitlines() if line.startswith('EXPGAP|')}
        sources = [self.kernel / 'config' / n for n in values['EXPORTS_FILES']]
        sources += [Path(n) for k in ['Kasan_EXPORTS', 'Kcov_EXPORTS'] for n in values[k]]
        return values, sources

    def generate(self, name, sources):
        output = self.out / (name + '.exp')
        self.command(['sh', self.kernel / 'config/generate_linker_exports.sh', output, *sources], name + '-generate')
        return output

    def exports(self):
        values, sources = self.select('native')
        self.check('exact-native-selected-export-files', values['EXPORTS_FILES'] == self.native['metadata']['query_values']['EXPORTS_FILES'])
        for source in sources:
            self.witness(self.rel(source))
        output = self.generate('native', sources)
        original = self.main / NATIVE
        original = original.parent / 'stage/all-kpi.exp'
        self.check('fresh-required-export-bytes-identical', output.read_bytes() == original.read_bytes()
            and self.names <= set(output.read_text().splitlines()))
        positions = []
        for symbol in sorted(self.names):
            occurrences = [(self.rel(path), index) for path in sources
                           for index, line in enumerate(path.read_text().splitlines(), 1) if line == symbol]
            self.check('unique-native-origin-' + symbol, len(occurrences) == 1)
            positions.append(dict(symbol=symbol, export_file=occurrences[0][0], line=occurrences[0][1]))
        self.report['exports'] = dict(values=values, generated=self.rel(output), sha256=sha(output), symbols=positions,
            feature_filter='Native generator has no feature preprocessor; alias split and sort only')
        wrong_values, wrong_sources = self.select('wrong-arch', {'CURRENT_ARCH_CONFIG_LC': 'x86_64'})
        wrong = self.generate('wrong-arch', wrong_sources)
        self.reject('wrong-architecture-export-selection', lambda:
            require(self.names <= set(wrong.read_text().splitlines()), 'Different architecture hides35 required ARM64 exports'))
        require(wrong_values['EXPORTS_FILES'] != values['EXPORTS_FILES'], 'Wrong-arch control did not change recipe')
        donor = self.main / 'references/s24-port'
        patch_path = 'xnu/legacy-sweet-patches/0009-sweet-drop-apple-soc-only-exports.patch'
        text = self.command(['git', '-C', donor, 'show', DONOR + ':' + patch_path], 'pinned-donor-drop-patch')
        removed = {line[1:] for line in text.splitlines() if line.startswith('-_')}
        self.check('prohibited-donor-deletes-exactly37-required-exports', removed == self.names)
        negative_sources = []
        for path in sources:
            target = self.out / 'drop-control' / path.name
            target.parent.mkdir(exist_ok=True)
            target.write_text(''.join(line for line in path.read_text().splitlines(keepends=True) if line.strip() not in removed))
            negative_sources.append(target)
        negative = self.generate('drop-control', negative_sources)
        self.check('actual-donor-deletion-hides-all37', not self.names.intersection(negative.read_text().splitlines()))
        self.reject('drop-required-export-control', lambda: require(output.read_bytes() == negative.read_bytes(), 'Required native export bytes were removed'))
        self.report['negative_export_outputs'] = dict(wrong_architecture=self.rel(wrong), deleted_exports=self.rel(negative))

    def source(self):
        ref = self.main / 'references/apple-xnu'
        patterns = self.out / 'provider-patterns.txt'
        tokens = sorted({('IOUnifiedAddressTranslator' if 'IOUnifiedAddressTranslator' in n else n[1:]) for n in self.names})
        patterns.write_text('\n'.join(tokens) + '\n')
        self.command(['git', '-C', ref, 'grep', '-n', '-I', '-F', '-f', patterns, PIN, '--'], 'pinned-public-provider-inventory')
        paths = ['config/Makefile', 'config/generate_linker_exports.sh', 'config/Private.arm64.exports',
                 'config/Private.exports', 'osfmk/arm/pmap/pmap_cs.c', 'osfmk/arm/pmap/pmap_iommu.c',
                 'osfmk/conf/files.arm64', 'osfmk/vm/pmap.h', 'osfmk/x86_64/pmap.c']
        for index, name in enumerate(paths):
            text = self.command(['git', '-C', ref, 'show', PIN + ':' + name], 'pinned-source-' + str(index))
            prepared = self.kernel / name
            if name == 'osfmk/conf/files.arm64':
                self.witness(self.rel(prepared), self.fixture['prepared_files_arm64_sha256'])
                base_lines = [line for line in text.splitlines() if '/pmap/' in line]
                selected_lines = [line for line in prepared.read_text().splitlines() if '/pmap/' in line]
                self.check('donor-conf-preserves-all-public-pmap-selection-lines', base_lines == selected_lines)
                self.report['prepared_conf_note'] = 'Pinned base differs through existing donor additions/amcc exclusions; all six public pmap selection lines remain byte-identical. No new source correction.'
            else:
                self.check('prepared-source-matches-pin-' + name, text.encode() == prepared.read_bytes())
            self.witness(self.rel(prepared))
        self.report['source_pins'] = dict(xnu=PIN, donor=DONOR)
        self.report['source_findings'] = dict(
            IOUnifiedAddressTranslator='17 exports; no public class declaration, IIG or implementation found at exact pin',
            iommu_and_soc='18 exports; no public target implementation found at exact pin',
            pmap_queries='2 exported declarations; unsupported x86 bodies are not an ARM64 provider',
            original_placeholder_files={p: sha(self.kernel / p) for p in paths if p.endswith(('pmap_cs.c','pmap_iommu.c'))})

    def compile(self):
        profile = read(self.main / PROFILE)
        nm = Path.home() / NM
        compiler = self.main / self.native['compiler']['path']
        self.report['tools_sha256'].update({str(p): sha(p) for p in [compiler, nm, Path('/usr/bin/make'), Path('/usr/bin/sh')]})
        self.check('same-current-compiler', sha(compiler) == self.native['compiler']['sha256'])
        self.report['full_recipes'] = []
        for filename in ['pmap_cs', 'pmap_iommu']:
            name = 'osfmk/arm/pmap/' + filename + '.c'
            source = self.kernel / name
            recipe = next(c for c in profile['commands'] if str(source) in c['argv'])
            row = self.rows['osfmk/' + filename + '.o']
            self.check('already-selected-object-' + filename, row['source_sha256'] == sha(source) and recipe['exit_code'] == 0)
            target = self.out / (filename + '.c')
            shutil.copyfile(source, target)
            argv = recipe['argv'].copy()
            argv[argv.index(str(source))] = str(target)
            argv[argv.index('-o') + 1] = str(self.out / (filename + '.o'))
            argv[argv.index('-MF') + 1] = str(self.out / (filename + '.d'))
            self.command(argv, filename + '-compile-full-recipe', cwd=recipe['cwd'])
            nm_text = self.command([nm, '--defined-only', '--extern-only', self.out / (filename + '.o')], filename + '-native-definitions')
            self.check('placeholder-emits-no-external-provider-' + filename, not nm_text.strip())
            macro_argv = []
            skip = False
            for a in argv:
                if skip:
                    skip = False
                    continue
                if a in ['-o', '-MF']:
                    skip = True
                elif a not in ['-c', '-MD', '-MP']:
                    macro_argv.append(a)
            macro_argv += ['-dM', '-E']
            macros = self.command(macro_argv, filename + '-effective-macros', cwd=recipe['cwd'])
            definitions = dict(re.findall(r'^#define (\w+)\s+([^\n]+)$', macros, re.M))
            self.check('exact-required-effective-profile-' + filename, all(definitions.get(k) == v for k, v in REQUIRED.items()))
            self.report['full_recipes'].append(dict(id=row['id'], original_argv=recipe['argv'],
                owned_argv=argv, cwd=recipe['cwd'], output=self.rel(self.out / (filename + '.o')),
                output_sha256=sha(self.out / (filename + '.o')), effective_defines={k: definitions.get(k) for k in [*REQUIRED,'XNU_MONITOR','CONFIG_SPTM','ARM64_BOARD_CONFIG_E1S']},
                proposed_for_graph_replacement=False, reason='Diagnostic recompilation of public placeholder only'))
            if filename == 'pmap_iommu':
                disabled = macro_argv + ['-UCONFIG_PMAP_PPL', '-DCONFIG_PMAP_PPL=0']
                control = self.command(disabled, 'disabled-feature-effective-macros', cwd=recipe['cwd'])
                control_defs = dict(re.findall(r'^#define (\w+)\s+([^\n]+)$', control, re.M))
                self.check('feature-disable-control-actually-differs', control_defs.get('CONFIG_PMAP_PPL') == '0')
                self.reject('feature-disable-cannot-qualify-selected-profile', lambda:
                    require(all(control_defs.get(k) == v for k,v in REQUIRED.items()), 'Required production CONFIG_PMAP_PPL changed'))
        # Genuine wrong-architecture producer under the unchanged ARM64 recipe.
        # It is a negative source control, never a graph replacement.
        x86 = self.out / 'wrong-source-x86-pmap.c'
        shutil.copyfile(self.kernel / 'osfmk/x86_64/pmap.c', x86)
        wrong_argv = argv.copy()
        wrong_argv[wrong_argv.index(str(target))] = str(x86)
        wrong_argv[wrong_argv.index('-o') + 1] = str(self.out / 'wrong-source-x86-pmap.o')
        wrong_argv[wrong_argv.index('-MF') + 1] = str(self.out / 'wrong-source-x86-pmap.d')
        self.command(wrong_argv, 'genuine-x86-source-under-arm64-recipe', cwd=recipe['cwd'], expected=None)
        wrong_code = self.report['commands'][-1]['exit_code']
        self.check('actual-x86-source-cannot-produce-arm64-provider', wrong_code != 0
            and not (self.out / 'wrong-source-x86-pmap.o').exists())
        self.report['wrong_source_compile'] = dict(source_pin=PIN, source='osfmk/x86_64/pmap.c',
            unchanged_selected_arm64_flags=True, exit_code=wrong_code, qualified_for_replacement=False)
        changed = self.out / 'wrong-source.c'
        changed.write_text((self.out / 'pmap_iommu.c').read_text() + '\n/* unqualified modification */\n')
        self.reject('changed-source-cannot-reuse-qualified-identity', lambda:
            require(sha(changed) == self.rows['osfmk/pmap_iommu.o']['source_sha256'], 'Source bytes differ from exact current graph'))

    def execute(self):
        try:
            self.parents()
            self.exports()
            self.source()
            self.compile()
            self.report['diagnostic_checks_passed'] = True
            self.report['outcome'] = 'inconclusive'
            self.report['unavailable_inputs'] = [
                'Exact selected ARM64 implementations and declarations/ABI for17 IOUnifiedAddressTranslator exports.',
                'Exact selected ARM64 implementations and hardware/ABI contracts for7 pmap_iommu and11 DART/SART/UAT/NVMe PPL exports.',
                'Exact selected ARM64 pmap_has_iofilter_protected_write and pmap_cs_configuration semantics/implementation.',
                'No source-backed native export/profile correction established; required37 export bytes preserved.']
        except Exception as error:
            self.report['error'] = str(error)
        self.report['max_child_rss_kib'] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        self.report['max_harness_rss_kib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        self.report['process_memory_status'] = [line for line in Path('/proc/self/status').read_text().splitlines() if line.startswith(('VmPeak:', 'VmHWM:', 'VmRSS:'))]
        self.report['commit'] = subprocess.check_output(['git','rev-parse','HEAD'], cwd=self.wt, env=self.env, text=True).strip()
        self.report['owned_inputs'] = {self.rel(p): sha(p) for p in [Path(__file__), self.wt / 'fixtures/public/kernel-export-gaps/inputs.json', self.wt / 'docs/procedures/xnu-kernel-export-gaps.md']}
        self.save('report.json', self.report)
        artifacts = sorted(p for p in self.out.rglob('*') if p.is_file())
        evidence = {k: self.report[k] for k in ['kind','origin','outcome','recorded_at','commit','summary','commands']}
        evidence.update(artifacts=[self.rel(p) for p in artifacts], artifact_sha256={self.rel(p): sha(p) for p in artifacts},
            limitations=['No genuine provider or export correction available; task acceptance remains incomplete.',
                         'No full kernel link, private Apple ABI, runtime or device promotion.'])
        self.save('evidence.json', evidence)
        print(json.dumps(dict(outcome=self.report['outcome'], diagnostic_checks_passed=self.report.get('diagnostic_checks_passed', False),
                              report=self.rel(self.out/'report.json'), error=self.report.get('error'))))
        return self.report['outcome'] == 'fail'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--main-root', type=Path, required=True)
    parser.add_argument('--run', required=True)
    args = parser.parse_args()
    return Audit(args).execute()


if __name__ == '__main__':
    sys.exit(main())
