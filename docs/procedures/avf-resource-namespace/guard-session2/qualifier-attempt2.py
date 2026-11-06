#!/usr/bin/env python3
"""Derive a source-qualified matching ARM resource namespace without compilation."""
from __future__ import annotations
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = 'avf-resource-namespace-v1'
TASK = 'VM-045'
OWNER = 'codex-guest-resource-namespace-20261106-es'
SELECTED = 'bsd/apfs_deflate.o'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def bound(path):
    p = Path(path)
    return dict(path=str(p), sha256=sha(p), size_bytes=p.stat().st_size)


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def check_pin(path, digest):
    if sha(path) != digest:
        raise ValueError('Frozen input changed: ' + str(path))


def output_path(path):
    path = Path(path).absolute()
    allowed = ROOT / 'docs/procedures/avf-resource-namespace'
    if path == allowed or not path.is_relative_to(allowed) or path.resolve() != path:
        raise ValueError('Fresh canonical owned procedure output required')
    return path


def require_absent(paths):
    if any(os.path.lexists(p) for p in paths):
        raise ValueError('A historical absent root was materialized')


def verify_resources(helper, root, headers):
    if helper.overlay_files(Path(root)) != headers:
        raise ValueError('Missing, wrong, extra or shadowing resource content')


def validate_transition(helper, old, new, old_root, root):
    changes = helper.validate_transition(old, new, old_root, root)
    actual = [(r['id'], e['argv_index']) for r in changes for e in r['replacements']]
    if actual != [(SELECTED, 244)]:
        raise ValueError('Exactly APFS existing resource operand244 must change')
    row = next(r for r in old if r['id'] == SELECTED)
    if row['next_owned_compile_argv_template'][243:245] != ['-idirafter', str(old_root)]:
        raise ValueError('Genuine existing -idirafter at243/244 changed')
    return changes


def namespace_derivation(parent, old_root, root, headers):
    if str(old_root) not in parent['absent_search_roots']:
        raise ValueError('Parent must bind old resource root absence')
    result = dict(roots=sorted([*parent['roots'], str(root)], key=lambda p: (len(Path(p).parts), p)),
        absent_search_roots=[p for p in parent['absent_search_roots'] if p != str(old_root)],
        files={**parent['files'], **{str(root / n): h for n, h in headers.items()}})
    result['sha256'] = canonical(result)
    return result


def object_key(row, manifest, namespace):
    data = dict(schema=SCHEMA, id=row['id'], manifest_sha256=manifest, namespace_sha256=namespace,
        source=row['bound_source'], source_sha256=row['bound_source_sha256'],
        configuration=row['configuration'], configuration_sha256=row['configuration_sha256'],
        compiler=row['next_owned_compile_argv_template'][0], cwd=row['cwd'],
        argv_template_sha256=canonical(row['next_owned_compile_argv_template']))
    return dict(id=row['id'], input_key=canonical(data), binding=data)


def angle_roots(helper, row):
    # Clang searches -I before -isystem before -idirafter, irrespective of
    # their relative positions in argv. -iquote does not apply to angle includes.
    ranks = {'-I': 0, '-isystem': 1, '-idirafter': 2}
    roots = [r for r in helper.include_roots(row) if r['flag'] in ranks]
    return sorted(roots, key=lambda r: ranks[r['flag']])


def closure(helper, row, namespace, root, headers):
    roots = angle_roots(helper, row)
    expected = dict(headers)
    expected.update({n: None for n in ['stdint.h', 'machine/types.h', 'arm/types.h', 'arm/_types.h',
        'sys/cdefs.h', 'ptrcheck.h', *['sys/_types/_' + n + '.h' for n in
        ['int8_t', 'int16_t', 'int32_t', 'int64_t', 'u_int8_t', 'u_int16_t', 'u_int32_t', 'u_int64_t', 'intptr_t', 'uintptr_t']]]})
    nodes = []
    for name, digest in expected.items():
        matches = [Path(r['path']) / name for r in roots if (Path(r['path']) / name).is_file()]
        if not matches:
            raise ValueError('ARM/KERNEL source prerequisite missing: ' + name)
        p = matches[0]
        if digest is not None:
            if p != root / name or sha(p) != digest or len(matches) != 1:
                raise ValueError('Wrong or shadowed matched resource: ' + name)
        elif p.is_relative_to(root) or namespace['files'].get(str(p)) != sha(p):
            raise ValueError('Existing XNU prerequisite was displaced or changed: ' + name)
        edges = [dict(line=i, directive=m[1], delimiter=m[2], spelling=m[3])
            for i, line in enumerate(p.read_text().splitlines(), 1)
            if (m := re.match(r'^\s*#\s*(include(?:_next)?)\s*([<"])([^>"]+)', line))]
        nodes.append(dict(include=name, first_match=bound(p), literal_includes=edges))
    # The three new files have this entire literal include closure. The
    # inherited stdint/type branch is source-qualified under KERNEL+ARM64.
    actual = {n['include']: [e['spelling'] for e in n['literal_includes']] for n in nodes if n['include'] in headers}
    if actual != {'arm_neon.h': ['stdint.h', 'arm_bf16.h'], 'arm_bf16.h': [], 'arm_acle.h': ['stdint.h']}:
        raise ValueError('New resource literal include closure changed')
    return dict(ordered_angle_search_roots=roots, nodes=nodes,
        source_branch_conditions=['KERNEL selects stdint machine/types; its include_next is inactive',
            'arm64 target selects machine/types arm/types branch; i386 branch is inactive',
            'sys/cdefs userland symbol/availability includes inactive under KERNEL',
            'sys/cdefs __has_include(ptrcheck.h) resolves the retained XNU EXTERNAL_HEADERS/ptrcheck.h'],
        qualification='Literal include graph and ARM64/KERNEL source branch review; no preprocessor invocation or compiled ABI measurement',
        inherited_namespace_files=len(namespace['files']), new_header_files=3)


def run(args):
    main = args.main.resolve()
    out = output_path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    inputs_path = ROOT / 'fixtures/public/avf-resource-namespace/inputs.json'
    inputs = json.loads(inputs_path.read_text())
    old_root = main / inputs['old_resource_root']
    root = out / 'resource/lib/clang/17/include'
    report = dict(kind='host-test', origin='local-host', task=TASK, owner=OWNER,
        recorded_at=datetime.now(timezone.utc).isoformat(), outcome='fail', argv=sys.orig_argv,
        builder=bound(__file__), commands=[], checks=[], compiler_executed=False,
        generator_executed=False, archiver_executed=False, guest_executed=False,
        old_objects_reused=False, preprocessed_closure_measured=False, consumer_admitted=False)
    witnesses = {}

    def pin(name, parse=True):
        p = main / inputs[name]
        check_pin(p, inputs[name + '_sha256'])
        witnesses[str(p)] = inputs[name + '_sha256']
        return json.loads(p.read_text()) if parse else p

    def negative(name, action):
        try:
            action()
        except (ValueError, OSError) as error:
            report['checks'].append(dict(name=name, rejected=True, diagnostic=str(error)))
        else:
            raise ValueError('Negative control accepted: ' + name)

    try:
        require_absent([old_root])
        helper_path = pin('parent_helper', False)
        helper = ModuleType('frozen_vm038_namespace_primitives')
        helper.__file__ = str(helper_path)
        data = helper_path.read_bytes()
        if hashlib.sha256(data).hexdigest() != inputs['parent_helper_sha256']:
            raise ValueError('Parent helper changed during capture')
        exec(compile(data, str(helper_path), 'exec'), helper.__dict__)
        rows = pin('parent_manifest'); qualification = pin('parent_qualification')
        namespace = pin('parent_namespace_receipt'); index = pin('parent_index')
        selectors = pin('parent_selectors'); old_keys = pin('parent_input_keys')
        if namespace['sha256'] != inputs['parent_namespace_digest'] or canonical({k:namespace[k] for k in ['roots','absent_search_roots','files']}) != inputs['parent_namespace_digest']:
            raise ValueError('Exact inherited namespace digest required')
        if qualification['namespace_digest'] != namespace['sha256'] or len(namespace['files']) != 6722 or len(index['files']) != 53997:
            raise ValueError('Exact VM038 qualification/full inventory required')
        require_absent(namespace['absent_search_roots'])
        facts = pin('corrected_facts')
        for name in ['previous_facts', 'actual_object_record', 'full_unfiltered_argv']:
            p = main / facts[name]['path']; check_pin(p, facts[name]['sha256']); witnesses[str(p)] = facts[name]['sha256']
        failed = json.loads((main / facts['actual_object_record']['path']).read_text())
        if failed['id'] != SELECTED or failed['outcome'] != 'fail' or failed['command']['argv'][243:245] != ['-idirafter', str(old_root)]:
            raise ValueError('Actual wave20 failure/existing flag binding changed')
        stderr = Path(str(main / facts['actual_object_record']['path']).removesuffix('/bsd_apfs_deflate.o.object.json')) / 'bsd_apfs_deflate.o.stderr.txt'
        # Bind the actual compiler failure through its recorded command stderr.
        if 'stderr_sha256' in failed['command']:
            check_pin(stderr, failed['command']['stderr_sha256'])
            if "'arm_neon.h' file not found" not in stderr.read_text():
                raise ValueError('Expected actual missing resource diagnostic differs')
            witnesses[str(stderr)] = sha(stderr)
        generation = pin('generation_report'); compiler_report = pin('compiler_report')
        compiler = pin('compiler', False); generator = pin('generator', False)
        if compiler_report['source_revision'] != inputs['source_revision'] or compiler_report['compiler_sha256'] != inputs['compiler_sha256'] or compiler_report['resource_parent']['sha256'] != inputs['generation_report_sha256']:
            raise ValueError('Final compiler does not inherit exact matching resource generation')
        bundle = generation['resource_bundle']
        if bundle['headers'] != inputs['headers'] or bundle['source_revision'] != inputs['source_revision'] or bundle['generator_sha256'] != inputs['generator_sha256']:
            raise ValueError('Matching public resource generation identity differs')
        if any(r['next_owned_compile_argv_template'][0] != str(compiler) for r in rows):
            raise ValueError('1080 parent compiler identities differ')
        for row in rows:
            for field in ['bound_source','configuration']:
                if namespace['files'].get(row[field]) != row[field + '_sha256']:
                    raise ValueError('Parent does not bind source/config: ' + row['id'])
        source_files = []
        relative = [p.split('/compiler-source/', 1)[1] for p in inputs['source_inputs']]
        argv = ['git','-C',str(main/'references/xnu-tapi'),'ls-tree',inputs['source_revision'],'--',*relative]
        env = dict(os.environ, GIT_NO_LAZY_FETCH='1', GIT_OPTIONAL_LOCKS='0', GIT_TERMINAL_PROMPT='0')
        result = subprocess.run(argv, capture_output=True, timeout=30, env=env)
        (out/'canonical-source-blobs.stdout.txt').write_bytes(result.stdout)
        (out/'canonical-source-blobs.stderr.txt').write_bytes(result.stderr)
        report['commands'].append(dict(argv=argv, exit_code=result.returncode))
        if result.returncode:
            raise ValueError('Read-only canonical public Git tree inspection failed')
        blobs = {line.split('\t',1)[1]:line.split()[2] for line in result.stdout.decode().splitlines()}
        for path, digest in inputs['source_inputs'].items():
            p = main / path; check_pin(p,digest); witnesses[str(p)] = digest
            blob = hashlib.sha1(('blob ' + str(p.stat().st_size) + '\0').encode())
            with p.open('rb') as stream:
                for block in iter(lambda:stream.read(1024*1024), b''): blob.update(block)
            name = path.split('/compiler-source/',1)[1]
            if blob.hexdigest() != blobs.get(name):
                raise ValueError('Prepared source differs from canonical Git blob: ' + name)
            source_files.append(dict(**bound(p), git_blob_sha1=blob.hexdigest(), canonical_path=name))
        depfiles = []
        for path, digest in inputs['generation_depfiles'].items():
            p = main / path; check_pin(p,digest); witnesses[str(p)] = digest
            depfiles.append(dict(**bound(p), text=p.read_text()))
        root.mkdir(parents=True)
        for name,digest in inputs['headers'].items():
            source = main / inputs['resource_source_root'] / name
            check_pin(source,digest); witnesses[str(source)] = digest
            shutil.copyfile(source,root/name)
        verify_resources(helper,root,inputs['headers'])
        for name in ['clang','llvm']:
            shutil.copyfile(main / ('artifacts/xnu-compiler-types/frontend-session1/compiler-source/src/' + name + '/LICENSE.TXT'),out/(name+'-LICENSE.TXT'))
        new_rows = copy.deepcopy(rows)
        for row in new_rows:
            row['next_owned_compile_argv_template'],_ = helper.replacement(row,old_root,root)
        changes = validate_transition(helper,rows,new_rows,old_root,root)
        manifest = out/'next-full-object-manifest.json'; dump(manifest,new_rows)
        new_namespace = namespace_derivation(namespace,old_root,root,inputs['headers'])
        ns_path = out/'input-bindings.json'; dump(ns_path,new_namespace)
        manifest_sha = sha(manifest)
        flat = [i for shard in selectors['shards'].values() for i in shard]
        if len(flat) != 1080 or len(set(flat)) != 1080 or set(flat) != {r['id'] for r in rows} or selectors['sha256'] != inputs['parent_manifest_sha256'] or (main/selectors['source_manifest']).resolve() != (main/inputs['parent_manifest']).resolve():
            raise ValueError('Parent selector identity/ordered partition differs')
        new_selectors = copy.deepcopy(selectors)
        new_selectors.update(source_manifest=str(manifest.relative_to(main)),sha256=manifest_sha)
        selectors_path = out/'object-shards.json'; dump(selectors_path,new_selectors)
        keys = [object_key(r,manifest_sha,new_namespace['sha256']) for r in new_rows]
        if [k['id'] for k in old_keys['keys']] != [r['id'] for r in rows] or any(a['input_key']==b['input_key'] for a,b in zip(keys,old_keys['keys'])):
            raise ValueError('Cross-version object keys reused or parent IDs differ')
        keys_path = out/'object-input-keys.json'; dump(keys_path,dict(schema=SCHEMA,keys=keys))
        transition = out/'manifest-transition.json'; dump(transition,dict(parent_manifest_sha256=inputs['parent_manifest_sha256'],new_manifest=bound(manifest),rows=changes,changed_rows=1,exact_changed_argv_index=244,preserved_flag_index=243))
        selected = next(r for r in new_rows if r['id']==SELECTED)
        closure_path = out/'source-type-closure.json'; dump(closure_path,closure(helper,selected,namespace,root,inputs['headers']))
        proof = out/'canonical-resource-proof.json'
        dump(proof,dict(source_revision=inputs['source_revision'],canonical_sources=source_files,
            generation_report=bound(main/inputs['generation_report']), compiler_report=bound(main/inputs['compiler_report']),
            final_compiler=bound(compiler),generator=bound(generator),generator_executed=False,
            generation_commands=[c for c in generation['commands'] if '-gen-arm-neon' in c['argv'] or '-gen-arm-bf16' in c['argv']],
            generation_depfiles=depfiles,generated_headers={n:bound(root/n) for n in inputs['headers']},
            recipe='Reuse exact already-generated RHDR002 arm_neon/arm_bf16; arm_acle exact canonical public source copy; no regeneration',
            corrected_existing_flag_facts=bound(main/inputs['corrected_facts']),actual_wave20_failure=bound(main/facts['actual_object_record']['path']),
            prior_missing_flag_hypothesis_superseded=True,make_expansion_modified=False))
        controls=out/'controls';controls.mkdir()
        wrong = controls/'wrong-resource';wrong.mkdir()
        for n in inputs['headers']:shutil.copyfile(root/n,wrong/n)
        with (wrong/'arm_bf16.h').open('a') as stream:stream.write('\n/* actual owned tamper */\n')
        negative('wrong-resource-bytes',lambda:verify_resources(helper,wrong,inputs['headers']))
        extra=controls/'shadow-resource';extra.mkdir()
        for n in inputs['headers']:shutil.copyfile(root/n,extra/n)
        (extra/'stdint.h').write_text('/* unexpected stdint shadow */\n')
        negative('extra-shadow-file',lambda:verify_resources(helper,extra,inputs['headers']))
        missing=controls/'missing-resource';missing.mkdir()
        negative('missing-resource',lambda:verify_resources(helper,missing,inputs['headers']))
        links=controls/'symlink-resource';links.mkdir();(links/'arm_neon.h').symlink_to(root/'arm_neon.h')
        negative('resource-symlink',lambda:verify_resources(helper,links,inputs['headers']))
        (links/'arm_neon.h').unlink()
        source_control=controls/'changed-source.td';shutil.copyfile(main/next(iter(inputs['source_inputs'])),source_control)
        with source_control.open('a') as stream:stream.write('\n// actual source mutation\n')
        negative('source-byte-mutation',lambda:check_pin(source_control,inputs['source_inputs'][next(iter(inputs['source_inputs']))]))
        negative('wrong-resource-pin',lambda:check_pin(root/'arm_bf16.h','0'*64))
        materialized=controls/'formerly-absent';materialized.mkdir()
        negative('materialized-old-root',lambda:require_absent([materialized]))
        negative('unowned-output',lambda:output_path(main/'artifacts/unowned-resource-output'))
        alias=controls/'output-alias';alias.symlink_to(controls,target_is_directory=True)
        negative('symlink-output',lambda:output_path(alias/'fresh'));alias.unlink()
        for name,mutation in [('later-profile-override',lambda r:r['next_owned_compile_argv_template'].append('-UDEVELOPMENT')),
                ('changed-existing-flag',lambda r:r['next_owned_compile_argv_template'].__setitem__(243,'-I')),
                ('extra-include-flag',lambda r:r['next_owned_compile_argv_template'].extend(['-I','/usr/include'])),
                ('source-binding-mutation',lambda r:r.update(bound_source_sha256='0'*64)),
                ('wrong-resource-path',lambda r:r['next_owned_compile_argv_template'].__setitem__(244,str(root.parent)))]:
            changed=copy.deepcopy(new_rows);mutation(next(r for r in changed if r['id']==SELECTED))
            negative(name,lambda:validate_transition(helper,rows,changed,old_root,root))
            del changed
        wrong_ns=copy.deepcopy(new_namespace);wrong_ns['files'][str(root/'arm_neon.h')]='0'*64
        negative('namespace-byte-mutation',lambda:helper.verify_namespace_exact(wrong_ns,new_namespace))
        report['checks'].append(dict(name='exact-ordered1080-positive',passed=True,changed_rows=1,generated_rows=sum(r['generated_input'] for r in rows),new_namespace_files=len(new_namespace['files']),all_keys_changed=True))
        require_absent(namespace['absent_search_roots'])
        for p,digest in witnesses.items():check_pin(p,digest)
        contract=out/'consumer-admission-contract.json'
        dump(contract,dict(schema=SCHEMA,manifest=bound(manifest),namespace=new_namespace['sha256'],input_keys=bound(keys_path),
            parent_manifest=dict(path=str(main/inputs['parent_manifest']),sha256=inputs['parent_manifest_sha256']),
            parent_namespace=namespace['sha256'],parent_qualification=bound(main/inputs['parent_qualification']),
            parent_selectors=bound(main/inputs['parent_selectors']),derived_selectors=bound(selectors_path),
            retired_absent_root=str(old_root),new_root=str(root),changed_rows=[SELECTED],argv_index=244,flag='-idirafter',
            required_route='Independent CN/root source review, then separately reviewed consumer admission after VM044; old AF193/be02 admission must reject this new version',
            invariants=['Preserve all1080 ordered IDs/source/config/generated/compiler/make/flags except exact APFS operand244',
                'Require exact new complete namespace/index/root content/keys/selectors before any compiler',
                'Reject previous-schema/key sidecars on resume; old accepted objects retain their old provenance',
                'No implicit object reuse/relabeling across versions; no old physical roots or receipts mutated'],
            object_key_algorithm='SHA256 compact sorted JSON of each binding in object-input-keys.json',actual_retry_authorized=False))
        index_files=dict(index['files'])
        # Preserve the inherited metadata index and explicitly index every
        # newly consumed witness, including the corrected actual failure.
        normalized = {str((main/Path(p)).absolute()):h for p,h in index_files.items()}
        for p,digest in witnesses.items():
            if p in normalized and normalized[p] != digest:
                raise ValueError('Inherited index conflicts with a consumed source witness: ' + p)
            if p not in normalized:index_files[p]=digest
        for p in sorted(out.rglob('*')):
            if p.is_file() and not p.is_symlink():index_files[str(p)]=sha(p)
        for p in [Path(__file__),inputs_path]:index_files[str(p)]=sha(p)
        index_path=out/'artifact-index.json';dump(index_path,dict(kind='host-test',origin='local-host',
            scope='Complete inherited53997-file index plus all new inputs; excludes self/descriptor/final evidence to avoid hash cycles',
            parent_index=bound(main/inputs['parent_index']),files=index_files))
        descriptor=dict(schema_version=1,namespace_version=SCHEMA,task=TASK,owner=OWNER,kind='host-test',
            status='source-only resource namespace pending independent acceptance',
            parents={n:dict(path=str(main/inputs[n]),sha256=inputs[n+'_sha256']) for n in ['parent_manifest','parent_qualification','parent_index','parent_namespace_receipt']},
            parent_namespace_digest=namespace['sha256'],old_root=dict(path=str(old_root),still_absent=True),
            new_root=dict(path=str(root),files=inputs['headers']),object_manifest=bound(manifest),selectors=bound(selectors_path),
            namespace_receipt=bound(ns_path),namespace_digest=new_namespace['sha256'],object_input_keys=bound(keys_path),
            manifest_transition=bound(transition),artifact_index=bound(index_path),source_proof=bound(proof),
            source_type_closure=bound(closure_path),consumer_contract=bound(contract),
            inherited_parent_namespace_files=len(namespace['files']),new_namespace_files=len(new_namespace['files']),
            inherited_artifact_files=len(index['files']),new_artifact_files=len(index_files),complete_parent_input_binding_preserved=True,
            compiler_executed=False,generator_executed=False,old_objects_reused=False,actual_APFS_compile=False,sdk_qualified=False,private_abi_qualified=False)
        dump(out/'qualified-component.json',descriptor)
        report.update(outcome='pass',summary='Matching genuine three-header resource root and exact APFS existing-operand-only namespace/1080manifest derivation; no compiler',qualified_component=bound(out/'qualified-component.json'),parent_witnesses_unchanged=True,old_resource_root_still_absent=True,new_namespace_digest=new_namespace['sha256'])
    except Exception as error:
        report['error']=str(error)
        raise
    finally:
        report['proc_status']=[line.strip() for line in Path('/proc/self/status').read_text().splitlines() if line.startswith(('VmRSS:','VmHWM:'))]
        dump(out/'evidence.json',report)
    return 0


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--main',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    return run(parser.parse_args())


if __name__=='__main__':
    try:sys.exit(main())
    except (ValueError,OSError,subprocess.SubprocessError) as error:
        print(str(error),file=sys.stderr);sys.exit(1)
