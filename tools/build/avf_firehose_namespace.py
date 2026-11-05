#!/usr/bin/env python3
"""Derive a versioned public firehose install namespace without compiling XNU."""
from __future__ import annotations
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = 'avf-firehose-namespace-v1'
FLAGS = ['-DKERNEL=1', '-DOS_FIREHOSE_SPI=1', '-DOS_VOUCHER_ACTIVITY_SPI_TYPES=1', '-UOS_VOUCHER_ACTIVITY_SPI']
HEADER = 'os/firehose_buffer_private.h'
OLD_ROOT = 'worktrees/vm-008-20261105/artifacts/avf-kernel-headers/handoff-1/public-source-context/usr/local/include/kernel'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(data)
    return h.hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def dump(path, data):
    Path(path).write_text(json.dumps(data, indent=2) + '\n')


def bound(path):
    p = Path(path)
    return dict(path=str(p), sha256=sha(p), size_bytes=p.stat().st_size)


def load_pin(main, inputs, name):
    p = main / inputs[name]
    if sha(p) != inputs[name + '_sha256']:
        raise ValueError('Frozen input changed: ' + name)
    return json.loads(p.read_text())


def include_roots(row):
    a = row['next_owned_compile_argv_template']
    roots = []
    for i, token in enumerate(a):
        if token in ['-I', '-isystem', '-iquote', '-idirafter']:
            p = Path(a[i + 1]); roots.append(dict(argv_index=i + 1, joined=False, flag=token, path=str((Path(row['cwd']) / p).absolute())))
        elif token.startswith('-I') and len(token) > 2:
            p = Path(token[2:]); roots.append(dict(argv_index=i, joined=True, flag='-I', path=str((Path(row['cwd']) / p).absolute())))
    return roots


def replacement(row, old_root, new_root):
    a = row['next_owned_compile_argv_template'].copy()
    edits = []
    for slot, root in enumerate(include_roots(row)):
        if root['path'] == str(old_root):
            i = root['argv_index']
            new = ('-I' if root['joined'] else '') + str(new_root)
            edits.append(dict(search_slot_zero_based=slot, argv_index=i, old=a[i], new=new))
            a[i] = new
    return a, edits


def validate_transition(old_rows, new_rows, old_root, new_root):
    if len(old_rows) != 1080 or len(new_rows) != 1080 or [r['id'] for r in old_rows] != [r['id'] for r in new_rows]:
        raise ValueError('Exact ordered 1080-row graph required')
    changes = []
    for before, after in zip(old_rows, new_rows):
        expected = copy.deepcopy(before)
        expected['next_owned_compile_argv_template'], edits = replacement(before, old_root, new_root)
        if expected != after:
            raise ValueError('Undeclared source/config/order/flags/tool/template change: ' + before['id'])
        changes.append(dict(id=before['id'], replacements=edits,
            source_sha256=before['bound_source_sha256'], configuration_sha256=before['configuration_sha256'],
            old_argv_digest=canonical(before['next_owned_compile_argv_template']),
            new_argv_digest=canonical(after['next_owned_compile_argv_template'])))
    return changes


def verify_export_recipe(config, project, flags):
    actual = shlex.split(re.search(r'^COPY_HEADERS_UNIFDEF_FLAGS = (.+)$', config, re.M)[1])
    if flags != FLAGS or actual != FLAGS or 'COPY_HEADERS_RUN_UNIFDEF = YES' not in config:
        raise ValueError('Genuine four-flag kernel export changed')
    if re.search(r'^PRIVATE_HEADERS_FOLDER_PATH = (.+)$', config, re.M)[1] != '/usr/local/include/kernel/os':
        raise ValueError('Canonical private kernel install directory changed')
    phase = project.split('6E040C611C499B1B00411A2E /* Headers */ = {', 1)[1].split('\n\t\t};', 1)[0]
    if re.findall(r'/\* (\S+ in Headers) \*/', phase) != ['firehose_buffer_private.h in Headers']:
        raise ValueError('Kernel target exported-header set changed')
    # The actual PBXBuildFile declaration marks this kernel header private.
    entries = [line for line in project.splitlines() if 'firehose_buffer_private.h in Headers' in line and 'PBXBuildFile' in line]
    if not any('Private' in line for line in entries):
        raise ValueError('Kernel header private build-file attribute missing')


def overlay_files(root):
    if root.resolve() != root or not root.is_dir():
        raise ValueError('Canonical existing new install root required')
    result = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in [*dirs, *files]:
            if (Path(directory) / name).is_symlink():
                raise ValueError('Overlay symlink is forbidden')
        for name in files:
            p = Path(directory) / name
            result[str(p.relative_to(root))] = sha(p)
    return result


def verify_overlay(root, expected):
    if overlay_files(root) != {HEADER: expected}:
        raise ValueError('Missing, changed or shadowing installed content')


def namespace_derivation(parent, root, old_root, header_sha):
    if str(old_root) not in parent['absent_search_roots']:
        raise ValueError('Parent does not prove canonical root absent')
    fields = dict(roots=sorted([*parent['roots'], str(root)], key=lambda p: (len(Path(p).parts), p)),
        absent_search_roots=[p for p in parent['absent_search_roots'] if p != str(old_root)],
        files={**parent['files'], str(root / HEADER): header_sha})
    fields['sha256'] = canonical(fields)
    return fields


def key(row, manifest_digest, namespace_digest):
    data = dict(schema=SCHEMA, id=row['id'], manifest_sha256=manifest_digest,
        namespace_sha256=namespace_digest, source=row['bound_source'], source_sha256=row['bound_source_sha256'],
        configuration=row['configuration'], configuration_sha256=row['configuration_sha256'],
        compiler=row['next_owned_compile_argv_template'][0], cwd=row['cwd'],
        argv_template_sha256=canonical(row['next_owned_compile_argv_template']))
    return dict(id=row['id'], input_key=canonical(data), binding=data)


def run(args):
    main = args.main.resolve()
    out = args.output.absolute()
    allowed = ROOT / 'docs/procedures/avf-firehose-namespace'
    if not out.is_relative_to(allowed) or out.resolve() != out:
        raise ValueError('Fresh canonical owned procedure output required')
    out.mkdir(parents=True, exist_ok=False)
    report = dict(kind='host-test', origin='local-host', task='VM-038', owner='codex-guest-fh-namespace-20261106-ef',
        recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'), outcome='fail',
        argv=sys.orig_argv, builder=bound(__file__), commands=[], checks=[],
        compiler_executed=False, archive_executed=False, guest_executed=False, device_executed=False,
        old_objects_reused=False, preprocessed_closure_measured=False, full_kernel_qualified=False,
        sdk_qualified=False, accepted_consumer_available=False)
    inputs = json.loads((ROOT / 'fixtures/public/avf-firehose-namespace/inputs.json').read_text())
    old_root = main / OLD_ROOT
    witnesses = {}
    env = dict(os.environ, LC_ALL='C', LANG='C', GIT_NO_LAZY_FETCH='1', GIT_OPTIONAL_LOCKS='0')

    def command(argv, label, expected=(0,)):
        start = time.monotonic()
        result = subprocess.run([str(p) for p in argv], capture_output=True, env=env, timeout=30)
        stdout, stderr = out / (label + '.stdout.txt'), out / (label + '.stderr.txt')
        stdout.write_bytes(result.stdout); stderr.write_bytes(result.stderr)
        report['commands'].append(dict(argv=[str(p) for p in argv], exit_code=result.returncode,
            elapsed_seconds=round(time.monotonic() - start, 3), stdout=bound(stdout), stderr=bound(stderr)))
        if result.returncode not in expected:
            raise ValueError('Actual source/export command failed: ' + label)
        return result.stdout.decode()

    def negative(name, action):
        try:
            action()
        except (ValueError, FileNotFoundError) as error:
            report['checks'].append(dict(name=name, rejected=True, diagnostic=str(error)))
        else:
            raise ValueError('Negative control accepted: ' + name)

    try:
        if os.path.lexists(old_root):
            raise ValueError('Historical absent root was materialized')
        parent_rows = load_pin(main, inputs, 'parent_manifest')
        parent_qualification = load_pin(main, inputs, 'parent_qualification')
        parent_index = load_pin(main, inputs, 'parent_index')
        parent_selectors = load_pin(main, inputs, 'parent_selectors')
        parent_namespace = load_pin(main, inputs, 'parent_namespace_receipt')
        if parent_namespace['sha256'] != inputs['parent_namespace_digest'] or canonical({k:parent_namespace[k] for k in ['roots','absent_search_roots','files']}) != inputs['parent_namespace_digest']:
            raise ValueError('Parent namespace receipt embedded digest differs')
        for row in parent_rows:
            for field in ['bound_source', 'configuration']:
                if parent_namespace['files'].get(row[field]) != row[field + '_sha256']:
                    raise ValueError('Parent full namespace does not bind source/config: ' + row['id'])
        for name in ['parent_manifest', 'parent_qualification', 'parent_index', 'parent_namespace_receipt', 'parent_selectors']:
            witnesses[str(main / inputs[name])] = inputs[name + '_sha256']
        if len(parent_namespace['files']) != 6721 or len(parent_index['files']) != 53976:
            raise ValueError('Frozen parent inventory cardinality changed')
        source = main / 'references/xnu-kernel-firehose'
        if command(['git','-C',source,'rev-parse','HEAD'],'source-revision').strip() != inputs['source_revision']:
            raise ValueError('Genuine public source revision changed')
        tree = command(['git','-C',source,'ls-tree',inputs['source_revision'],'--',*inputs['source_files_sha256']], 'source-blobs')
        blobs = {line.split('\t',1)[1]:line.split()[2] for line in tree.splitlines()}
        source_proof = []
        for name, digest in inputs['source_files_sha256'].items():
            p = source / name
            if sha(p) != digest:
                raise ValueError('Pinned canonical source changed: ' + name)
            git_hash = hashlib.sha1(('blob ' + str(p.stat().st_size) + '\0').encode())
            with p.open('rb') as stream:
                for block in iter(lambda:stream.read(1024*1024),b''):git_hash.update(block)
            if git_hash.hexdigest() != blobs[name]:
                raise ValueError('Source differs from canonical Git blob')
            source_proof.append(dict(**bound(p), git_blob_sha1=git_hash.hexdigest()))
        config = (source / 'xcodeconfig/libfirehose_kernel.xcconfig').read_text()
        project = (source / 'libdispatch.xcodeproj/project.pbxproj').read_text()
        verify_export_recipe(config, project, FLAGS)
        unifdef = main / inputs['unifdef']
        if sha(unifdef) != inputs['unifdef_sha256']:
            raise ValueError('Source-built unifdef changed')
        root = out / 'installtree/usr/local/include/kernel'
        header = root / HEADER
        header.parent.mkdir(parents=True)
        command([unifdef,*FLAGS,'-o',header,source / 'os/firehose_buffer_private.h'], 'genuine-kernel-export', (0,1))
        verify_overlay(root, inputs['exported_header_sha256'])
        shutil.copyfile(source / 'LICENSE', out / 'libdispatch-LICENSE')
        new_rows = copy.deepcopy(parent_rows)
        for row in new_rows:
            row['next_owned_compile_argv_template'], _ = replacement(row, old_root, root)
        changes = validate_transition(parent_rows, new_rows, old_root, root)
        if any(os.path.lexists(p) for p in parent_namespace['absent_search_roots']):
            raise ValueError('Historical absent search root changed')
        manifest_path = out / 'next-full-object-manifest.json'
        dump(manifest_path, new_rows)
        new_namespace = namespace_derivation(parent_namespace, root, old_root, inputs['exported_header_sha256'])
        namespace_path = out / 'input-bindings.json'; dump(namespace_path, new_namespace)
        manifest_digest = sha(manifest_path)
        flattened = [identifier for shard in parent_selectors['shards'].values() for identifier in shard]
        if len(flattened) != 1080 or len(set(flattened)) != 1080 or set(flattened) != {r['id'] for r in parent_rows} or parent_selectors['sha256'] != inputs['parent_manifest_sha256'] or (main / parent_selectors['source_manifest']).resolve() != (main / inputs['parent_manifest']).resolve():
            raise ValueError('Parent selector identity/partition changed')
        selectors = copy.deepcopy(parent_selectors)
        selectors['source_manifest'] = str(manifest_path.relative_to(main))
        selectors['sha256'] = manifest_digest
        selectors_path = out / 'object-shards.json'; dump(selectors_path, selectors)
        if selectors['shards'] != parent_selectors['shards']:
            raise ValueError('Derived selectors changed ordered IDs/shards')
        keys = [key(row, manifest_digest, new_namespace['sha256']) for row in new_rows]
        old_keys = [key(row, inputs['parent_manifest_sha256'], parent_namespace['sha256']) for row in parent_rows]
        if any(a['input_key'] == b['input_key'] for a,b in zip(keys,old_keys)):
            raise ValueError('Cross-version input keys were reused')
        keys_path = out / 'object-input-keys.json'; dump(keys_path, dict(schema=SCHEMA, keys=keys))
        delta_path = out / 'manifest-transition.json'
        dump(delta_path, dict(parent_manifest_sha256=inputs['parent_manifest_sha256'], new_manifest=bound(manifest_path),
            ordered_ids_preserved=True, unchanged_fields='All fields except declared next_owned_compile_argv_template root tokens',
            rows=changes))
        selected = {r['id']:r for r in new_rows if r['id'] in ['libkern/OSKext.cpo','libkern/log.o','bsd/subr_log.o']}
        closure = []
        direct_names = ['stdint.h','stdbool.h','firehose/tracepoint_private.h','firehose/chunk_private.h',
            'firehose/firehose_types_private.h','mach/mach_types.h','mach/std_types.h','mach/machine/vm_types.h',
            'mach/arm/vm_types.h','os/base.h','machine/types.h','arm/types.h','arm/_types.h','sys/_types/_size_t.h']
        for identifier, row in selected.items():
            roots = include_roots(row)
            root_slots = [i for i,r in enumerate(roots) if r['path'] == str(root)]
            hits = [str(Path(r['path'])/HEADER) for r in roots if (Path(r['path'])/HEADER).is_file()]
            if hits != [str(header)] or len(root_slots) != 1:
                raise ValueError('Missing or shadowing os header search result: ' + identifier)
            resolutions = []
            for name in direct_names:
                candidates = [Path(r['path'])/name for r in roots if (Path(r['path'])/name).is_file()]
                if not candidates:
                    raise ValueError('Source/type prerequisite missing: ' + name)
                p = candidates[0]
                if parent_namespace['files'].get(str(p)) != sha(p):
                    raise ValueError('Type dependency not bound to parent namespace: ' + str(p))
                resolutions.append(dict(include=name, first_match=bound(p),
                    direct_includes=[dict(line=i, directive=m[1], delimiter=m[2], spelling=m[3])
                        for i,line in enumerate(p.read_text().splitlines(),1)
                        if (m:=re.match(r'^\s*#\s*(include(?:_next)?)\s*([<"])([^>"]+)',line))]))
            source_text = Path(row['bound_source']).read_text()
            include_lines = [dict(line=i, text=line) for i,line in enumerate(source_text.splitlines(),1)
                if re.search(r'firehose/(tracepoint|chunk)_private.h|os/firehose_buffer_private.h',line)]
            closure.append(dict(id=identifier, source=bound(row['bound_source']), include_lines=include_lines,
                ordered_search_roots=roots, header_first_match=bound(header), new_root_search_slots_zero_based=root_slots,
                dependencies=resolutions))
        closure_path = out / 'source-type-closure.json'
        dump(closure_path, dict(new_install_content={HEADER:inputs['exported_header_sha256']},
            direct_export_includes=['stdint.h'], preincluded_types='Existing tracepoint/chunk/types and Mach/BSD definitions in frozen parent namespace',
            complete_retained_namespace_files=len(parent_namespace['files']), selected_first_match_edges=closure,
            conditional_scope='Literal include edges recorded with line numbers; KERNEL/ARM64 flags retained. This is not a preprocessor or compiled ABI measurement.',
            broader_new_install_dependencies=[], sdk_supplied=False))
        proof_path = out / 'canonical-export-proof.json'
        dump(proof_path, dict(source_revision=inputs['source_revision'], sources=source_proof,
            install_directory='/usr/local/include/kernel/os', flags=FLAGS,
            private_headers_phase='6E040C611C499B1B00411A2E', header=bound(header),
            unifdef=bound(unifdef), license=bound(out/'libdispatch-LICENSE'),
            previous_genuine_header='VM020 preparation-session3 export; exact output SHA unchanged'))
        controls = out / 'controls'; controls.mkdir()
        negative('reject-changed-export-flags', lambda:verify_export_recipe(config,project,[*FLAGS,'-UKERNEL']))
        altered_source = controls/'changed-source.h'; shutil.copyfile(source/'os/firehose_buffer_private.h',altered_source)
        with altered_source.open('a') as stream:stream.write('\n/* owned mutation control */\n')
        def check_source():
            if sha(altered_source) != inputs['source_files_sha256']['os/firehose_buffer_private.h']:
                raise ValueError('Actual source mutation differs from pin')
        negative('reject-actual-source-mutation',check_source)
        missing = controls/'missing-install'; missing.mkdir()
        negative('reject-missing-new-header',lambda:verify_overlay(missing,inputs['exported_header_sha256']))
        shadow = controls/'shadow-install'; (shadow/'os').mkdir(parents=True)
        shutil.copyfile(header,shadow/HEADER); (shadow/'stdint.h').write_text('/* unexpected shadow file */\n')
        negative('reject-extra-shadow-file',lambda:verify_overlay(shadow,inputs['exported_header_sha256']))
        links = controls/'symlink-install'; (links/'os').mkdir(parents=True)
        (links/HEADER).symlink_to(header)
        negative('reject-installed-symlink',lambda:verify_overlay(links,inputs['exported_header_sha256']))
        (links/HEADER).unlink()  # Retain the observed rejection without shipping symlink aliases.
        for name, edit in [('reject-later-profile-override',lambda r:r['next_owned_compile_argv_template'].append('-UDEVELOPMENT')),
                ('reject-source-binding-change',lambda r:r.update(bound_source_sha256='0'*64))]:
            changed = copy.deepcopy(new_rows); edit(next(r for r in changed if r['id']=='libkern/log.o'))
            negative(name,lambda:validate_transition(parent_rows,changed,old_root,root))
        wrong_namespace = copy.deepcopy(new_namespace); wrong_namespace['files'][str(header)] = '0'*64
        negative('reject-namespace-content-change',lambda:verify_namespace_exact(wrong_namespace,new_namespace))
        report['checks'].append(dict(name='exact-ordered-1080-transition',pass_check=True, changed_rows=sum(bool(r['replacements']) for r in changes),
            generated_rows=sum(r['generated_input'] for r in new_rows), every_new_input_key_differs=True))
        for path,digest in witnesses.items():
            if sha(path) != digest:raise ValueError('Parent witness changed during derivation')
        if os.path.lexists(old_root):raise ValueError('Old absent root changed during derivation')
        contract_path = out/'consumer-admission-contract.json'
        dump(contract_path,dict(schema=SCHEMA, namespace=new_namespace['sha256'], manifest=bound(manifest_path), input_keys=bound(keys_path),
            required_route='Explicit independently reviewed VM039 new-version admission after VM037 ownership release; old afc5-only runner must reject this version',
            parent_namespace=inputs['parent_namespace_digest'], retired_absent_root=str(old_root), new_root=str(root),
            derived_selectors=bound(selectors_path), parent_selectors=dict(path=str(main/inputs['parent_selectors']),sha256=inputs['parent_selectors_sha256']),
            selectors_transition='Only source_manifest and its sha256 identity change; all ordered shard arrays/IDs identical',
            invariants=['All1080 IDs/order/source/config/generated/compiler/resources/flags unchanged except exact declared include-root tokens',
                'Old absent root remains absent; no extra include flag; new root sole content is genuine exported header',
                'Validate complete namespace/index/absence/shadow/symlink identities before any compiler',
                'Require exact new manifest+namespace+input-key schema on every sidecar; reject cross-version resume',
                'Preserve old object provenance; no old objects are relabeled or credited as new-version compilation'],
            object_key_algorithm='SHA256 compact sorted JSON of each binding in object-input-keys.json',
            actual_retry_authorized=False, compiler_executed=False))
        # The full artifact index preserves every inherited indexed witness and
        # adds all current publication inputs before the non-self-indexed capsule.
        index_files = dict(parent_index['files'])
        for p in sorted(out.rglob('*')):
            if p.is_file() and not p.is_symlink():index_files[str(p)] = sha(p)
        for p in [Path(__file__),ROOT/'fixtures/public/avf-firehose-namespace/inputs.json']:
            index_files[str(p)] = sha(p)
        index_path = out/'artifact-index.json'
        dump(index_path,dict(kind='host-test',origin='local-host',scope='Full inherited53976-file artifact index plus new immutable publication inputs; excludes index itself, descriptor and final evidence to avoid self-reference',
            parent_index=dict(path=str(main/inputs['parent_index']),sha256=inputs['parent_index_sha256']), files=index_files))
        descriptor = dict(schema_version=1,namespace_version=SCHEMA,task='VM-038',owner=report['owner'],kind='host-test',
            status='source-only namespace derivation pending independent acceptance', source_proof=bound(proof_path),
            parents={name:dict(path=str(main/inputs[name]),sha256=inputs[name+'_sha256']) for name in ['parent_manifest','parent_qualification','parent_index','parent_namespace_receipt']},
            parent_namespace_digest=inputs['parent_namespace_digest'], old_root=dict(path=str(old_root),still_absent=True),
            new_root=dict(path=str(root),files={HEADER:inputs['exported_header_sha256']}),
            object_manifest=bound(manifest_path),selectors=bound(selectors_path),manifest_transition=bound(delta_path),namespace_receipt=bound(namespace_path),
            namespace_digest=new_namespace['sha256'],object_input_keys=bound(keys_path),artifact_index=bound(index_path),
            source_type_closure=bound(closure_path),consumer_contract=bound(contract_path),
            inherited_parent_namespace_files=len(parent_namespace['files']),new_namespace_files=len(new_namespace['files']),
            inherited_artifact_files=len(parent_index['files']),new_artifact_files=len(index_files),
            complete_parent_input_binding_preserved=True, compiler_executed=False,old_objects_reused=False,
            sdk_qualified=False,private_abi_qualified=False,actual_OSKext_or_log_compile=False)
        dump(out/'qualified-component.json',descriptor)
        report.update(outcome='pass',summary='Genuine one-header canonical install and exact new1080 source-only namespace/manifest/input-key derivation; no compiler or retry',
            qualified_component=bound(out/'qualified-component.json'),parent_witnesses_unchanged=True,
            retired_old_root_still_absent=True,new_namespace_digest=new_namespace['sha256'])
    except Exception as error:
        report['error']=str(error)
        raise
    finally:
        report['proc_status']=[line.strip() for line in Path('/proc/self/status').read_text().splitlines() if line.startswith(('VmRSS:','VmHWM:'))]
        dump(out/'evidence.json',report)
    return 0


def verify_namespace_exact(actual, expected):
    if actual != expected:
        raise ValueError('Namespace differs from exact parent-plus-one-header derivation')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--main',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    return run(parser.parse_args())


if __name__=='__main__':
    try:sys.exit(main())
    except (ValueError,OSError,subprocess.SubprocessError) as error:
        print(str(error),file=sys.stderr);sys.exit(1)
