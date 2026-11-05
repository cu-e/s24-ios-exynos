#!/usr/bin/env python3
"""Source-build matched Clang17 ARM resources and qualify genuine APFS recipes."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import resource
import shlex
import shutil
import subprocess
import sys
from xnu_kernel_firehose_headers import Firehose, COMPILER
from xnu_compiler_atomics import ROOT, KERNEL, NDK, registered, sha, dump
from xnu_kernel_syscalls import ObjectData
from xnu_macho_tools import macho

PUBLIC = ROOT / 'references/xnu-tapi'
REVISION = 'fa9443738c1a18accef4244732ec6d6ee97a8133'
PARENT = ROOT / 'artifacts/xnu-kernel-firehose-headers/full-profile-session1'
FIXTURES = ROOT / 'fixtures/public/xnu-kernel-resource-headers'
APFS = 'bsd/apfs_deflate.o'


def verify_bundle(root, bundle):
    if bundle['source_revision'] != REVISION or bundle['compiler_sha256'] != sha(COMPILER):
        raise ValueError('Unmatched compiler resource bundle')
    if {p.name for p in root.iterdir()} != set(bundle['headers']) or any(sha(root / n) != h for n, h in bundle['headers'].items()):
        raise ValueError('Genuine generated resource bytes/file set changed')


class Resources(Firehose):
    def __init__(self, args):
        self.args = args
        self.out = ROOT / 'artifacts/xnu-kernel-resource-headers' / args.run
        if self.out.resolve() != self.out:
            raise ValueError('Use a canonical fresh resource run')
        self.out.mkdir(parents=True, exist_ok=False)
        shutil.copyfile(__file__, self.out / 'builder.py')
        self.ledger = json.loads((ROOT / 'state/lab.json').read_text())
        self.report = dict(kind='host-test', origin='local-host', outcome='fail',
            recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
            mode=args.mode, commands=[], checks=[], kernel_cases=[],
            device_executed=False, sdk_used=False, full_kernel_qualified=False,
            apple_private_abi_qualified=False, native_device_qualified=False)

    def inputs(self):
        super().inputs()
        for name in ['FHDR-003', 'FHDR-005', 'FHDR-006', 'FHDR-007', 'FHDR-008']:
            registered(name, self.ledger)
            e = next(e for e in self.ledger['experiments'] if e['id'] == name)
            self.report['parents'][name] = dict(path=e['evidence'], sha256=e['evidence_sha256'])
        self.reuse_export()
        self.original = json.loads((PARENT / 'report.json').read_text())
        self.rows = {r['id']: r for r in self.original['compile_results']}
        self.recipes = {Path(c['stdout']).name.removeprefix('compile-').removesuffix('.stdout.txt'): c
            for c in self.original['commands'] if Path(c['stdout']).name.startswith('compile-')}
        if len(self.rows) != 962 or len(self.recipes) != 962:
            raise ValueError('All current selected source recipes are required')
        self.report['recipe_parent'] = dict(experiment='FHDR-005', report=str((PARENT / 'report.json').relative_to(ROOT)), sha256=sha(PARENT / 'report.json'))
        if self.must(['git', '-C', PUBLIC, 'rev-parse', 'HEAD'], 'resource-source-revision').strip() != REVISION:
            raise ValueError('Public generator source revision changed')
        names = ['src/clang/lib/Headers/CMakeLists.txt', 'src/clang/utils/TableGen/NeonEmitter.cpp',
                 'src/clang/utils/TableGen/TableGen.cpp', 'src/clang/include/clang/Basic/arm_neon.td',
                 'src/clang/include/clang/Basic/arm_bf16.td', 'src/clang/lib/Headers/arm_acle.h',
                 'src/clang/lib/Headers/stdint.h', 'src/clang/LICENSE.TXT', 'src/llvm/LICENSE.TXT']
        for i, name in enumerate(names):
            self.must(['git', '-C', PUBLIC, 'show', REVISION + ':' + name], 'public-source-' + str(i))
            if sha(self.out / ('public-source-' + str(i) + '.stdout.txt')) != sha(self.private / name):
                raise ValueError('Actual resource source differs from pinned public blob: ' + name)
        self.report['source_inputs'] = {str((self.private / p).relative_to(ROOT)):sha(self.private / p) for p in names}
        self.report['source_revision'] = REVISION
        rule = (KERNEL / 'bsd/conf/Makefile.arm64').read_text()
        if 'apfs_deflate.o_CFLAGS_ADD += -idirafter $(shell $(CC) -print-resource-dir)/include' not in rule:
            raise ValueError('Genuine selected APFS resource rule differs')
        self.report['selected_resource_rule'] = dict(path=str((KERNEL / 'bsd/conf/Makefile.arm64').relative_to(ROOT)), sha256=sha(KERNEL / 'bsd/conf/Makefile.arm64'))
        for p in FIXTURES.iterdir():
            if p.suffix in {'.c', '.cpp'}:
                shutil.copyfile(p, self.out / 'fixture-inputs' / p.name)
        self.report['fixture_files_sha256'] = {p.name:sha(p) for p in (self.out / 'fixture-inputs').iterdir()}

    def command(self, row, output, source=None, header=True):
        previous = self.recipes[row['id'].replace('/', '-')]
        argv = previous['argv'].copy()
        if Path(argv[0]) != COMPILER or sha(ROOT / row['source']) != row['source_sha256']:
            raise ValueError('Actual full current compiler/source profile changed')
        if '-DXNU_NO_TYPE_BUILTINS=0' not in argv or '-w' in argv or any('xnu_clang_compat.h' in a for a in argv):
            raise ValueError('Actual allocator checks must remain enabled')
        if header and row['id'] == APFS:
            old = ROOT / 'artifacts/xnu-compiler-hardening/lib/clang/17/include'
            if argv.count('-idirafter') != 1 or argv[argv.index('-idirafter') + 1] != str(old):
                raise ValueError('Original selected APFS resource binding differs')
            argv[argv.index('-idirafter') + 1] = str(self.resource_root)
        elif '-idirafter' in argv and row['id'] != APFS:
            raise ValueError('Unreviewed additional resource consumer')
        argv[argv.index('-o') + 1] = str(output)
        argv[argv.index('-MF') + 1] = str(output.with_suffix('.d'))
        if source is not None:
            argv[argv.index(str(ROOT / row['source']))] = str(source)
        return argv, Path(previous['cwd'])

    def compile_rows(self, identifiers, header=True):
        super().compile_rows(identifiers, header=header)
        for check in self.report['checks']:
            check['name'] = check['name'].replace('all-prior-954-successes', 'all-prior-957-successes')
        if self.args.mode == 'kernel':
            row = next(r for r in self.report['compile_results'] if r['id'] == APFS)
            self.check('genuine-apfs-resource-object', row['actual_arm64_object'], errors=row['errors'])

    def generate(self):
        recipe = self.must([shutil.which('ninja'), '-C', self.build, '-t', 'commands', 'bin/clang-tblgen'], 'generator-link-recipe')
        tokens = shlex.split(recipe.splitlines()[-1])
        if tokens[:2] != [':', '&&'] or tokens[-2:] != ['&&', ':']:
            raise ValueError('Unexpected original generator link wrapper')
        link = tokens[2:-2]
        rpaths = [i for i, a in enumerate(link) if 'ORIGIN' in a]
        if len(rpaths) != 1 or link[rpaths[0]].replace('\\', '') != '-Wl,-rpath,$ORIGIN/../lib:':
            raise ValueError('Unreviewed literal generator rpath')
        # shlex preserves this escaped dollar inside double quotes, whereas the
        # actual original shell passes a literal $ORIGIN with no backslash.
        link[rpaths[0]] = '-Wl,-rpath,$ORIGIN/../lib:'
        if sha(link[0]) != self.host_sha:
            raise ValueError('Original generator host compiler changed')
        originals = [a for a in link if a.endswith('.o')]
        if len(originals) != 21 or len(set(Path(p).name for p in originals)) != 21:
            raise ValueError('Unreviewed actual generator translation-unit inventory')
        objects = self.out / 'generator-objects'; objects.mkdir()
        def one(original):
            name = Path(original).name
            recipe = self.must([shutil.which('ninja'), '-C', self.build, '-t', 'commands', original], 'recipe-' + name)
            argv = shlex.split(recipe.splitlines()[-1])
            if sha(argv[0]) != self.host_sha or argv.count('-c') != 1:
                raise ValueError('Actual generator compile recipe differs')
            source = Path(argv[argv.index('-c') + 1])
            relative = source.relative_to(self.private)
            self.must(['git', '-C', PUBLIC, 'show', REVISION + ':' + str(relative)], 'pinned-' + name)
            if sha(source) != sha(self.out / ('pinned-' + name + '.stdout.txt')):
                raise ValueError('Generator translation unit differs from pinned public source')
            output = objects / name
            for flag, value in [('-o', output), ('-MF', output.with_suffix('.d')), ('-MT', output)]:
                if argv.count(flag) != 1:
                    raise ValueError('Actual generator output/dependency option differs')
                argv[argv.index(flag) + 1] = str(value)
            self.must(argv, 'build-' + name, cwd=self.build, timeout=180)
            return dict(original_object=original, source=str(source.relative_to(ROOT)), source_sha256=sha(source),
                object=str(output.relative_to(ROOT)), object_sha256=sha(output))
        with ThreadPoolExecutor(max_workers=self.args.jobs) as pool:
            consumers = list(pool.map(one, originals))
        for old, row in zip(originals, consumers):
            link[link.index(old)] = str(ROOT / row['object'])
        self.generator = self.out / 'clang-tblgen'
        link[link.index('-o') + 1] = str(self.generator)
        dep = self.out / 'generator-link.d'
        locations = [i for i, a in enumerate(link) if a.startswith('--dependency-file=')]
        if len(locations) != 1:
            raise ValueError('Original generator linker dependency option differs')
        link[locations[0]] = '--dependency-file=' + str(dep)
        archive_inputs = {str((self.build / a).resolve()):sha(self.build / a) for a in link if a.endswith('.a')}
        if len(archive_inputs) != 3:
            raise ValueError('Unreviewed generator link archive inventory')
        self.must(link, 'source-generator-link', cwd=self.build, timeout=120)
        self.must([self.generator, '--version'], 'source-generator-version')
        self.report['generator'] = dict(path=str(self.generator.relative_to(ROOT)), sha256=sha(self.generator),
            consumers=consumers, archive_inputs_sha256=archive_inputs,
            host_compiler_sha256=self.host_sha, linker_dependency=str(dep.relative_to(ROOT)),
            linker_dependency_sha256=sha(dep), original_build_ninja_sha256=sha(self.build / 'build.ninja'))
        self.resource_root = self.out / 'resource/lib/clang/17/include'; self.resource_root.mkdir(parents=True)
        generated = {}
        for name in ['arm_neon.h', 'arm_bf16.h']:
            target = 'tools/clang/lib/Headers/' + name
            recipe = self.must([shutil.which('ninja'), '-C', self.build, '-t', 'commands', target], 'rule-' + name)
            parts = [shlex.split(p) for p in recipe.splitlines()[-1].split(' && ')]
            if len(parts) != 3 or parts[0] != ['cd', str(self.build)] or parts[1][0] != str(self.build / 'bin/clang-tblgen'):
                raise ValueError('Genuine resource generation recipe wrapper differs')
            argv = parts[1]
            argv[0] = str(self.generator)
            output = self.resource_root / name
            argv[argv.index('-o') + 1] = str(output)
            argv[argv.index('-d') + 1] = str(self.out / (name + '.d'))
            self.must(argv, 'generate-' + name, cwd=self.build, timeout=60)
            original = self.build / target
            self.check('reproduced-' + name, sha(output) == sha(original), sha256=sha(output),
                original=str(original.relative_to(ROOT)), original_sha256=sha(original))
            generated[name] = sha(output)
        shutil.copyfile(self.private / 'src/clang/lib/Headers/arm_acle.h', self.resource_root / 'arm_acle.h')
        generated['arm_acle.h'] = sha(self.resource_root / 'arm_acle.h')
        self.report['resource_bundle'] = dict(root=str(self.resource_root.relative_to(ROOT)), headers=generated,
            source_revision=REVISION, compiler_sha256=sha(COMPILER), generator=self.report['generator']['path'],
            generator_sha256=sha(self.generator), sdk_used=False,
            stdint_source='Selected existing XNU stdint.h remains first under genuine -idirafter binding')
        self.check('exact-required-resource-set', {p.name for p in self.resource_root.iterdir()} == {'arm_neon.h', 'arm_bf16.h', 'arm_acle.h'})

    def reuse_resources(self):
        if not self.args.resource_evidence:
            raise ValueError('Supply recorded generated resource evidence')
        doc = registered(self.args.resource_evidence, self.ledger)
        reports = [ROOT / p for p in doc['artifacts'] if p.endswith('/report.json')]
        if doc['outcome'] != 'pass' or len(reports) != 1:
            raise ValueError('Require a single passing source generator/header report')
        previous = json.loads(reports[0].read_text())
        bundle = previous['resource_bundle']
        self.resource_root = ROOT / bundle['root']
        verify_bundle(self.resource_root, bundle)
        self.report['resource_bundle'] = bundle
        self.report['resource_parent'] = dict(experiment=self.args.resource_evidence, report=str(reports[0].relative_to(ROOT)), sha256=sha(reports[0]))

    def controls(self):
        core = self.out / 'controls-core'; core.mkdir()
        shutil.copyfile(self.private / 'src/clang/lib/Headers/stdint.h', core / 'stdint.h')
        ndk_resource = NDK.parent / 'lib/clang/19/include'
        if not ndk_resource.is_dir():
            raise ValueError('Independent Clang19 resource inputs unavailable')
        source = self.out / 'fixture-inputs/neon-contract.c'
        expected = (8, 8, 16, 16, 16, 16, 16, 16, 16, 2, 32, 16)
        flags = ['-target', 'arm64-apple-ios16.5', '-ffreestanding', '-nostdinc', '-std=gnu11', '-O2']
        self.report['independent_resource_inputs'] = {str((ndk_resource / n)):sha(ndk_resource / n)
            for n in ['arm_neon.h', 'arm_bf16.h', 'arm_acle.h', 'stdint.h']}
        for label, compiler, includes in [('source17', COMPILER, [self.resource_root, core]),
                                          ('independent19', NDK / 'clang', [ndk_resource])]:
            arguments = [compiler, *flags, *[a for p in includes for a in ['-I', p]]]
            obj = self.out / (label + '-neon.o')
            self.must([*arguments, '-c', source, '-o', obj], label + '-neon')
            observed = ObjectData(obj).value('_s24_neon_layout', '<12Q')
            self.check(label + '-real-target-layout', observed == expected, observed=observed)
            text = self.must([NDK / 'llvm-objdump', '-d', obj], label + '-disassembly')
            self.check(label + '-actual-neon-code', all(re.search(r'\b' + name + r'(?:\.|\s)', text)
                for name in ['uaddlp', 'umlal', 'umlal2', 'addv', 'eor']), instructions=['uaddlp', 'umlal', 'umlal2', 'addv', 'eor'])
            ir = self.out / (label + '-neon.ll')
            self.must([*arguments, '-S', '-emit-llvm', source, '-o', ir], label + '-llvm-ir')
            value = ir.read_text()
            constant = re.search(r'define[^@]+@neon_constant\([^}]+\bret i32 52\b', value)
            self.check(label + '-actual-intrinsic-constant-fold', bool(constant))
            self.check(label + '-real-vector-ir', 'add <16 x i8>' in value and
                any(n in value for n in ['llvm.vector.reduce.add.v4i32', 'llvm.aarch64.neon.uaddv']))
        arguments = [COMPILER, *flags, '-I', self.resource_root, '-I', core, '-ferror-limit=8']
        cpp = self.out / 'fixture-inputs/neon-metadata.cpp'
        cxx_flags = [a for a in arguments if a != '-std=gnu11']
        self.must([*cxx_flags, '-std=gnu++17', '-DXNU_NO_TYPE_BUILTINS=0', '-Werror=unknown-attributes',
            '-c', cpp, '-o', self.out / 'neon-metadata.o'], 'actual-generated-neon-metadata')
        cases = {
            'lane-out-of-range': ('#include <arm_neon.h>\nuint8_t bad(uint8x16_t a) { return vgetq_lane_u8(a,16); }\n', [], 'outside the valid range'),
            'nonconstant-immediate': ('#include <arm_neon.h>\nuint16x8_t bad(uint16x8_t a,int n) { return vshlq_n_u16(a,n); }\n', [], 'constant integer'),
            'neon-disabled': ('#include <arm_neon.h>\n', ['-mgeneral-regs-only'], 'NEON'),
            'polynomial-metadata': ('#include <arm_neon.h>\nunsigned bad(void) { return __builtin_xnu_type_summary(poly8x16_t); }\n', [], 'experimental XNU metadata does not support'),
        }
        for name, (text, extra, diagnostic) in cases.items():
            path = self.out / (name + '.c'); path.write_text(text)
            code, _, error = self.run([*arguments, *extra, '-fsyntax-only', path], name)
            self.check('reject-' + name, code == 1 and diagnostic in error, exit_code=code, diagnostic=error[-2500:])
        # Actual foreign Clang19 headers are never accepted for this Clang17 bundle.
        code, _, error = self.run([COMPILER, *flags, '-I', ndk_resource, '-ferror-limit=8',
            '-fsyntax-only', source], 'unmatched-clang19-headers')
        self.check('reject-unmatched-clang19-compilation', code == 1 and ('unknown type name' in error or 'unknown builtin' in error or 'undeclared' in error),
                   exit_code=code, diagnostic=error[-4500:])
        foreign = self.out / 'foreign-resource-bundle'; foreign.mkdir()
        for name in self.report['resource_bundle']['headers']:
            shutil.copyfile(ndk_resource / name, foreign / name)
        try:
            verify_bundle(foreign, self.report['resource_bundle'])
        except ValueError:
            self.check('reject-foreign-bundle-provenance', True)
        else:
            self.check('reject-foreign-bundle-provenance', False)
        mutated = self.out / 'mutated-resource-bundle'; shutil.copytree(self.resource_root, mutated)
        with (mutated / 'arm_neon.h').open('a') as file:
            file.write('\n#error S24_RESOURCE_CONTENT_MUTATION\n')
        try:
            verify_bundle(mutated, self.report['resource_bundle'])
        except ValueError:
            self.check('reject-actual-header-byte-mutation', True)
        else:
            self.check('reject-actual-header-byte-mutation', False)
        missing = self.out / 'missing-bf16'; missing.mkdir()
        shutil.copyfile(self.resource_root / 'arm_neon.h', missing / 'arm_neon.h')
        code, _, error = self.run([COMPILER, *flags, '-I', missing, '-I', core, '-ferror-limit=2',
            '-fsyntax-only', source], 'missing-matched-bf16')
        self.check('reject-incomplete-resource-bundle', code == 1 and "'arm_bf16.h' file not found" in error,
                   exit_code=code, diagnostic=error[-2500:])
        apfs = ROOT / self.report['compile_results'][0]['output']
        text = self.must([NDK / 'llvm-objdump', '-d', apfs], 'genuine-apfs-disassembly')
        function = re.search(r'(?ms)^[0-9a-f]+ <_adler32_arm_neon>:\n(.*?)(?=^[0-9a-f]+ <|\Z)', text)
        body = function[1] if function else ''
        opcodes = {n:len(re.findall(r'\b' + n + r'(?:\.|\s)', body))
            for n in ['uadalp', 'umlal', 'umlal2', 'ext', 'addv', 'uaddlp']}
        upper_half = opcodes['umlal2'] > 0 or (opcodes['umlal'] >= 16 and
            len(re.findall(r'\bext\.16b\s+(v\d+),\s*\1,\s*\1,\s*#0x8\b', body)) == 8)
        self.check('genuine-apfs-real-neon-adler-code', bool(function) and upper_half and
            all(opcodes[n] > 0 for n in ['uadalp', 'umlal', 'addv', 'uaddlp']),
            observed_opcodes=opcodes, upper_half_implementation='umlal2 or eight real high-half ext#8 plus umlal pairs')
        text = self.must([NDK / 'llvm-nm', '--undefined-only', '--just-symbol-name', apfs], 'genuine-apfs-undefined')
        self.check('no-unlowered-neon-builtin-symbols', not any('builtin_neon' in n for n in text.splitlines()), undefined=text.splitlines())

    def audit_profile(self):
        super().audit_profile()
        for check in self.report['checks']:
            check['name'] = check['name'].replace('all-prior954-retained', 'all-prior957-retained')
        compiled = json.loads((self.out / 'compiled-objects.json').read_text())
        self.check('genuine-apfs-audited', any(r['id'] == APFS for r in compiled))
        deps = json.loads((self.out / 'object-dependencies.json').read_text())
        required = {str((self.resource_root / n).relative_to(ROOT)) for n in ['arm_neon.h', 'arm_bf16.h', 'arm_acle.h']}
        self.check('actual-apfs-resource-dependencies', required <= set(deps[APFS]['inputs']))
        resources = {n for d in deps.values() for n in d['inputs'] if n.startswith(str(self.resource_root.relative_to(ROOT)) + '/')}
        self.check('only-matched-generated-resource-files', resources == required)
        stdint = [n for n in deps[APFS]['inputs'] if n.endswith('/stdint.h')]
        self.check('selected-kernel-stdint-preserved', stdint == [str((KERNEL / 'EXTERNAL_HEADERS/stdint.h').relative_to(ROOT))], observed=stdint)

    def finish(self):
        self.report['outcome'] = 'pass' if self.report['checks'] and all(c['pass_check'] for c in self.report['checks']) and 'error' not in self.report else 'fail'
        self.report['summary'] = 'Source-built matched Clang17 ARM resource/APFS qualification; full kernel/link/private ABI/native support remains unqualified'
        self.report['compiler_sha256'] = sha(self.compiler) if hasattr(self, 'compiler') else None
        dump(self.out / 'report.json', self.report)
        files = sorted(p for p in self.out.rglob('*') if p.is_file() and p.name != 'evidence.json')
        doc = {k:self.report[k] for k in ['kind', 'origin', 'outcome', 'recorded_at', 'summary', 'device_executed', 'full_kernel_qualified', 'apple_private_abi_qualified']}
        doc.update(commands=self.report['commands'][:20], commands_scope='Representative exact commands; all executions retained in hashed report.json',
            actual_command_count=len(self.report['commands']), commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
            artifacts=[str(p.relative_to(ROOT)) for p in files], sha256={str(p.relative_to(ROOT)):sha(p) for p in files})
        dump(self.out / 'evidence.json', doc)
        print(json.dumps(dict(outcome=self.report['outcome'], error=self.report.get('error'),
            failed_checks=[c['name'] for c in self.report['checks'] if not c['pass_check']])))
        return 0 if self.report['outcome'] == 'pass' else 1


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', required=True)
    p.add_argument('--mode', choices=['baseline', 'generate', 'consumer', 'controls', 'kernel', 'audit'], required=True)
    p.add_argument('--resource-evidence')
    p.add_argument('--profile-evidence')
    p.add_argument('--jobs', type=int, default=2)
    args = p.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', args.run):
        p.error('Use a canonical fresh run name')
    if not 1 <= args.jobs <= 3:
        p.error('Use 1..3 bounded host jobs')
    args.compiler, args.compiler_evidence, args.header_evidence = COMPILER, 'VCOMP-002', 'FHDR-003'
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    build = Resources(args)
    try:
        build.inputs()
        if args.mode == 'baseline':
            build.compile_rows([APFS], header=False)
        elif args.mode == 'generate':
            build.generate()
        else:
            build.reuse_resources()
            if args.mode == 'audit':
                build.audit_profile()
            else:
                build.compile_rows(list(build.rows) if args.mode == 'kernel' else [APFS])
                if args.mode == 'controls':
                    build.controls()
    except Exception as error:
        build.report['error'] = str(error)
    return build.finish()


if __name__ == '__main__':
    sys.exit(main())
