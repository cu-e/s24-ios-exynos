#!/usr/bin/env python3
"""Qualify two genuine selected kernel declaration ports in isolated copies."""
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
from xnu_kernel_resource_headers import Resources
from xnu_kernel_firehose_headers import COMPILER
from xnu_compiler_atomics import ROOT, KERNEL, NDK, registered, sha, dump
from xnu_kernel_syscalls import ObjectData
from xnu_macho_tools import macho

PARENT = ROOT / 'artifacts/xnu-kernel-resource-headers/full-profile-session1'
DONOR = ROOT / 'references/s24-port'
DONOR_REVISION = 'c8860decc62c6d6180e609036d027a2997972420'
FIXTURES = ROOT / 'fixtures/public/xnu-kernel-declarations'
PATCHES = ROOT / 'patches/kernel-declarations'
PORTS = {
    'osfmk/mc_provider.o': ('osfmk/minicrypto/mc_provider.c', '0001-use-existing-kernel-printf-declaration.patch'),
    'osfmk/user_exception_trace.o': ('osfmk/arm64/user_exception_trace.c', '0002-include-genuine-proc-declarations.patch'),
}


class Declarations(Resources):
    def __init__(self, args):
        self.args = args
        self.out = ROOT / 'artifacts/xnu-kernel-declarations' / args.run
        if self.out.resolve() != self.out:
            raise ValueError('Use a canonical fresh declaration run')
        self.out.mkdir(parents=True, exist_ok=False)
        shutil.copyfile(__file__, self.out / 'builder.py')
        self.ledger = json.loads((ROOT / 'state/lab.json').read_text())
        self.ports = {}
        self.report = dict(kind='host-test', origin='local-host', outcome='fail',
            recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
            mode=args.mode, commands=[], checks=[], kernel_cases=[],
            device_executed=False, sdk_used=False, full_kernel_qualified=False,
            full_crypto_qualified=False, apple_private_abi_qualified=False, native_device_qualified=False)

    def inputs(self):
        super().inputs()
        for name in ['RHDR-002', 'RHDR-004', 'RHDR-005', 'RHDR-006', 'RHDR-008']:
            registered(name, self.ledger)
            e = next(e for e in self.ledger['experiments'] if e['id'] == name)
            self.report['parents'][name] = dict(path=e['evidence'], sha256=e['evidence_sha256'])
        self.reuse_resources()
        self.original = json.loads((PARENT / 'report.json').read_text())
        self.rows = {r['id']:r for r in self.original['compile_results']}
        self.recipes = {Path(c['stdout']).name.removeprefix('compile-').removesuffix('.stdout.txt'):c
            for c in self.original['commands'] if Path(c['stdout']).name.startswith('compile-')}
        if len(self.rows) != 962 or len(self.recipes) != 962:
            raise ValueError('Complete current 962 source recipes required')
        aliases = []
        for identifier, row in self.rows.items():
            previous = self.recipes[identifier.replace('/', '-')]
            indices = self.source_indices(row, previous)
            if len(indices) != 1:
                raise ValueError('One exact current compile source binding required: ' + identifier)
            if previous['argv'][indices[0]] != str(ROOT / row['source']):
                aliases.append(dict(id=identifier, argv_source=previous['argv'][indices[0]], resolved_source=row['source'], cwd=previous['cwd']))
        self.report['source_argument_aliases'] = aliases
        self.report['recipe_parent'] = dict(experiment='RHDR-004', report=str((PARENT / 'report.json').relative_to(ROOT)), sha256=sha(PARENT / 'report.json'))
        if self.must(['git', '-C', DONOR, 'rev-parse', 'HEAD'], 'donor-revision').strip() != DONOR_REVISION:
            raise ValueError('Pinned donor revision changed')
        sources = [p for p, patch in PORTS.values()] + ['osfmk/minicrypto/minicrypto.h']
        for index, name in enumerate(sources):
            self.must(['git', '-C', DONOR, 'show', DONOR_REVISION + ':xnu/hackios/files/' + name], 'donor-source-' + str(index))
            if sha(self.out / ('donor-source-' + str(index) + '.stdout.txt')) != sha(KERNEL / name):
                raise ValueError('Selected source differs from genuine pinned donor file: ' + name)
        headers = ['osfmk/kern/debug.h', 'osfmk/kern/misc_protos.h', 'bsd/libkern/libkern.h',
                   'bsd/sys/proc.h', 'osfmk/kern/task.c', 'osfmk/vm/vm_protos.h', 'bsd/kern/kern_proc.c',
                   'libkern/libkern/crypto/register_crypto.h', 'APPLE_LICENSE']
        self.report['declaration_inputs'] = {str((KERNEL / n).relative_to(ROOT)):sha(KERNEL / n) for n in [*sources, *headers]}
        bridge = next(line for line in (KERNEL / 'osfmk/kern/task.c').read_text().splitlines() if line.startswith('extern int proc_pid('))
        if bridge != 'extern int proc_pid(struct proc *);' or 'extern int proc_pid(proc_t);' not in (KERNEL / 'bsd/sys/proc.h').read_text():
            raise ValueError('Unreviewed canonical Mach/BSD process ABI')
        self.report['proc_pid_bridge'] = dict(declaration=bridge, mach_source=str((KERNEL / 'osfmk/kern/task.c').relative_to(ROOT)),
            bsd_header=str((KERNEL / 'bsd/sys/proc.h').relative_to(ROOT)), provider_source=str((KERNEL / 'bsd/kern/kern_proc.c').relative_to(ROOT)))
        self.report['donor_revision'] = DONOR_REVISION
        for p in FIXTURES.iterdir():
            if p.suffix in {'.c', '.cpp'}:
                shutil.copyfile(p, self.out / 'fixture-inputs' / p.name)
        self.report['fixture_files_sha256'] = {p.name:sha(p) for p in (self.out / 'fixture-inputs').iterdir()}

    def make_ports(self):
        base = self.out / 'source-ports'; self.ports = {}
        for identifier, (relative, patchname) in PORTS.items():
            source = base / relative; source.parent.mkdir(parents=True, exist_ok=True)
            original = KERNEL / relative; shutil.copyfile(original, source)
            patch = PATCHES / patchname; shutil.copyfile(patch, self.out / patchname)
            self.must(['git', '-C', base, 'apply', '--check', patch], 'check-' + patchname)
            self.must(['git', '-C', base, 'apply', patch], 'apply-' + patchname)
            if identifier == 'osfmk/mc_provider.o':
                expected = original.read_text().replace('extern int printf(const char *format, ...) __printflike(1, 2);\n', '', 1)
            else:
                bridge = next(line for line in (KERNEL / 'osfmk/kern/task.c').read_text().splitlines() if line.startswith('extern int proc_pid('))
                expected = original.read_text().replace('extern char *proc_name_address(struct proc *p);\n', 'extern char *proc_name_address(struct proc *p);\n' + bridge + '\n', 1)
            if source.read_text() != expected or source.read_bytes() == original.read_bytes():
                raise ValueError('Source port changed beyond exact declaration/include delta')
            self.ports[identifier] = dict(original=str(original.relative_to(ROOT)), original_sha256=sha(original),
                source=str(source.relative_to(ROOT)), source_sha256=sha(source),
                patch=str((self.out / patchname).relative_to(ROOT)), patch_sha256=sha(patch))
        header = base / 'osfmk/minicrypto/minicrypto.h'; original = KERNEL / 'osfmk/minicrypto/minicrypto.h'
        shutil.copyfile(original, header)
        self.report['source_ports'] = self.ports
        self.report['quoted_include_copy'] = dict(source=str(original.relative_to(ROOT)), source_sha256=sha(original),
            copy=str(header.relative_to(ROOT)), copy_sha256=sha(header))
        self.check('exact-declaration-only-ports', True, count=len(self.ports))

    def reuse_ports(self):
        if not self.args.port_evidence:
            raise ValueError('Supply a recorded source-port experiment')
        doc = registered(self.args.port_evidence, self.ledger)
        reports = [ROOT / p for p in doc['artifacts'] if p.endswith('/report.json')]
        if doc['outcome'] != 'pass' or len(reports) != 1:
            raise ValueError('Require one passing genuine source-port report')
        old = json.loads(reports[0].read_text())
        self.ports = old['source_ports']
        if set(self.ports) != set(PORTS):
            raise ValueError('Exactly two qualified source ports required')
        for row in self.ports.values():
            for path, h in [('original', 'original_sha256'), ('source', 'source_sha256'), ('patch', 'patch_sha256')]:
                if sha(ROOT / row[path]) != row[h]:
                    raise ValueError('Recorded source port bytes changed')
        self.report['source_ports'] = self.ports
        self.report['quoted_include_copy'] = old['quoted_include_copy']
        self.report['port_parent'] = dict(experiment=self.args.port_evidence, report=str(reports[0].relative_to(ROOT)), sha256=sha(reports[0]))

    def source_indices(self, row, previous):
        return [i for i, arg in enumerate(previous['argv']) if arg.endswith(('.c', '.cpp', '.cc', '.s', '.S')) and
                (Path(previous['cwd']) / arg).resolve() == (ROOT / row['source']).resolve()]

    def command(self, row, output, source=None, header=True):
        previous = self.recipes[row['id'].replace('/', '-')]
        argv = previous['argv'].copy()
        if Path(argv[0]) != COMPILER or sha(ROOT / row['source']) != row['source_sha256']:
            raise ValueError('Actual current full source/compiler profile changed')
        if '-DXNU_NO_TYPE_BUILTINS=0' not in argv or '-w' in argv or any('xnu_clang_compat.h' in a for a in argv):
            raise ValueError('Keep genuine allocator checks and diagnostics')
        selected = source or (ROOT / self.ports[row['id']]['source'] if row['id'] in self.ports else ROOT / row['source'])
        indices = self.source_indices(row, previous)
        if len(indices) != 1:
            raise ValueError('Unreviewed actual compile source binding')
        # Retain genuine relative arguments (notably ioconf.c) for unchanged
        # sources; substitute only the declared owned source ports/controls.
        if Path(selected).resolve() != (ROOT / row['source']).resolve():
            argv[indices[0]] = str(selected)
        argv[argv.index('-o') + 1] = str(output)
        argv[argv.index('-MF') + 1] = str(output.with_suffix('.d'))
        return argv, Path(previous['cwd']), Path(selected)

    def compile_rows(self, identifiers):
        def one(identifier):
            row = self.rows[identifier]; output = self.out / 'objects' / identifier
            output.parent.mkdir(parents=True, exist_ok=True)
            argv, cwd, source = self.command(row, output)
            code, _, error = self.run(argv, 'compile-' + identifier.replace('/', '-'), cwd=cwd, timeout=120)
            good = code == 0 and output.is_file() and macho(output)['filetype'] == 1
            return dict(id=identifier, source=str(source.relative_to(ROOT)), source_sha256=sha(source),
                original_source=row['source'], original_source_sha256=row['source_sha256'], parent_status=row['actual_arm64_object'],
                exit_code=code, actual_arm64_object=good, output=str(output.relative_to(ROOT)) if good else None,
                output_sha256=sha(output) if good else None, missing_headers=re.findall(r"fatal error: '([^']+)' file not found", error),
                errors=re.findall(r'(?m)^.*(?:fatal error:|error:).*$', error)[:12], diagnostic=error[-2500:])
        results = []
        with ThreadPoolExecutor(max_workers=self.args.jobs) as pool:
            for row in pool.map(one, identifiers):
                results.append(row)
                if len(results) % 40 == 0:
                    dump(self.out / 'progress.json', dict(completed=len(results), total=len(identifiers), actual_arm64=sum(r['actual_arm64_object'] for r in results)))
        self.report['compile_results'] = results
        if self.args.mode == 'kernel':
            regressions = [r['id'] for r in results if r['parent_status'] and not r['actual_arm64_object']]
            self.check('all-prior958-retained', not regressions, regressions=regressions)
            self.check('all962-current-recipes', len(results) == 962)
            self.check('both-genuine-declaration-consumers', all(r['actual_arm64_object'] for r in results if r['id'] in PORTS))
            self.check('no-crash-or-timeout', all(r['exit_code'] in [0, 1] for r in results))
            self.report['coverage'] = dict(attempted=len(results), actual_arm64=sum(r['actual_arm64_object'] for r in results),
                actual_component_arm64=sum(r['actual_arm64_object'] and not r['id'].startswith('kernel/') for r in results),
                prior_successes=sum(r['parent_status'] for r in results), prior_object_regressions=regressions)
        else:
            for row in results:
                self.check('actual-' + row['id'], row['actual_arm64_object'], exit_code=row['exit_code'], errors=row['errors'])

    def control_object(self, source, label, identifier='osfmk/mc_provider.o', formats=False):
        output = self.out / (label + '.o')
        argv, cwd, _ = self.command(self.rows[identifier], output, source=source)
        if formats:
            flags = [a for a in argv if a.split('=', 1)[0] == '-DCONFIG_NO_PRINTF_STRINGS']
            if len(flags) != 1:
                raise ValueError('One actual configured printf flag required')
            argv.remove(flags[0]); argv.append('-DCONFIG_NO_PRINTF_STRINGS=0')
        code, _, error = self.run(argv, label, cwd=cwd, timeout=120)
        return output, code, error, argv, cwd

    def controls(self):
        source = self.out / 'fixture-inputs/declaration-contract.c'
        for label, formats, callee in [('current', False, '_consume_printf_args'), ('formats-enabled', True, 'printf')]:
            obj, code, error, argv, cwd = self.control_object(source, label + '-contract', formats=formats)
            self.check(label + '-canonical-prototypes', code == 0 and obj.is_file(), exit_code=code, diagnostic=error[-2500:])
            if code:
                raise ValueError('Actual selected declaration contract failed')
            observed = ObjectData(obj).value('_s24_declaration_layout', '<4Q')
            self.check(label + '-actual-target-layout', observed == (8, 4, 8, 8), observed=observed)
            names = self.must([NDK / 'llvm-nm', '--undefined-only', '--just-symbol-name', obj], label + '-symbols').splitlines()
            self.check(label + '-actual-required-symbols', '_proc_pid' in names and '_' + callee in names,
                       undefined=names, expected_printf='_' + callee)
            marker = b'S24_DECLARATION_FORMAT:%d'
            self.check(label + '-actual-format-string-policy', (marker in obj.read_bytes()) == formats)
            ir = self.out / (label + '-contract-ir.ll')
            argv.remove('-c'); argv += ['-S', '-emit-llvm']
            argv[argv.index('-o') + 1] = str(ir)
            argv[argv.index('-MF') + 1] = str(ir.with_suffix('.d'))
            self.must(argv, label + '-contract-ir', cwd=cwd)
            body = re.search(r'(?ms)^define[^\n]*@declaration_printf_probe\(.*?^}', ir.read_text())
            self.check(label + '-argument-side-effect-and-callee', bool(body) and 'store i32' in body[0] and '@' + callee + '(' in body[0])
        bsd = self.out / 'fixture-inputs/bsd-proc-contract.c'
        obj, code, error, _, _ = self.control_object(bsd, 'genuine-bsd-proc-prototype', identifier='bsd/kern_proc.o')
        self.check('genuine-bsd-proc-prototype', code == 0 and obj.is_file(), exit_code=code, diagnostic=error[-2500:])
        if code: raise ValueError('Actual independent BSD profile declaration failed')
        self.check('mach-bsd-opaque-target-abi', ObjectData(obj).value('_s24_bsd_proc_layout', '<3Q') == (8, 4, 8))
        names = self.must([NDK / 'llvm-nm', '--undefined-only', '--just-symbol-name', obj], 'bsd-proc-symbols').splitlines()
        self.check('bsd-proc-canonical-required-symbol', '_proc_pid' in names, undefined=names)
        for name, suffix, expected in [
            ('conflicting-proc-prototype', '\nextern long proc_pid(struct proc *);\n', "conflicting types for 'proc_pid'"),
            ('redundant-printf-declaration', '\nextern int printf(const char *format, ...) __printflike(1, 2);\n', '_consume_printf_args')]:
            path = self.out / (name + '.c'); path.write_text(source.read_text() + suffix)
            _, code, error, _, _ = self.control_object(path, name)
            self.check('reject-' + name, code == 1 and expected in error, exit_code=code, diagnostic=error[-2000:])
        missing = self.out / 'missing-proc-header.c'
        missing.write_text((ROOT / self.ports['osfmk/user_exception_trace.o']['source']).read_text().replace('extern int proc_pid(struct proc *);\n', '', 1))
        _, code, error, _, _ = self.control_object(missing, 'missing-canonical-proc-header', identifier='osfmk/user_exception_trace.o')
        self.check('reject-missing-canonical-proc-header', code == 1 and "undeclared function 'proc_pid'" in error, exit_code=code, diagnostic=error[-2200:])
        base = (ROOT / self.ports['osfmk/mc_provider.o']['source']).parents[2]
        for identifier, row in self.ports.items():
            code, _, error = self.run(['git', '-C', base, 'apply', '--check', ROOT / row['patch']], 'duplicate-' + identifier.replace('/', '-'))
            self.check('reject-duplicate-' + identifier, code == 1 and 'patch does not apply' in error and sha(ROOT / row['source']) == row['source_sha256'], exit_code=code)
        self.crypto_table_control()

    def crypto_table_control(self):
        fields = ['ccdigest_init_fn', 'ccaes_ecb_encrypt', 'ccaes_xts_encrypt', 'ccaes_xts_decrypt',
                  'ccaes_gcm_encrypt', 'ccaes_gcm_decrypt', 'ccchacha20poly1305_fns', 'ccdes_ecb_encrypt',
                  'ccrsa_make_pub_fn', 'ccrsa_verify_pkcs1v15_fn']
        source = self.out / 'crypto-table-probe.c'
        provider = ROOT / self.ports['osfmk/mc_provider.o']['source']
        source.write_text('#include "' + str(provider) + '"\n' +
            '__attribute__((used,section("__DATA_CONST,__s24decl"))) const unsigned long long s24_crypto_offsets[] = {' +
            ','.join(['sizeof(struct crypto_functions)', *['__builtin_offsetof(struct crypto_functions,' + f + ')' for f in fields]]) + '};\n')
        output, code, error, _, _ = self.control_object(source, 'actual-crypto-table-probe')
        self.check('actual-crypto-table-probe', code == 0 and output.is_file(), exit_code=code, diagnostic=error[-2500:])
        if code:
            raise ValueError('Actual callback table probe failed')
        data = ObjectData(output); values = data.value('_s24_crypto_offsets', '<11Q'); size, offsets = values[0], dict(zip(fields, values[1:]))
        def inspect(path):
            obj = ObjectData(path); obj.location('_mc_funcs', size)
            active = {}
            for field, expected in [('ccdigest_init_fn', '_ccdigest_init'), ('ccaes_ecb_encrypt', '_mc_aes_ecb_encrypt')]:
                relocation = obj.relocation('_mc_funcs', offsets[field])
                if relocation['name'] != expected:
                    raise ValueError('Actual crypto callback relocation differs: ' + field)
                active[field] = relocation['name']
            for field in fields[2:]:
                offset = offsets[field]; section, at, _ = obj.location('_mc_funcs', 8, offset)
                relocations = [i for i in range(section['nreloc']) if struct.unpack_from('<i', obj.data, section['reloc'] + 8 * i)[0] == at]
                if obj.value('_mc_funcs', '<Q', offset)[0] != 0 or relocations:
                    raise ValueError('Expected unsupported zero callback without relocation: ' + field)
            return active
        pure = ROOT / next(r['output'] for r in self.report['compile_results'] if r['id'] == 'osfmk/mc_provider.o')
        self.check('actual-crypto-table-unchanged', inspect(pure) == inspect(output), active=inspect(pure), zero_callbacks=fields[2:], offsets=offsets, size=size)
        self.report['crypto_table'] = dict(size=size, offsets=offsets, active_callbacks=inspect(pure),
            observed_zero_callbacks=fields[2:], full_crypto_qualified=False, runtime_executed=False)
        mutated = self.out / 'mutated-null-callback.o'; binary = bytearray(pure.read_bytes()); obj = ObjectData(pure)
        _, _, at = obj.location('_mc_funcs', 8, offsets[fields[2]]); struct.pack_into('<Q', binary, at, 1); mutated.write_bytes(binary)
        try:
            inspect(mutated)
        except ValueError:
            self.check('reject-actual-null-callback-mutation', True)
        else:
            self.check('reject-actual-null-callback-mutation', False)
        mutated = self.out / 'mutated-active-callback.o'; binary = bytearray(pure.read_bytes())
        first = obj.relocation('_mc_funcs', offsets[fields[0]]); second = obj.relocation('_mc_funcs', offsets[fields[1]])
        struct.pack_into('<I', binary, first['info_offset'], second['info']); mutated.write_bytes(binary)
        try:
            inspect(mutated)
        except ValueError:
            self.check('reject-actual-active-callback-mutation', True)
        else:
            self.check('reject-actual-active-callback-mutation', False)

    def audit_profile(self):
        if not self.args.profile_evidence:
            raise ValueError('Supply recorded full profile evidence')
        doc = registered(self.args.profile_evidence, self.ledger)
        paths = [ROOT / p for p in doc['artifacts'] if p.endswith('/report.json')]
        if doc['outcome'] != 'pass' or len(paths) != 1:
            raise ValueError('Require one passing complete selected profile')
        profile = json.loads(paths[0].read_text())
        if profile['source_ports'] != self.ports or profile['compiler_sha256'] != sha(COMPILER) or profile['resource_bundle'] != self.report['resource_bundle']:
            raise ValueError('Exact source ports/compiler/resources must agree')
        rows = {r['id']:r for r in profile['compile_results']}
        commands = {Path(c['stdout']).name.removeprefix('compile-').removesuffix('.stdout.txt'):c
            for c in profile['commands'] if Path(c['stdout']).name.startswith('compile-')}
        if set(rows) != set(self.rows) or len(rows) != 962 or len(commands) != 962:
            raise ValueError('Complete actual recipe inventory required')
        compiled, unresolved, objects, inputs, dependencies = [], [], [], {}, {}
        groups, headers = Counter(), Counter()
        for identifier, row in rows.items():
            before = self.rows[identifier]; process = commands[identifier.replace('/', '-')]
            output = Path(process['argv'][process['argv'].index('-o') + 1])
            expected, cwd, source = self.command(before, output)
            if process['argv'] != expected or process['cwd'] != str(cwd) or row['source'] != str(source.relative_to(ROOT)) or sha(source) != row['source_sha256'] or row['original_source'] != before['source'] or row['original_source_sha256'] != before['source_sha256']:
                raise ValueError('Actual source/full recipe changed beyond declared source ports and outputs')
            if process['timed_out'] or process['exit_code'] != row['exit_code'] or row['exit_code'] not in [0, 1]:
                raise ValueError('Actual exit/crash/timeout mismatch')
            if not row['actual_arm64_object']:
                text = (ROOT / process['stderr']).read_text(errors='replace')
                missing = re.findall(r"fatal error: '([^']+)' file not found", text)
                category = 'missing_header' if missing else 'unsupported_metadata' if 'error: experimental XNU metadata does not support' in text else 'other_compile_error'
                groups[category] += 1; headers.update(missing)
                unresolved.append(dict(id=identifier, category=category, missing_headers=missing, errors=row['errors']))
                continue
            obj = ROOT / row['output']
            if process['exit_code'] != 0 or sha(obj) != row['output_sha256'] or macho(obj)['filetype'] != 1:
                raise ValueError('Actual ARM64 output differs')
            objects.append(obj)
            compiled.append({k:row[k] for k in ['id', 'source', 'source_sha256', 'original_source', 'original_source_sha256', 'output', 'output_sha256', 'parent_status']})
            dep = Path(process['argv'][process['argv'].index('-MF') + 1])
            line = dep.read_text().replace('\\\n', ' ').splitlines()[0]
            files = [(cwd / p).resolve() for p in shlex.split(line.split(':', 1)[1])]
            if source.resolve() not in files:
                raise ValueError('Actual source missing from dependency graph')
            names = []
            for path in files:
                name = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
                if name not in inputs: inputs[name] = sha(path)
                names.append(name)
            dependencies[identifier] = dict(depfile=str(dep.relative_to(ROOT)), depfile_sha256=sha(dep), inputs=sorted(set(names)))
        for row in self.object_report['inventory']:
            if row['id'] not in rows:
                unresolved.append(dict(id=row['id'], category='missing_source_or_recipe', source=row['source']))
        rules = (KERNEL / 'makedefs/MakeInc.kernel').read_text()
        top = re.findall(r'(?m)^([A-Za-z_][A-Za-z0-9_]*\.o):[ \t]*(\$\((?:SRCROOT|OBJPATH)\)/[^\s]+\.c)[ \t]*$', rules)
        if {n for n, s in top} != {'version.o', 'nonlto.o', 'lastkerneldataconst.o', 'lastkernelconstructor.o'}:
            raise ValueError('Known direct source declarations changed')
        unresolved.extend(dict(id='kernel/' + n, category='not_attempted_top_level', source_expression=s) for n, s in top if n != 'version.o')
        text = self.must([NDK / 'llvm-readobj', '--file-headers', *objects], 'audit-llvm-headers', timeout=120)
        self.check('independent-arm64-headers', text.count('Format: Mach-O arm64') == len(objects), count=len(objects))
        text = self.must([NDK / 'llvm-nm', '--defined-only', '--format=posix', *objects], 'audit-llvm-symbols', timeout=120)
        symbols = Counter(re.findall(r'(?m)^\S+ ([A-Za-z]) [0-9a-f]+', text))
        self.check('actual-code-symbols', symbols['T'] + symbols['t'] > 0, defined_symbol_types=dict(symbols))
        regressions = [r['id'] for r in rows.values() if r['parent_status'] and not r['actual_arm64_object']]
        self.check('all-prior958-retained', not regressions, regressions=regressions)
        self.check('both-genuine-source-ports', all(rows[n]['actual_arm64_object'] for n in PORTS))
        self.check('complete982-known-direct-inventory', len(compiled) + len(unresolved) == len(self.object_report['inventory']) + len(top) == 982)
        header = self.report['quoted_include_copy']
        self.check('actual-quoted-header-copy', header['copy'] in dependencies['osfmk/mc_provider.o']['inputs'] and sha(ROOT / header['copy']) == sha(ROOT / header['source']) == header['source_sha256'])
        self.check('opaque-mach-bsd-bridge-preserved', not any(n.endswith('/sys/proc.h') for n in dependencies['osfmk/user_exception_trace.o']['inputs']) and 'extern int proc_pid(struct proc *);' in (ROOT / self.ports['osfmk/user_exception_trace.o']['source']).read_text())
        self.report['coverage'] = dict(selected_components=len(self.object_report['inventory']), attempted=len(rows),
            actual_arm64=len(objects), actual_component_arm64=sum(not r['id'].startswith('kernel/') for r in compiled),
            known_direct_objects=982, known_direct_unresolved=len(unresolved), component_unresolved=sum(not r['id'].startswith('kernel/') for r in unresolved),
            additional_objects=sum(not r['parent_status'] for r in compiled), prior_successes=sum(r['parent_status'] for r in compiled),
            prior_object_regressions=regressions, failure_categories=dict(groups), missing_headers=dict(headers),
            unique_dependency_files=len(inputs), defined_symbol_types=dict(symbols))
        self.report['profile_parent'] = dict(experiment=self.args.profile_evidence, report=str(paths[0].relative_to(ROOT)), sha256=sha(paths[0]))
        for name, value in [('compiled-objects', compiled), ('unresolved-objects', unresolved), ('dependency-files', inputs), ('object-dependencies', dependencies)]:
            dump(self.out / (name + '.json'), value)

    def finish(self):
        self.report['outcome'] = 'pass' if self.report['checks'] and all(c['pass_check'] for c in self.report['checks']) and 'error' not in self.report else 'fail'
        self.report['summary'] = 'Genuine selected declaration/source-port assessment; full kernel/link/crypto/private ABI/native support remains unqualified'
        self.report['compiler_sha256'] = sha(self.compiler) if hasattr(self, 'compiler') else None
        dump(self.out / 'report.json', self.report)
        files = sorted(p for p in self.out.rglob('*') if p.is_file() and p.name != 'evidence.json')
        doc = {k:self.report[k] for k in ['kind', 'origin', 'outcome', 'recorded_at', 'summary', 'device_executed', 'full_kernel_qualified', 'full_crypto_qualified', 'apple_private_abi_qualified']}
        doc.update(commands=self.report['commands'][:20], commands_scope='Representative exact commands; every execution retained in hashed report.json',
            actual_command_count=len(self.report['commands']), commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
            artifacts=[str(p.relative_to(ROOT)) for p in files], sha256={str(p.relative_to(ROOT)):sha(p) for p in files})
        dump(self.out / 'evidence.json', doc)
        print(json.dumps(dict(outcome=self.report['outcome'], error=self.report.get('error'), failed_checks=[c['name'] for c in self.report['checks'] if not c['pass_check']])))
        return 0 if self.report['outcome'] == 'pass' else 1


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', required=True)
    p.add_argument('--mode', choices=['baseline', 'port', 'consumers', 'controls', 'kernel', 'audit'], required=True)
    p.add_argument('--port-evidence')
    p.add_argument('--profile-evidence')
    p.add_argument('--jobs', type=int, default=2)
    args = p.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', args.run):
        p.error('Use a canonical fresh run name')
    if not 1 <= args.jobs <= 3:
        p.error('Use 1..3 bounded host jobs')
    args.compiler, args.compiler_evidence, args.header_evidence, args.resource_evidence = COMPILER, 'VCOMP-002', 'FHDR-003', 'RHDR-002'
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    build = Declarations(args)
    try:
        build.inputs()
        if args.mode == 'port':build.make_ports()
        elif args.mode in ['consumers', 'controls', 'kernel', 'audit']:build.reuse_ports()
        if args.mode == 'audit': build.audit_profile()
        else:
            build.compile_rows(list(build.rows) if args.mode == 'kernel' else sorted(PORTS))
            if args.mode == 'controls': build.controls()
    except Exception as error:build.report['error'] = str(error)
    return build.finish()


if __name__ == '__main__':sys.exit(main())
