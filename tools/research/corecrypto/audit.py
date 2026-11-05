#!/usr/bin/env python3
"""Audit selected crypto provider inputs and actual ARM64 callback ABI, no provider build."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import resource
import shlex
import shutil
import struct
import subprocess
import sys
import urllib.request

HERE = Path(__file__).resolve().parent
WORKTREE = HERE.parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(WORKTREE / 'tools/build'))
from xnu_kernel_syscalls import ObjectData


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_hash(path, expected):
    if digest(path) != expected:
        raise ValueError('Input hash mismatch: ' + str(path))


def without_comments(text):
    return re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S)


def table_fields(header):
    body = without_comments(header).split('typedef struct crypto_functions {', 1)[1].split('} *crypto_functions_t', 1)[0]
    fields = [re.search(r'(\w+)\s*$', field.strip())[1] for field in body.split(';') if field.strip()]
    if len(set(fields)) != len(fields):
        raise ValueError('Duplicate crypto table member')
    return fields


def required_link(argv):
    if '-lcc_kext' not in argv:
        raise ValueError('Required genuine cc_kext link input was removed')


def table_observation(path, fields, offsets, assignments):
    obj = ObjectData(path)
    rows = []
    for field in fields:
        section, position, file_at = obj.location('_mc_funcs', 8, offsets[field])
        relocs = [i for i in range(section['nreloc'])
                  if struct.unpack_from('<i', obj.data, section['reloc'] + 8 * i)[0] == position]
        raw = obj.value('_mc_funcs', '<Q', offsets[field])[0]
        if field in assignments:
            expected = '_' + assignments[field].strip().removeprefix('&')
            relocation = obj.relocation('_mc_funcs', offsets[field])
            if len(relocs) != 1 or relocation['name'] != expected:
                raise ValueError('Actual callback relocation mismatch: ' + field)
            rows.append(dict(field=field, offset=offsets[field], storage_bytes=8,
                             state='relocated', target=relocation['name']))
        else:
            if raw or relocs:
                raise ValueError('Expected static zero without relocation: ' + field)
            rows.append(dict(field=field, offset=offsets[field], storage_bytes=8,
                             state='deferred-startup' if field == 'ccsha256_di' else 'unsupported',
                             raw=raw, relocations=len(relocs)))
    return rows


def conservative_full_table_policy(fields, assigned, integration_rights):
    if not integration_rights:
        raise ValueError('Provider integration/redistribution permission not established')
    missing = sorted(set(fields) - set(assigned))
    if missing:
        raise ValueError('Conservative full-table policy: missing assignments: ' + ','.join(missing))
    # Deliberately conservative review policy, not an inferred Apple ABI rule:
    # unused slots may legitimately remain absent in a matched consumer profile.
    # Passing this policy never promotes any signature/context/PRNG/runtime ABI.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('/home/egor/dev/pet/s24-ios-exynos'))
    parser.add_argument('--run', required=True)
    parser.add_argument('--metadata-root', type=Path, default=HERE / 'local/public-metadata')
    parser.add_argument('--fetch-metadata', action='store_true', help='Fetch only named pinned research text into owned ignored metadata root')
    args = parser.parse_args()
    root = args.root.resolve()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', args.run):
        raise ValueError('Use a fresh canonical run name')
    out = HERE / 'local' / args.run
    if out.resolve() != out:
        raise ValueError('Symlink outputs forbidden')
    out.mkdir(parents=True, exist_ok=False)
    report = dict(kind='source-review', origin='local-host', outcome='fail',
                  recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                  summary='Attempted bounded selected crypto input/ABI audit; actual failures retained',
                  commands=[], checks=[], source_inputs={}, device_executed=False,
                  provider_built=False, full_crypto_qualified=False, full_kernel_qualified=False,
                  apple_private_abi_qualified=False, FIPS_qualified=False, native_device_qualified=False)

    def rel(path):
        return str(path.relative_to(root))

    def bind(path, expected=None):
        if expected is not None:
            verify_hash(path, expected)
        report['source_inputs'][rel(path)] = digest(path)
        return path

    def run(argv, label, cwd=WORKTREE, expected=0):
        argv = list(map(str, argv))
        result = subprocess.run(argv, cwd=cwd, capture_output=True, timeout=45)
        stdout, stderr = out / (label + '.stdout.txt'), out / (label + '.stderr.txt')
        stdout.write_bytes(result.stdout)
        stderr.write_bytes(result.stderr)
        report['commands'].append(dict(argv=argv, cwd=str(cwd), exit_code=result.returncode,
                                       stdout=rel(stdout), stderr=rel(stderr)))
        if result.returncode != expected:
            raise ValueError(label + ' unexpected exit ' + str(result.returncode) + ': ' + result.stderr[-1800:].decode(errors='replace'))
        if resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss >= 1024 * 1024:
            raise ValueError('Child exceeded 1 GiB RSS')
        return result.stdout

    def check(name, value, **facts):
        report['checks'].append(dict(name=name, passed=bool(value), **facts))
        if not value:
            raise ValueError('Check failed: ' + name)

    def reject(name, action):
        try:
            action()
        except (ValueError, KeyError) as error:
            check(name, True, diagnostic=str(error))
        else:
            check(name, False)

    try:
        report['commit'] = run(['git', 'rev-parse', 'HEAD'], 'worktree-commit').decode().strip()
        snapshot = out / 'auditor.py'
        shutil.copyfile(__file__, snapshot)
        manifest_path = bind(WORKTREE / 'fixtures/public/corecrypto-provider/inputs.json')
        manifest = json.loads(manifest_path.read_text())
        parents = {}
        for key, row in manifest['parents'].items():
            parents[key] = json.loads(bind(root / row['path'], row['sha256']).read_text())
        declaration = parents['declarations']
        public = manifest['public_corecrypto']
        metadata = args.metadata_root.resolve()
        if args.fetch_metadata:
            if HERE not in metadata.parents:
                raise ValueError('Fetched metadata must stay under owned tool directory')
            metadata.mkdir(parents=True, exist_ok=True)
            pin = public['revision']
            urls = {'git-commit.json': f'https://api.github.com/repos/apple/corecrypto/git/commits/{pin}',
                    'kext-list.json': f'https://api.github.com/repos/apple/corecrypto/contents/corecrypto_kext?ref={pin}'}
            for name, source in [('License.txt', 'License.txt'), ('README.md', 'README.md'), ('corecrypto_kext.c', 'corecrypto_kext/corecrypto_kext.c')]:
                urls[name] = f'https://raw.githubusercontent.com/apple/corecrypto/{pin}/{source}'
            report['downloads'] = []
            for name, url in urls.items():
                request = urllib.request.Request(url, headers={'User-Agent': 's24-bounded-source-audit'})
                with urllib.request.urlopen(request, timeout=30) as response:
                    data = response.read(256 * 1024 + 1)
                    if len(data) > 256 * 1024:
                        raise ValueError('Named metadata exceeds bounded acquisition extent')
                    status = response.status
                target = metadata / name
                if target.exists() and target.read_bytes() != data:
                    raise ValueError('Do not overwrite changed metadata; use fresh metadata root')
                target.write_bytes(data)
                report['downloads'].append(dict(url=url, http_status=status, path=rel(target), sha256=digest(target)))
        for name, expected in public['local_files'].items():
            bind(metadata / name, expected)
        check('public-commit-metadata-full-sha', json.loads((metadata / 'git-commit.json').read_text())['sha'] == public['revision'])
        license_text = (metadata / 'License.txt').read_text()
        check('public-default-license-is-restricted-evaluation', all(token in license_text for token in ['ninety (90) days', 'may not, directly or indirectly, redistribute', "prior written permission"]))
        report['public_provider'] = public
        blob_sources = [('xnu', 'references/apple-xnu', manifest['xnu_revision'],
                         ['libkern/libkern/crypto/register_crypto.h', 'libkern/crypto/register_crypto.c', 'makedefs/MakeInc.def',
                          'libkern/crypto/corecrypto_aesxts.c', 'libkern/crypto/corecrypto_aes.c',
                          'libkern/crypto/corecrypto_rsa.c', 'libkern/crypto/corecrypto_des.c',
                          'libkern/crypto/corecrypto_chacha20poly1305.c', 'APPLE_LICENSE']),
                        ('donor', 'references/s24-port', manifest['donor_revision'],
                         ['xnu/hackios/files/osfmk/minicrypto/mc_provider.c', 'xnu/hackios/LICENSE'])]
        blobs = {}
        for label, repository, pin, names in blob_sources:
            for i, name in enumerate(names):
                data = run(['git', '-C', root / repository, 'show', pin + ':' + name], label + '-source-' + str(i))
                blobs[label + ':' + name] = data.decode()
            report[label + '_revision'] = pin
        header = blobs['xnu:libkern/libkern/crypto/register_crypto.h']
        check('actual-prepared-registration-header-matches-pin', (root / 'artifacts/xnu-prepare/e1s-dependency-source-session1/xnu/libkern/libkern/crypto/register_crypto.h').read_text() == header)
        fields = table_fields(header)
        check('all-selected-table-members-enumerated', len(fields) == manifest['expected_fields'])
        provider_row = next(row for row in parents['coherent_objects'] if row['id'] == 'osfmk/mc_provider.o')
        provider_source = bind(root / provider_row['source'], provider_row['source_sha256'])
        provider_object = bind(root / provider_row['output'], provider_row['output_sha256'])
        check('current-provider-is-same-qualified-object', provider_row['output_sha256'] == next(row for row in declaration['compile_results'] if row['id'] == 'osfmk/mc_provider.o')['output_sha256'])
        provider = without_comments(provider_source.read_text())
        initializer = provider.split('static struct crypto_functions mc_funcs = {', 1)[1].split('};', 1)[0]
        assignments = dict(re.findall(r'\.(\w+)\s*=\s*([^,]+)', initializer))
        check('deferred-SHA256-assignment-precedes-registration', provider.index('mc_funcs.ccsha256_di = ccsha256_di();') < provider.index('register_crypto_functions(&mc_funcs)'))
        command = next(row for row in declaration['commands'] if str(provider_source) in row['argv'] and '-c' in row['argv'])
        argv = list(command['argv'])
        bind(Path(argv[0]), declaration['compiler_sha256'])
        run([argv[0], '--version'], 'actual-selected-compiler')
        probe, obj, dep = out / 'layout.c', out / 'layout.o', out / 'layout.d'
        expressions = ['sizeof(struct crypto_functions)', '_Alignof(struct crypto_functions)']
        for field in fields:
            expressions += ['__builtin_offsetof(struct crypto_functions,' + field + ')', 'sizeof(((struct crypto_functions*)0)->' + field + ')']
        contracts = ('#include <libkern/crypto/register_crypto.h>\n'
                     '_Static_assert(__builtin_types_compatible_p(ccrsa_make_pub_fn_t, __typeof__(&ccrsa_make_pub)), "selected RSA make-public type");\n'
                     '_Static_assert(__builtin_types_compatible_p(ccrsa_verify_pkcs1v15_fn_t, __typeof__(&ccrsa_verify_pkcs1v15)), "selected RSA verification type");\n')
        probe.write_text(contracts + '__attribute__((used)) const unsigned long long corecrypto_provider_layout[] = {' + ','.join(expressions) + '};\n')
        argv[argv.index(str(provider_source))] = str(probe)
        argv[argv.index('-o') + 1] = str(obj)
        argv[argv.index('-MF') + 1] = str(dep)
        run(argv, 'selected-header-layout', Path(command['cwd']))
        values = ObjectData(obj).value('_corecrypto_provider_layout', '<' + str(len(expressions)) + 'Q')
        offsets = dict(zip(fields, values[2::2]))
        check('genuine-target-table-layout', values[0] == manifest['expected_table_bytes'] and values[1] == 8 and
              list(offsets.values()) == list(range(0, 448, 8)) and all(size == 8 for size in values[3::2]), bytes=values[0], alignment=values[1])
        check('selected-RSA-callback-types-match-real-corecrypto-declarations', True)
        wrong = out / 'wrong-signature.c'
        wrong.write_text(contracts + '_Static_assert(__builtin_types_compatible_p(ccrsa_make_pub_fn_t, int (*)(void)), "INTENTIONAL_INCOMPATIBLE_PROVIDER_SIGNATURE");\n')
        negative_argv = list(argv)
        negative_argv[negative_argv.index(str(probe))] = str(wrong)
        negative_argv[negative_argv.index('-o') + 1] = str(out / 'wrong-signature.o')
        negative_argv[negative_argv.index('-MF') + 1] = str(out / 'wrong-signature.d')
        run(negative_argv, 'reject-real-signature-mismatch', Path(command['cwd']), expected=1)
        check('incompatible-provider-signature-rejected-by-genuine-header', 'INTENTIONAL_INCOMPATIBLE_PROVIDER_SIGNATURE' in (out / 'reject-real-signature-mismatch.stderr.txt').read_text())
        dependency_line = dep.read_text().replace('\\\n', ' ').splitlines()[0].split(':', 1)[1]
        dependencies = [Path(path) if Path(path).is_absolute() else Path(command['cwd']) / path
                        for path in shlex.split(dependency_line)]
        report['probe_dependency_hashes'] = {str(path.resolve()): digest(path) for path in dependencies}
        rows = table_observation(provider_object, fields, offsets, assignments)
        unsupported = [row['field'] for row in rows if row['state'] == 'unsupported']
        check('prior-eight-zero-slots-retained', set(manifest['known_sampled_zero_callbacks']) <= set(unsupported))
        check('full-unsupported-set-is-21-not-eight', len(unsupported) == 21 and len(assignments) == 34)
        report['table'] = dict(bytes=values[0], fields=rows, unsupported_count=len(unsupported), unsupported=unsupported,
                               deferred=['ccsha256_di'], static_relocated_count=len(assignments))
        for field in unsupported:
            damaged = out / ('changed-null-' + field + '.o')
            binary = bytearray(provider_object.read_bytes())
            _, _, at = ObjectData(provider_object).location('_mc_funcs', 8, offsets[field])
            struct.pack_into('<Q', binary, at, 1)
            damaged.write_bytes(binary)
            reject('reject-real-null-slot-mutation-' + field, lambda: table_observation(damaged, fields, offsets, assignments))
        damaged = out / 'changed-active-relocation.o'
        binary = bytearray(provider_object.read_bytes())
        original = ObjectData(provider_object)
        first = original.relocation('_mc_funcs', offsets['ccdigest_init_fn'])
        other = original.relocation('_mc_funcs', offsets['ccaes_ecb_encrypt'])
        struct.pack_into('<I', binary, first['info_offset'], other['info'])
        damaged.write_bytes(binary)
        reject('reject-real-active-relocation-mutation', lambda: table_observation(damaged, fields, offsets, assignments))
        poisoned = out / 'changed-input.c'
        poisoned.write_bytes(provider_source.read_bytes() + b'\n/* mutation */\n')
        reject('reject-source-hash-drift', lambda: verify_hash(poisoned, provider_row['source_sha256']))
        links = [row for row in parents['link']['commands'] if '-lcc_kext' in row['argv']]
        check('actual-native-link-retains-required-cc_kext', bool(links))
        for row in links:
            required_link(row['argv'])
            for key in ['stdout', 'stderr']:
                if key in row and (root / row[key]).is_file():
                    bind(root / row[key])
        reject('reject-required-library-removal', lambda: required_link([arg for arg in links[-1]['argv'] if arg != '-lcc_kext']))
        search_directories = set()
        for row in links:
            for index, arg in enumerate(row['argv']):
                if arg.startswith('-L'):
                    name = row['argv'][index + 1] if arg == '-L' else arg[2:]
                    path = Path(name)
                    search_directories.add(str(path if path.is_absolute() else Path(row['cwd']) / path))
        found_archives = [str(Path(directory) / name) for directory in search_directories
                          for name in ['libcc_kext.a', 'libcc_kext.dylib'] if (Path(directory) / name).is_file()]
        check('required-provider-not-present-in-measured-search-directories', not found_archives)
        report['native_link'] = dict(parent=manifest['parents']['link'], required='cc_kext',
                                     historical_attempts=[parents['link']['full_link_attempt'], parents['link']['available_provider_attempt']],
                                     actual_commands_with_required_library=len(links), current_archive_supplied=bool(found_archives),
                                     measured_search_directories=sorted(search_directories), found_provider_archives=found_archives,
                                     absence_scope='Only recorded explicit library search directories; not a global filesystem absence assertion')
        public_source = without_comments((metadata / 'corecrypto_kext.c').read_text())
        public_assignments = set(re.findall(r'kpis\.(\w+)\s*=', public_source))
        public_missing = sorted(set(fields) - public_assignments)
        report['public_source_coverage'] = dict(selected_fields=len(fields), assigned_selected_fields=len(set(fields) & public_assignments),
                                               missing_selected_fields=public_missing, extra_fields=sorted(public_assignments - set(fields)),
                                               type_or_runtime_compatibility_qualified=False)
        reject('reject-public-provider-rights-for-integration', lambda: conservative_full_table_policy(fields, public_assignments, False))
        reject('reject-public-provider-under-conservative-full-table-policy', lambda: conservative_full_table_policy(fields, public_assignments, True))
        reject('reject-minicrypto-under-conservative-full-table-policy', lambda: conservative_full_table_policy(fields, set(assignments) | {'ccsha256_di'}, True))
        registration = blobs['xnu:libkern/crypto/register_crypto.c']
        check('registration-publishes-table-without-size-version-negotiation', 'g_crypto_funcs = funcs;' in registration and 'crypto_init = true;' in registration and 'if (g_crypto_funcs)' in registration)
        report['registration'] = dict(first_provider_wins=True, table_copied=False,
                                     callback_coverage_or_size_check=False, runtime_registration_executed=False)
        consumers = parents['consumers']
        report['provider_entry'] = dict(public_source_entry='corecrypto_kext_start',
                                        selected_direct_object_reference=consumers.get('_corecrypto_kext_start', []),
                                        selected_direct_stop_reference=consumers.get('_corecrypto_kext_stop', []),
                                        initializer_linked_or_executed_qualified=False,
                                        warning='A required archive search flag does not establish extraction or execution of its provider startup member')
        report['consumer_references'] = {field: [] for field in fields}
        report['demand_source_hashes'] = {}
        for selected in parents['coherent_objects']:
            source = root / selected['source']
            if source.suffix not in ['.c', '.cpp', '.cc', '.h', '.m', '.mm']:
                continue
            verify_hash(source, selected['source_sha256'])
            report['demand_source_hashes'][selected['source']] = selected['source_sha256']
            data = source.read_bytes()
            if b'g_crypto_funcs' not in data:
                continue
            bind(source, selected['source_sha256'])
            for i, line in enumerate(data.decode(errors='replace').splitlines(), 1):
                for field in re.findall(r'g_crypto_funcs\s*->\s*(\w+)', line):
                    if field in report['consumer_references']:
                        report['consumer_references'][field].append(dict(file=selected['source'], selected_object=selected['id'], line=i, text=line.strip()))
        # The shared header defines inline wrappers and is demand even when
        # their text is not spelled directly in a consuming translation unit.
        for name in ['libkern/libkern/crypto/crypto_internal.h', 'libkern/libkern/crypto/rand.h']:
            data = run(['git', '-C', root / 'references/apple-xnu', 'show', manifest['xnu_revision'] + ':' + name], 'demand-header-' + Path(name).stem).decode()
            for i, line in enumerate(data.splitlines(), 1):
                for field in re.findall(r'g_crypto_funcs\s*->\s*(\w+)', line):
                    if field in report['consumer_references']:
                        report['consumer_references'][field].append(dict(file=name, source_revision=manifest['xnu_revision'], line=i, text=line.strip(), kind='pinned-inline-header'))
        for row in report['table']['fields']:
            row['source_demand_count'] = len(report['consumer_references'][row['field']])
            row['demand_scope'] = 'Direct text references in actual selected translation units and two pinned inline headers; not runtime reachability'
        report['public_source_coverage']['missing_fields_with_direct_selected_text_demand'] = [
            field for field in public_missing if report['consumer_references'][field]]
        report['public_source_coverage']['coverage_policy_is_an_Apple_ABI_requirement'] = False
        report['public_source_coverage']['coverage_failure_proves_binary_incompatibility'] = False
        catalog = json.loads(bind(WORKTREE / 'fixtures/public/corecrypto-provider/registration-abi.json').read_text())
        check('committed-56-slot-catalog-matches-actual-observation', catalog['table'] == report['table'] and
              catalog['consumer_references'] == report['consumer_references'])
        report['peak_child_RSS_KiB'] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        report['outcome'] = 'pass'
        report['summary'] = 'Bounded genuine selected crypto input/ABI audit passes; full provider absent: 21 unsupported minicrypto slots, restricted public source omits 13 selected slots, required cc_kext remains unsupplied.'
    except Exception as error:
        report['error'] = repr(error)
    finally:
        for module in list(sys.modules.values()):
            name = getattr(module, '__file__', None)
            if name and str(WORKTREE / 'tools/build') in name and Path(name).is_file():
                report['source_inputs'][rel(Path(name))] = digest(Path(name))
        paths = sorted(path for path in out.rglob('*') if path.is_file())
        report['artifacts'] = [rel(path) for path in paths]
        report['sha256'] = {rel(path): digest(path) for path in paths}
        (out / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report.get(key) for key in ['outcome', 'error', 'summary', 'peak_child_RSS_KiB']}, indent=2))
    print('Actual checks:', len(report['checks']))
    return 0 if report['outcome'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
