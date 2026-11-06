#!/usr/bin/env python3
"""Focused source/temporary-filesystem review; never replay the production audit."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

sys.dont_write_bytecode = True
HEAD = 'c11aec8b0281cc82d5f187e83a847c3e69d990ed'
EVIDENCE = '687ae6113b66e7f608bf0ddec0317cda7352674523badc08faf1704ef5abd997'
TOOL = 'c2cbabbf2f337a2828e335c63481de7086144586cf8fb37263ef5ec3c62d9f97'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def blob(path):
    path = Path(path)
    value = hashlib.sha1(b'blob ' + str(path.stat().st_size).encode() + b'\0')
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def stamp():
    return datetime.now(timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--main', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    main_root = args.main.resolve()
    review_root = Path(__file__).resolve().parent
    out = args.out.resolve()
    if not out.is_relative_to(review_root) or out == review_root or out.exists():
        raise ValueError('Fresh own review output required')
    out.mkdir(parents=True)
    started = time.monotonic()
    checks, commands, bindings = [], [], {}
    report = {'kind': 'host-test', 'origin': 'local-host', 'outcome': 'fail', 'recorded_at': stamp(),
              'task': 'REV-045', 'owner': 'codex-review-guest-iig-20261106-ez',
              'experiment': 'REV045FOCUS-001', 'argv': [sys.executable, *sys.argv],
              'summary': 'Focused frozen-source review incomplete', 'checks': checks,
              'commands': commands, 'checked_sha256': bindings, 'compiler_executed': False,
              'corpus_replayed': False, 'generator_executed': False, 'guest_executed': False}

    def check(name, passed):
        checks.append({'name': name, 'pass': bool(passed)})
        if not passed:
            raise ValueError('Review check failed: ' + name)

    def bind(path, expected):
        actual = sha(path)
        check('hash ' + str(path), actual == expected)
        bindings[str(path)] = actual

    def git(producer, *argv):
        env = dict(os.environ, GIT_NO_LAZY_FETCH='1', GIT_OPTIONAL_LOCKS='0', GIT_TERMINAL_PROMPT='0')
        command = ['git', '-C', str(producer), *argv]
        result = subprocess.run(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        commands.append({'argv': command, 'exit_code': result.returncode,
                         'stdout_sha256': hashlib.sha256(result.stdout).hexdigest(),
                         'stderr_sha256': hashlib.sha256(result.stderr).hexdigest()})
        check('read-only Git exit0 ' + argv[0], result.returncode == 0)
        return result.stdout

    try:
        producer = main_root / 'worktrees/vm-032-20261106'
        tool = producer / 'tools/build/avf_guest_iig_closure.py'
        evidence_path = producer / 'docs/procedures/avf-guest-iig-closure/evidence.json'
        bind(evidence_path, EVIDENCE)
        bind(tool, TOOL)
        check('producer exact frozen HEAD', git(producer, 'rev-parse', 'HEAD').decode().strip() == HEAD)
        evidence = read(evidence_path)
        changed = git(producer, 'diff', '--name-only', 'aac27cfbc0d71b34eda33ddf366c72427507ae0b', HEAD).decode().splitlines()
        check('producer changes confined to its three paths', len(changed) == 6 and all(
            path == 'tools/build/avf_guest_iig_closure.py' or path.startswith(('fixtures/public/avf-guest-iig-closure/', 'docs/procedures/avf-guest-iig-closure/')) for path in changed))
        for path in changed:
            check('frozen Git bytes ' + path, hashlib.sha256(git(producer, 'show', HEAD + ':' + path)).hexdigest() == sha(producer / path))
        for path, expected in evidence['sha256'].items():
            bind(main_root / path, expected)
        final = read(producer / 'artifacts/avf-guest-iig-closure/final-run-1/audit/report.json')
        fixture = read(producer / 'fixtures/public/avf-guest-iig-closure/source-audit.json')
        check('source-only scope and summary unchanged', final['summary'] == evidence['result'] == fixture['summary']
              and final['compiler_executed'] is False and final['qemu_executed'] is False
              and fixture['full_selected_apple_abi_qualified'] is False)
        manifest_path = Path(final['inputs'][0]['path'])
        bind(manifest_path, final['inputs'][0]['sha256'])
        manifest = read(manifest_path)
        selected = {row['id']: row for row in manifest if row['component'] == 'iokit'}
        check('exact frozen104 recipe metadata', len(selected) == len(final['iokit_recipes']) == 104)
        for row in final['iokit_recipes']:
            expected = selected[row['id']]
            check('frozen recipe metadata ' + row['id'], row['source']['path'] == expected['bound_source']
                  and row['source']['sha256'] == expected['bound_source_sha256']
                  and row['configuration']['sha256'] == expected['configuration_sha256']
                  and row['argv'] == expected['next_owned_compile_argv_template']
                  and row['genuine_expanded_recipe_sha256'] == hashlib.sha256(expected['genuine_expanded_recipe'].encode()).hexdigest()
                  and row['guest_compile'] == 'unmeasured')
        check('exact17 pair identities', len(final['interfaces']) == 17 and len({row['name'] for row in final['interfaces']}) == 17)
        for interface in final['interfaces']:
            bind(interface['idl']['path'], interface['idl']['sha256'])
            for output in interface['outputs']:
                bind(output['path'], output['sha256'])
            check('interface remains lexical ' + interface['name'], interface['guest_compile'] == 'unmeasured' and interface['selected_apple_abi'] == 'unqualified')
        early = read(producer / 'artifacts/avf-guest-iig-closure/audit-1/report.json')
        corrected = read(producer / 'artifacts/avf-guest-iig-closure/audit-2/report.json')
        check('initial OSObject gap preserved and corrected', early['summary']['interfaces_without_dispatch_bridge'] == ['OSObject'] and corrected['summary']['interfaces_without_dispatch_bridge'] == [] and final['summary']['interfaces_without_dispatch_bridge'] == [])
        history = final['historical_compiles']
        check('historical native failures distinct', len(history) == 17 and sum(row['command']['exit_code'] != 0 for row in history) == 16
              and all(row['guest_result'] == 'unmeasured' and 'native E1S/NDK' in row['context'] for row in history))
        for row in history:
            bind(row['stderr']['path'], row['stderr']['sha256'])
        check('13 typed builtin and3 metaclass failures preserved', sum(any('XNU_NO_TYPE_BUILTINS' in value for value in row['unique_error_messages']) for row in history) == 13
              and {row['name'] for row in history if row['command']['exit_code'] != 0 and not any('XNU_NO_TYPE_BUILTINS' in value for value in row['unique_error_messages'])} == {'OSAction', 'IODispatchQueue', 'IODispatchSource'})
        spec = importlib.util.spec_from_file_location('frozen_iig_source_audit', tool)
        audit = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(audit)
        interfaces = {row['name']: row for row in final['interfaces']}
        data = interfaces['IODataQueueDispatchSource']
        shared_path = Path(data['implementation_provider_references'][0]['provider_candidates'][0]['source']['path'])
        shared = shared_path.read_text()
        body_starts = list(re.finditer(r'^IODataQueueDispatchSource::(\w+_Impl)\s*\([^;{}]*\)\s*\{', shared, re.M))
        check('nine genuine shared function bodies', len(body_starts) == 9 and {match[1] for match in body_starts} == {ref['qualified_name'].split('::')[1] for ref in data['implementation_provider_references']})
        report['shared_definitions'] = [{'method': match[1], 'line': shared[:match.start()].count('\n') + 1} for match in body_starts]
        provider_sources = {}
        for interface in final['interfaces']:
            for reference in interface['implementation_provider_references']:
                for candidate in reference['provider_candidates']:
                    witness = candidate['source']; provider_sources[witness['path']] = witness
                    text = Path(witness['path']).read_text()
                    line = text.splitlines()[candidate['line'] - 1]
                    check('reported provider line ' + reference['qualified_name'], reference['qualified_name'] in line)
                    check('reported provider has source body ' + reference['qualified_name'], re.search(r'^' + re.escape(reference['qualified_name']) + r'\s*\([^;{}]*\)\s*\{', text, re.M) is not None)
        osobject = interfaces['OSObject']['native_declaration_bridges'][0]
        macro_bridge = final['dispatch_macro_bridge']
        for witness in [*provider_sources.values(), osobject, macro_bridge, final['public_rpc_declarations']]:
            bind(witness['path'], witness['sha256'])
            check('independent canonical Git blob SHA1 ' + witness['path'], blob(witness['path']) == witness['canonical_git_blob_sha1'])
        user_server = next(Path(path) for path in provider_sources if path.endswith('/IOUserServer.cpp'))
        check('selected IOUserServer direct shared include', '#include <System/IODataQueueDispatchSourceShared.h>' in user_server.read_text().splitlines()[82])
        check('all9 shared candidates trace exact selected recipe', all(candidate['including_recipe'] == 'iokit/IOUserServer.cpo'
              and len(candidate['include_chain']) == 1 and candidate['include_chain'][0]['from'] == str(user_server)
              and candidate['include_chain'][0]['resolved'] == str(shared_path) for ref in data['implementation_provider_references'] for candidate in ref['provider_candidates']))
        object_text = Path(osobject['path']).read_text()
        meta_text = Path(macro_bridge['path']).read_text()
        check('OSObject corrected long dispatch macro', 'OSDeclareAbstractStructorsWithDispatchAndNoOperators(OSObject);' in object_text)
        check('metaclass exact token-paste bridge', 'className ## _Methods' in meta_text and 'className ## _KernelMethods' in meta_text and '_OSDeclareAbstractStructors(className, dispatch)' in meta_text)
        generated_header = next(Path(row['path']) for row in interfaces['OSObject']['outputs'] if row['path'].endswith('.h'))
        parsed = audit.macros(generated_header.read_text())
        check('focused real OSObject macro extraction', all('OSObject_' + suffix in parsed for suffix in ['Methods', 'KernelMethods', 'VirtualMethods']))
        sample = '#pragma pack(push, 4)\nstruct Demo_Msg\n{\n int value;\n};\n#pragma pack(pop)\nstruct Demo_Rpl\n{\n int result;\n};\n'
        record = audit.records(sample)
        check('record parser preserves lexical packing without layout claim', len(record) == 2 and [row['lexical_pack'] for row in record] == ['push, 4', 'pop'] and all(row['size_and_offsets'] == 'unmeasured' for row in record))
        with tempfile.TemporaryDirectory(dir=out, prefix='owned-source-control-') as temporary:
            root = Path(temporary) / 'source'
            entry = root / 'iokit/Kernel/Entry.cpp'; header = root / 'iokit/System/Provider.h'
            entry.parent.mkdir(parents=True); header.parent.mkdir(parents=True)
            entry.write_text('#include <System/Provider.h>\n')
            header.write_text('#include <System/Provider.h>\n#if 0\nint\nToy::Real_Impl(int value)\n{ return value; }\n#endif\nint\nToy::Prototype_Impl(int value);\n')
            def pins():
                return {str(path.relative_to(root)): {'sha256': sha(path), 'oid': blob(path)} for path in [entry, header]}
            rows = [{'bound_source': str(entry), 'id': 'iokit/Entry.cpo', 'generated_input': False}]
            providers, visited = audit.provider_index(root, rows, pins())
            check('temp header providers and include cycle', visited == 2 and set(providers) == {'Toy::Real_Impl', 'Toy::Prototype_Impl'})
            check('conditional and prototype stay lexical candidates', all(row['conditional_and_type_acceptance'] == 'unmeasured' for candidates in providers.values() for row in candidates))
            report['lexical_limit_control'] = 'Prototype and #if0 candidate intentionally inventoried; current real-provider bodies independently checked; no compiled acceptance inferred.'
            bad = pins(); bad[str(header.relative_to(root))]['sha256'] = '0' * 64
            try:
                audit.provider_index(root, rows, bad)
            except audit.AuditError:
                check('temp changed-header hash rejects', True)
            else:
                check('temp changed-header hash rejects', False)
            entry.write_text('// shared include removed\n')
            providers, visited = audit.provider_index(root, rows, pins())
            check('temp removal of include edge removes providers', visited == 1 and providers == {})
            outside = Path(temporary) / 'outside.h'; outside.write_text('int\nToy::Outside_Impl()\n{ return 1; }\n')
            entry.write_text('#include "../../../outside.h"\n')
            providers, visited = audit.provider_index(root, rows, pins())
            check('temp outside source root excluded', visited == 1 and providers == {})
        report.update(outcome='pass', summary='Independent frozen-source and focused parser/tempfilesystem review passed; no P0/P1/P2 source finding within lexical scope',
                      producer_head=HEAD, producer_evidence_sha256=EVIDENCE,
                      historical_failures=16, provider_files=len(provider_sources), full_selected_abi_qualified=False)
    except Exception as error:
        report['error'] = repr(error)
    finally:
        report['elapsed_seconds'] = time.monotonic() - started
        report['current_image_memory'] = {line.split(':')[0]: int(line.split()[1]) * 1024 for line in Path('/proc/self/status').read_text().splitlines() if line.startswith(('VmHWM:', 'VmRSS:'))}
        report['reviewer_source_sha256'] = sha(__file__)
        if report['current_image_memory']['VmHWM'] > 256 * 1024**2:
            report.update(outcome='fail', error='Reviewer current image exceeds256MiB')
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report.get(key) for key in ['outcome', 'error', 'summary', 'current_image_memory']}, indent=2))
    return report['outcome'] != 'pass'


if __name__ == '__main__':
    raise SystemExit(main())
