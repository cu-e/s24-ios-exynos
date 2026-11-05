#!/usr/bin/env python3
"""Export genuine kernel firehose headers and measure complete E1S consumers."""
from __future__ import annotations
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import resource
import shlex
import shutil
import struct
import subprocess
import sys
from xnu_compiler_vectors import Vectors
from xnu_compiler_atomics import ROOT, KERNEL, NDK, registered, sha, dump
from xnu_macho_tools import macho
from xnu_kernel_syscalls import ObjectData

SOURCE = ROOT / 'references/xnu-kernel-firehose'
REVISION = 'a641558f447659d90ad002ef0ee6f0212273fbfc'
PARENT = ROOT / 'artifacts/xnu-compiler-vectors/full-profile-session1'
COMPILER = ROOT / 'artifacts/xnu-compiler-vectors/source-build-session1/clang'
FIXTURES = ROOT / 'fixtures/public/xnu-kernel-firehose-headers'
CONSUMERS = {'bsd/subr_log.o', 'libkern/OSKext.cpo', 'libkern/log.o'}
UNIFDEF = ROOT / 'artifacts/xnu-host-tools/generators-session2/prefix/bin/unifdef'


class Firehose(Vectors):
    def __init__(self, args):
        self.args = args
        self.out = ROOT / 'artifacts/xnu-kernel-firehose-headers' / args.run
        if self.out.resolve() != self.out:
            raise ValueError('Use a canonical fresh run prefix')
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
        for name in ['E1SDEPS-003', 'HOSTGEN-002', 'VCOMP-002', 'VCOMP-004',
                     'VCOMP-007', 'VCOMP-008', 'VCOMP-009']:
            registered(name, self.ledger)
            e = next(e for e in self.ledger['experiments'] if e['id'] == name)
            self.report['parents'][name] = dict(path=e['evidence'], sha256=e['evidence_sha256'])
        self.reuse_compiler()
        self.original = json.loads((PARENT / 'report.json').read_text())
        self.rows = {r['id']: r for r in self.original['kernel_profile']}
        self.recipes = {Path(c['stdout']).name.removeprefix('kernel-').removesuffix('.stdout.txt'): c
            for c in self.original['commands'] if Path(c['stdout']).name.startswith('kernel-')}
        if len(self.rows) != 962 or len(self.recipes) != 962:
            raise ValueError('All current 962 selected source recipes are required')
        if self.must(['git', '-C', SOURCE, 'rev-parse', 'HEAD'], 'firehose-revision').strip() != REVISION:
            raise ValueError('Pinned firehose revision changed')
        if self.must(['git', '-C', SOURCE, 'status', '--porcelain'], 'firehose-clean').strip():
            raise ValueError('Original firehose checkout is modified')
        self.dependency = json.loads((ROOT / 'fixtures/public/xnu-dependencies/firehose-session1.json').read_text())
        origin = next(p for p in self.dependency['provenance'] if p['id'] == 'xnu-kernel-firehose')
        for name, h in origin['review_file_sha256'].items():
            if sha(SOURCE / name) != h:
                raise ValueError('Pinned firehose source differs: ' + name)
        names = [*origin['review_file_sha256'], 'xcodeconfig/libfirehose_kernel.xcconfig',
                 'xcodeconfig/libfirehose.xcconfig', 'libdispatch.xcodeproj/project.pbxproj']
        for index, name in enumerate(names):
            self.must(['git', '-C', SOURCE, 'show', REVISION + ':' + name], 'source-blob-' + str(index))
            if sha(self.out / ('source-blob-' + str(index) + '.stdout.txt')) != sha(SOURCE / name):
                raise ValueError('Actual source not equal to pinned Git blob: ' + name)
        self.report['source_inputs'] = {str((SOURCE / n).relative_to(ROOT)): sha(SOURCE / n) for n in names}
        self.report['source_revision'] = REVISION
        self.report['archive_profile'] = self.dependency['profiles']['E1S']
        for item in self.dependency['archives_built']:
            if sha(ROOT / item['path']) != item['sha256']:
                raise ValueError('Original firehose archive changed')
        for p in FIXTURES.iterdir():
            if p.suffix in {'.c', '.cpp'}:
                shutil.copyfile(p, self.out / 'fixture-inputs' / p.name)
        self.report['fixture_files_sha256'] = {p.name: sha(p) for p in (self.out / 'fixture-inputs').iterdir()}

    def export(self):
        text = (SOURCE / 'xcodeconfig/libfirehose_kernel.xcconfig').read_text()
        flags = re.findall(r'^COPY_HEADERS_UNIFDEF_FLAGS = (.+)$', text, re.M)
        if len(flags) != 1 or 'COPY_HEADERS_RUN_UNIFDEF = YES' not in text:
            raise ValueError('Genuine kernel export configuration changed')
        flags = shlex.split(flags[0])
        if flags != ['-DKERNEL=1', '-DOS_FIREHOSE_SPI=1', '-DOS_VOUCHER_ACTIVITY_SPI_TYPES=1', '-UOS_VOUCHER_ACTIVITY_SPI']:
            raise ValueError('Unreviewed kernel export flags')
        project = (SOURCE / 'libdispatch.xcodeproj/project.pbxproj').read_text()
        phase = project.split('6E040C611C499B1B00411A2E /* Headers */ = {', 1)[1].split('\n\t\t};', 1)[0]
        if re.findall(r'/\* (\S+ in Headers) \*/', phase) != ['firehose_buffer_private.h in Headers']:
            raise ValueError('Actual kernel header phase differs')
        self.header_root = self.out / 'export/include/kernel'
        header = self.header_root / 'os/firehose_buffer_private.h'
        header.parent.mkdir(parents=True)
        code, _, diagnostic = self.run([UNIFDEF, *flags, '-o', header, SOURCE / 'os/firehose_buffer_private.h'], 'export-kernel-header')
        self.check('genuine-kernel-export', code in [0, 1] and header.is_file(), exit_code=code, diagnostic=diagnostic)
        if code not in [0, 1]:
            raise ValueError('Genuine unifdef export failed')
        self.report['header_export'] = dict(root=str(self.header_root.relative_to(ROOT)),
            source=str((SOURCE / 'os/firehose_buffer_private.h').relative_to(ROOT)),
            source_sha256=sha(SOURCE / 'os/firehose_buffer_private.h'),
            header=str(header.relative_to(ROOT)), header_sha256=sha(header), flags=flags,
            unifdef=str(UNIFDEF), unifdef_sha256=sha(UNIFDEF),
            target='libfirehose_kernel', source_revision=REVISION)
        self.check('kernel-branches-preserved', '__firehose_buffer_create' in header.read_text() and
            'dispatch/dispatch.h' not in header.read_text() and not re.search(r'^\s*#\s*if\s+OS_FIREHOSE_SPI\s*$', header.read_text(), re.M))

    def reuse_export(self):
        if not self.args.header_evidence:
            raise ValueError('Supply recorded header export evidence')
        doc = registered(self.args.header_evidence, self.ledger)
        reports = [ROOT / p for p in doc['artifacts'] if p.endswith('/report.json')]
        if doc['outcome'] != 'pass' or len(reports) != 1:
            raise ValueError('Require a single passing genuine header export')
        previous = json.loads(reports[0].read_text())
        entry = previous['header_export']
        if entry['source_revision'] != REVISION or sha(ROOT / entry['header']) != entry['header_sha256']:
            raise ValueError('Recorded genuine header changed')
        self.header_root = ROOT / entry['root']
        self.report['header_export'] = entry
        self.report['header_parent'] = dict(experiment=self.args.header_evidence,
            report=str(reports[0].relative_to(ROOT)), sha256=sha(reports[0]))

    def command(self, row, output, source=None, header=True):
        previous = self.recipes[row['id'].replace('/', '-')]
        argv = previous['argv'].copy()
        if Path(argv[0]) != COMPILER or sha(ROOT / row['source']) != row['source_sha256']:
            raise ValueError('Recorded full compiler/source profile changed')
        if '-DXNU_NO_TYPE_BUILTINS=0' not in argv or '-w' in argv or any('xnu_clang_compat.h' in a for a in argv):
            raise ValueError('Actual allocator checks must be retained')
        if header:
            argv[1:1] = ['-I', str(self.header_root)]
        argv[argv.index('-o') + 1] = str(output)
        argv[argv.index('-MF') + 1] = str(output.with_suffix('.d'))
        if source is not None:
            argv[argv.index(str(ROOT / row['source']))] = str(source)
        return argv, Path(previous['cwd'])

    def compile_rows(self, identifiers, header=True):
        def one(identifier):
            row = self.rows[identifier]
            output = self.out / 'objects' / identifier
            output.parent.mkdir(parents=True, exist_ok=True)
            argv, cwd = self.command(row, output, header=header)
            code, _, stderr = self.run(argv, 'compile-' + identifier.replace('/', '-'), cwd=cwd, timeout=120)
            good = code == 0 and output.is_file() and macho(output)['filetype'] == 1
            return dict(id=identifier, source=row['source'], source_sha256=row['source_sha256'],
                parent_status=row['actual_arm64_object'], exit_code=code, actual_arm64_object=good,
                output=str(output.relative_to(ROOT)) if good else None, output_sha256=sha(output) if good else None,
                missing_headers=re.findall(r"fatal error: '([^']+)' file not found", stderr),
                errors=re.findall(r'(?m)^.*(?:fatal error:|error:).*$', stderr)[:12], diagnostic=stderr[-2500:])
        results = []
        with ThreadPoolExecutor(max_workers=self.args.jobs) as pool:
            for result in pool.map(one, identifiers):
                results.append(result)
                if len(results) % 40 == 0:
                    dump(self.out / 'progress.json', dict(completed=len(results), total=len(identifiers),
                        actual_arm64=sum(r['actual_arm64_object'] for r in results)))
        self.report['compile_results'] = results
        if self.args.mode == 'kernel':
            regressions = [r['id'] for r in results if r['parent_status'] and not r['actual_arm64_object']]
            self.check('all-prior-954-successes-retained', not regressions, regressions=regressions)
            self.check('all3-genuine-consumers', all(r['actual_arm64_object'] for r in results if r['id'] in CONSUMERS))
            self.check('all962-current-recipes', len(results) == 962)
            self.check('no-crash-or-timeout', all(r['exit_code'] in [0, 1] for r in results))
            self.report['coverage'] = dict(attempted=len(results), actual_arm64=sum(r['actual_arm64_object'] for r in results),
                actual_component_arm64=sum(r['actual_arm64_object'] and not r['id'].startswith('kernel/') for r in results),
                prior_successes=sum(r['parent_status'] for r in results), prior_object_regressions=regressions)
        else:
            for row in results:
                self.check('actual-' + row['id'], row['actual_arm64_object'], exit_code=row['exit_code'], errors=row['errors'])

    def audit_profile(self):
        if not self.args.profile_evidence:
            raise ValueError('Supply the recorded full profile evidence')
        doc = registered(self.args.profile_evidence, self.ledger)
        paths = [ROOT / p for p in doc['artifacts'] if p.endswith('/report.json')]
        if doc['outcome'] != 'pass' or len(paths) != 1:
            raise ValueError('Require a single passing scoped profile')
        profile = json.loads(paths[0].read_text())
        if profile['header_export'] != self.report['header_export'] or profile['compiler_sha256'] != sha(COMPILER):
            raise ValueError('Exact compiler/header profile must agree')
        rows = {r['id']: r for r in profile['compile_results']}
        commands = {Path(c['stdout']).name.removeprefix('compile-').removesuffix('.stdout.txt'): c
            for c in profile['commands'] if Path(c['stdout']).name.startswith('compile-')}
        if len(rows) != 962 or set(rows) != set(self.rows) or len(commands) != 962:
            raise ValueError('Incomplete full recipe selection')
        compiled, unresolved, objects, inputs, dependencies = [], [], [], {}, {}
        groups, headers = Counter(), Counter()
        for identifier, row in rows.items():
            old = self.rows[identifier]
            process = commands[identifier.replace('/', '-')]
            output = Path(process['argv'][process['argv'].index('-o') + 1])
            expected, cwd = self.command(old, output)
            if expected != process['argv'] or str(cwd) != process['cwd'] or row['source'] != old['source'] or row['source_sha256'] != old['source_sha256']:
                raise ValueError('Actual full source/recipe changed beyond include root and outputs')
            if process['timed_out'] or process['exit_code'] != row['exit_code'] or row['exit_code'] not in [0, 1]:
                raise ValueError('Actual result/crash/timeout mismatch')
            if not row['actual_arm64_object']:
                text = (ROOT / process['stderr']).read_text(errors='replace')
                missing = re.findall(r"fatal error: '([^']+)' file not found", text)
                category = 'missing_header' if missing else 'unsupported_metadata' if 'error: experimental XNU metadata does not support' in text else 'other_compile_error'
                groups[category] += 1; headers.update(missing)
                unresolved.append(dict(id=identifier, category=category, missing_headers=missing, errors=row['errors']))
                continue
            obj = ROOT / row['output']
            if process['exit_code'] != 0 or sha(obj) != row['output_sha256'] or macho(obj)['filetype'] != 1:
                raise ValueError('Actual ARM64 object changed')
            compiled.append({k:row[k] for k in ['id', 'source', 'source_sha256', 'output', 'output_sha256', 'parent_status']})
            objects.append(obj)
            dep = Path(process['argv'][process['argv'].index('-MF') + 1])
            line = dep.read_text().replace('\\\n', ' ').splitlines()[0]
            files = [(cwd / p).resolve() for p in shlex.split(line.split(':', 1)[1])]
            if (ROOT / row['source']).resolve() not in files:
                raise ValueError('Dependency source differs')
            names = []
            for path in files:
                name = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
                if name not in inputs:
                    inputs[name] = sha(path)
                names.append(name)
            dependencies[identifier] = dict(depfile=str(dep.relative_to(ROOT)), depfile_sha256=sha(dep), inputs=sorted(set(names)))
        for row in self.object_report['inventory']:
            if row['id'] not in rows:
                unresolved.append(dict(id=row['id'], category='missing_source_or_recipe', source=row['source']))
        rules = (KERNEL / 'makedefs/MakeInc.kernel').read_text()
        top = re.findall(r'(?m)^([A-Za-z_][A-Za-z0-9_]*\.o):[ \t]*(\$\((?:SRCROOT|OBJPATH)\)/[^\s]+\.c)[ \t]*$', rules)
        if {n for n, s in top} != {'version.o', 'nonlto.o', 'lastkerneldataconst.o', 'lastkernelconstructor.o'}:
            raise ValueError('Top-level direct declarations differ')
        unresolved.extend(dict(id='kernel/' + n, category='not_attempted_top_level', source_expression=s) for n, s in top if n != 'version.o')
        text = self.must([NDK / 'llvm-readobj', '--file-headers', *objects], 'audit-llvm-headers', timeout=120)
        self.check('independent-arm64-headers', text.count('Format: Mach-O arm64') == len(objects), count=len(objects))
        text = self.must([NDK / 'llvm-nm', '--defined-only', '--format=posix', *objects], 'audit-llvm-symbols', timeout=120)
        symbols = Counter(re.findall(r'(?m)^\S+ ([A-Za-z]) [0-9a-f]+', text))
        self.check('actual-code-symbols', symbols['T'] + symbols['t'] > 0, defined_symbol_types=dict(symbols))
        regressions = [r['id'] for r in rows.values() if r['parent_status'] and not r['actual_arm64_object']]
        self.check('all-prior954-retained', not regressions, regressions=regressions)
        self.check('actual3-firehose-consumers', all(rows[n]['actual_arm64_object'] for n in CONSUMERS))
        self.check('complete982-known-direct-inventory', len(compiled) + len(unresolved) == len(self.object_report['inventory']) + len(top) == 982)
        export_key = str((self.header_root / 'os/firehose_buffer_private.h').relative_to(ROOT))
        self.check('actual3-export-dependencies', export_key in inputs and all(export_key in dependencies[n]['inputs'] for n in CONSUMERS))
        self.report['coverage'] = dict(selected_components=len(self.object_report['inventory']), attempted=len(rows),
            actual_arm64=len(objects), actual_component_arm64=sum(not r['id'].startswith('kernel/') for r in compiled),
            known_direct_objects=982, known_direct_unresolved=len(unresolved),
            component_unresolved=sum(not r['id'].startswith('kernel/') for r in unresolved),
            additional_objects=sum(not r['parent_status'] for r in compiled), prior_successes=sum(r['parent_status'] for r in compiled),
            prior_object_regressions=regressions, failure_categories=dict(groups), missing_headers=dict(headers),
            unique_dependency_files=len(inputs), defined_symbol_types=dict(symbols))
        self.report['profile_parent'] = dict(experiment=self.args.profile_evidence, report=str(paths[0].relative_to(ROOT)), sha256=sha(paths[0]))
        for name, value in [('compiled-objects', compiled), ('unresolved-objects', unresolved), ('dependency-files', inputs), ('object-dependencies', dependencies)]:
            dump(self.out / (name + '.json'), value)

    def contract_object(self, source, label, extra=()):
        output = self.out / (label + '.o')
        argv, cwd = self.command(self.rows['bsd/subr_log.o'], output, source=source)
        argv[1:1] = list(map(str, extra))
        code, _, diagnostic = self.run(argv, label, cwd=cwd, timeout=120)
        return output, code, diagnostic

    def contracts(self):
        source = self.out / 'fixture-inputs/interface-contract.c'
        output, code, diagnostic = self.contract_object(source, 'interface-contract')
        self.check('actual-prototypes', code == 0 and output.is_file(), exit_code=code, diagnostic=diagnostic[-3500:])
        if code:
            raise ValueError('Genuine interface contract failed')
        expected = (20180226, 24, 24, 4096, 16, 4, 8, 16, 16, 64, 8)
        observed = ObjectData(output).value('_s24_firehose_interface', '<11Q')
        self.check('actual-interface-bytes', observed == expected, observed=observed)
        obj = ObjectData(output)
        targets = [obj.relocation('_s24_firehose_calls', i * 8)['name'] for i in range(9)]
        expected_targets = ['___firehose_' + n for n in ['buffer_tracepoint_reserve',
            'buffer_tracepoint_flush', 'buffer_create', 'merge_updates', 'kernel_configuration_valid',
            'allocate', 'critical_region_enter', 'critical_region_leave', 'buffer_push_to_logd']]
        self.check('actual-interface-relocations', targets == expected_targets, observed=targets)
        self.report['interface_relocations'] = targets
        # Exact pinned provider compiled under the current complete kernel profile,
        # separately from the historical minimal-profile archive.
        provider = self.out / 'fixture-inputs/provider-layout.c'
        extra = ['-I', str(SOURCE / 'src/firehose'), '-I', str(KERNEL / 'libkern/firehose'),
                 '-DDISPATCH_USE_DTRACE=0', '-DOS_ATOMIC_CONFIG_MEMORY_ORDER_DEPENDENCY=1',
                 '-DOS_ATOMIC_CONFIG_STARVATION_FREE_ONLY=0']
        provider_obj, code, diagnostic = self.contract_object(provider, 'provider-layout', extra)
        self.check('current-full-profile-provider', code == 0 and provider_obj.is_file(), exit_code=code, diagnostic=diagnostic[-4500:])
        if code:
            raise ValueError('Actual current-profile firehose provider failed')
        prior = self.dependency['profiles']['E1S']['compiled_abi']
        keys = ['max_cpus', 'max_clusters', 'pointer_bytes', 'header_bytes', 'buffer_bytes',
                'stream_bytes', 'tracepoint_bytes', 'tracepoint_data_offset', 'header_unused_offset']
        observed_provider = ObjectData(provider_obj).value('_s24_firehose_provider', '<9Q')
        self.check('provider-layout-agreement', list(observed_provider) == [prior[k] for k in keys],
                   observed=dict(zip(keys, observed_provider)), historical_profile=prior)
        pure_provider, code, diagnostic = self.contract_object(SOURCE / 'src/firehose/firehose_buffer.c', 'genuine-provider', extra)
        self.check('unmodified-provider-translation-unit', code == 0 and pure_provider.is_file(),
                   exit_code=code, diagnostic=diagnostic[-3500:])
        if code:
            raise ValueError('Unmodified genuine provider translation unit failed')
        archive = self.out / 'current-profile-libfirehose_kernel.a'
        self.must([NDK / 'llvm-ar', 'rcs', archive, pure_provider], 'current-provider-archive')
        self.must([NDK / 'llvm-ar', 'p', archive, pure_provider.name], 'current-provider-member')
        self.check('actual-provider-archive-member', sha(self.out / 'current-provider-member.stdout.txt') == sha(pure_provider))
        historical = ROOT / next(a['path'] for a in self.dependency['archives_built'] if a['machine'] == 'E1S')
        objects = [ROOT / r['output'] for r in self.report['compile_results'] if r['actual_arm64_object']]
        definitions = {}
        for label, path in [('historical', historical), ('current', archive), *[(p.stem, p) for p in objects]]:
            text = self.must([NDK / 'llvm-nm', '--defined-only', '--format=posix', path], 'definitions-' + label)
            definitions[label] = sorted(set(re.findall(r'(?m)^(\S+) [A-Za-z] [0-9a-f]+', text)))
        required = set(targets)
        for profile in ['historical', 'current']:
            available = set(definitions[profile]) | set().union(*(set(definitions[p.stem]) for p in objects))
            self.check(profile + '-declared-required-symbols', required <= available,
                       missing=sorted(required - available), required=sorted(required))
        for path in objects:
            text = self.must([NDK / 'llvm-nm', '--undefined-only', '--just-symbol-name', path], 'undefined-' + path.stem)
            needed = {n for n in text.splitlines() if n.startswith('___firehose_')}
            for profile in ['historical', 'current']:
                available = set(definitions[profile]) | set().union(*(set(definitions[p.stem]) for p in objects))
                self.check(profile + '-consumer-' + path.stem, needed <= available,
                           required=sorted(needed), missing=sorted(needed - available))
        reverse = {}
        for profile, path in [('historical', historical), ('current', archive)]:
            text = self.must([NDK / 'llvm-nm', '--undefined-only', '--just-symbol-name', path], 'provider-undefined-' + profile)
            undefined = {n for n in text.splitlines() if n.startswith('_')}
            needed = {n for n in undefined if n.startswith('___firehose_')}
            available = set().union(*(set(definitions[p.stem]) for p in objects))
            self.check(profile + '-provider-callbacks-and-globals', needed <= available and len(needed) == 6,
                       required=sorted(needed), missing=sorted(needed - available))
            reverse[profile] = dict(firehose_required=sorted(needed),
                other_platform_undefined=sorted(undefined - needed), full_link_qualified=False)
        self.report['provider_required_symbols'] = reverse
        self.report['provider'] = dict(source=str((SOURCE / 'src/firehose/firehose_buffer.c').relative_to(ROOT)),
            source_sha256=sha(SOURCE / 'src/firehose/firehose_buffer.c'), object=str(pure_provider.relative_to(ROOT)),
            object_sha256=sha(pure_provider), archive=str(archive.relative_to(ROOT)), archive_sha256=sha(archive),
            layout_probe=str(provider_obj.relative_to(ROOT)), layout_probe_sha256=sha(provider_obj),
            archive_contains_layout_probe=False,
            abi=dict(zip(keys, observed_provider)), historical_archive=str(historical.relative_to(ROOT)),
            historical_archive_sha256=sha(historical), profiles_equivalent=False)
        dump(self.out / 'defined-symbols.json', definitions)
        # A real ABI byte mutation must be detected independently of source asserts.
        mutated = self.out / 'mutated-interface.o'
        data = bytearray(output.read_bytes()); _, _, at = obj.location('_s24_firehose_interface', 88)
        struct.pack_into('<Q', data, at + 4 * 8, 17); mutated.write_bytes(data)
        self.check('reject-actual-layout-mutation', ObjectData(mutated).value('_s24_firehose_interface', '<11Q') != expected)
        changed_relocation = self.out / 'mutated-relocation.o'
        data = bytearray(output.read_bytes())
        first, second = [obj.relocation('_s24_firehose_calls', n * 8) for n in [0, 1]]
        struct.pack_into('<I', data, first['info_offset'], second['info'])
        changed_relocation.write_bytes(data)
        altered = ObjectData(changed_relocation)
        self.check('reject-actual-relocation-mutation',
            [altered.relocation('_s24_firehose_calls', i * 8)['name'] for i in range(9)] != expected_targets)
        truncated = self.out / 'truncated-interface.o'; truncated.write_bytes(output.read_bytes()[:31])
        try:
            ObjectData(truncated)
        except (ValueError, struct.error):
            self.check('reject-truncated-object', True)
        else:
            self.check('reject-truncated-object', False)
        # Alter an actual exported parameter type; the independent contract must fail.
        mutated_root = self.out / 'mutated-headers'; header = mutated_root / 'os/firehose_buffer_private.h'
        header.parent.mkdir(parents=True)
        original = (self.header_root / 'os/firehose_buffer_private.h').read_text()
        if original.count('uint16_t pubsize') != 1:
            raise ValueError('Expected one genuine reservation parameter')
        header.write_text(original.replace('uint16_t pubsize', 'uint32_t pubsize'))
        _, code, diagnostic = self.contract_object(source, 'mutated-prototype', ['-I', mutated_root])
        self.check('reject-actual-prototype-mutation', code == 1 and '__firehose_buffer_tracepoint_reserve prototype' in diagnostic,
                   exit_code=code, diagnostic=diagnostic[-3000:])
        bad = self.out / 'malformed-header.h'; bad.write_text(original + '\n#ifdef S24_UNCLOSED_CONDITION\n')
        code, _, diagnostic = self.run([UNIFDEF, *self.report['header_export']['flags'], bad], 'malformed-unifdef')
        self.check('reject-malformed-header', code == 2 and 'Premature EOF' in diagnostic,
                   exit_code=code, diagnostic=diagnostic[-1200:])

    def finish(self):
        self.report['outcome'] = 'pass' if self.report['checks'] and all(c['pass_check'] for c in self.report['checks']) and 'error' not in self.report else 'fail'
        self.report['summary'] = 'Genuine kernel firehose header/consumer qualification; full kernel, private ABI and native support remain unqualified'
        self.report['compiler_sha256'] = sha(self.compiler) if hasattr(self, 'compiler') else None
        dump(self.out / 'report.json', self.report)
        files = sorted(p for p in self.out.rglob('*') if p.is_file() and p.name != 'evidence.json')
        doc = {k:self.report[k] for k in ['kind', 'origin', 'outcome', 'recorded_at', 'summary', 'device_executed', 'full_kernel_qualified', 'apple_private_abi_qualified']}
        doc.update(commands=self.report['commands'][:20], commands_scope='Representative commands; all exact executions are retained in hashed report.json',
            actual_command_count=len(self.report['commands']), commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
            artifacts=[str(p.relative_to(ROOT)) for p in files], sha256={str(p.relative_to(ROOT)):sha(p) for p in files})
        dump(self.out / 'evidence.json', doc)
        print(json.dumps(dict(outcome=self.report['outcome'], error=self.report.get('error'),
            failed_checks=[c['name'] for c in self.report['checks'] if not c['pass_check']])))
        return 0 if self.report['outcome'] == 'pass' else 1


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', required=True)
    p.add_argument('--mode', choices=['baseline', 'export', 'consumers', 'contracts', 'kernel', 'audit'], required=True)
    p.add_argument('--header-evidence')
    p.add_argument('--profile-evidence')
    p.add_argument('--jobs', type=int, default=2)
    args = p.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', args.run):
        p.error('Use a fresh canonical run name')
    if not 1 <= args.jobs <= 3:
        p.error('Use 1..3 bounded host jobs')
    args.compiler, args.compiler_evidence = COMPILER, 'VCOMP-002'
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    build = Firehose(args)
    try:
        build.inputs()
        if args.mode == 'baseline':
            build.compile_rows(sorted(CONSUMERS), header=False)
        elif args.mode == 'export':
            build.export()
            build.compile_rows(sorted(CONSUMERS))
        else:
            build.reuse_export()
            if args.mode == 'audit':
                build.audit_profile()
            else:
                build.compile_rows(list(build.rows) if args.mode == 'kernel' else sorted(CONSUMERS))
                if args.mode == 'contracts':
                    build.contracts()
    except Exception as error:
        build.report['error'] = str(error)
    return build.finish()


if __name__ == '__main__':
    sys.exit(main())
