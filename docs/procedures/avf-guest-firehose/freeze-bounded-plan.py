"""Freeze exact component commands and read-only tool/runtime inputs; never execute them."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
BASE = ROOT / 'docs/procedures/avf-guest-firehose'
PLAN = BASE / 'bounded-plan-session1'
OUT = BASE / 'execution-session1'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def bind(path):
    p = Path(path)
    return dict(path=str(p), sha256=sha(p), size_bytes=p.stat().st_size)


def dump(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n')


def main():
    assert PLAN.is_dir() and not OUT.exists()
    frozen = BASE / 'preparation-session3/compile-plan.json'
    assert sha(frozen) == 'f6c1f5ef1dd60353ae887bc257f0c900f0c8ba0fdf8f5bb1c3e31c62b940b197'
    capsule = BASE / 'admission-controls-session2.json'
    assert sha(capsule) == '5d2212987504e84712b5d10c5bafe8d4b5626c2f2bfb429dc0d63914b8d2926a'
    recipes = json.loads(frozen.read_text())['recipes']
    commands = []
    for row in recipes:
        old = row['argv_template']
        argv = old.copy()
        for flag, suffix in [('-o', '.o'), ('-MF', '.d')]:
            i = old.index(flag) + 1
            expected = '@OWNED_OUTPUT@/' + row['id'].split('/')[1] + suffix
            assert old[i] == expected
            argv[i] = str(OUT / Path(expected).name)
        assert [i for i, (a, b) in enumerate(zip(old, argv)) if a != b] == sorted([old.index('-MF') + 1, old.index('-o') + 1])
        assert '-nostdinc' in argv
        assert not any(a in ['-resource-dir', '-idirafter', '-isysroot', '--sysroot'] or a.startswith(('-resource-dir=', '--sysroot=')) for a in argv)
        assert sha(row['source']['path']) == row['source']['sha256']
        assert sha(row['configuration']['path']) == row['configuration']['sha256']
        commands.append(dict(id=row['id'], argv=argv, cwd=row['cwd'],
            expected_output=argv[argv.index('-o') + 1], depfile=argv[argv.index('-MF') + 1],
            source=row['source'], configuration=row['configuration'],
            admission_required=True, timeout_seconds=120))
    hosts_path = MAIN / 'fixtures/public/xnu-host-tools/qualified-inputs.json'
    hosts = json.loads(hosts_path.read_text())
    tool_rel = 'bin/aarch64-apple-darwin-libtool'
    archiver = MAIN / hosts['macho_prefix'] / tool_rel
    assert sha(archiver) == hosts['macho_files_sha256'][tool_rel]
    members = PLAN / 'provider-members.txt'
    members.write_text(str(OUT / 'provider.o') + '\n')
    commands.append(dict(id='firehose/provider-archive',
        argv=[str(archiver), '-static', '-csD', '-filelist', str(members), '-o', str(OUT / 'libfirehose_kernel.a')],
        cwd=str(OUT), expected_output=str(OUT / 'libfirehose_kernel.a'),
        member_inputs=[str(OUT / 'provider.o')], excluded_probe_objects=[str(OUT / 'provider-layout.o'), str(OUT / 'interface.o')],
        filelist=bind(members), admission_required=True, timeout_seconds=120))
    compiler = Path(commands[0]['argv'][0])
    assert sha(compiler) == recipes[0]['compiler']['sha256']
    readelf = Path('/usr/bin/readelf')
    observations = []
    host_libraries = {}
    for label, tool in [('compiler', compiler), ('archiver', archiver)]:
        texts = {}
        metadata_commands = []
        for flag, name in [('-d', 'dynamic'), ('-l', 'program-headers')]:
            argv = [str(readelf), flag, str(tool)]
            result = subprocess.run(argv, capture_output=True, env=dict(os.environ, LC_ALL='C'), check=True, timeout=30)
            stdout = PLAN / (label + '-' + name + '.stdout.txt')
            stderr = PLAN / (label + '-' + name + '.stderr.txt')
            stdout.write_bytes(result.stdout)
            stderr.write_bytes(result.stderr)
            texts[name] = result.stdout.decode()
            metadata_commands.append(dict(argv=argv, exit_code=result.returncode, stdout=bind(stdout), stderr=bind(stderr)))
        needed = re.findall(r'\(NEEDED\).*\[([^]]+)\]', texts['dynamic'])
        runpaths = re.findall(r'\((?:RUNPATH|RPATH)\).*\[([^]]*)\]', texts['dynamic'])
        interpreter = re.search(r'Requesting program interpreter:\s*([^]]+)', texts['program-headers'])
        library_bindings = []
        for name in needed:
            candidates = [directory / name for directory in [Path('/lib64'), Path('/usr/lib64'), Path('/lib'), Path('/usr/lib'), Path('/usr/lib/x86_64-linux-gnu')] if (directory / name).exists()]
            if not candidates:
                raise ValueError('Host library path is unresolved without invoking loader: ' + name)
            path = candidates[0].resolve(strict=True)
            host_libraries[str(path)] = bind(path)
            library_bindings.append(dict(needed_name=name, existing_candidate_paths=[str(p) for p in candidates], expected_file=bind(path), actual_loader_resolution_measured=False))
        if interpreter:
            path = Path(interpreter[1]).resolve(strict=True)
            host_libraries[str(path)] = bind(path)
        shadows = []
        for cwd in sorted({c['cwd'] for c in commands}):
            directory = Path(cwd)
            shadows.append(dict(cwd=cwd, exists=directory.exists(),
                needed_name_shadows=[str(directory / name) for name in needed if os.path.lexists(directory / name)]))
        assert not any(row['needed_name_shadows'] for row in shadows)
        observations.append(dict(tool=label, file=bind(tool), needed=needed, runpaths=runpaths,
            interpreter=interpreter[1] if interpreter else None, expected_system_library_files=library_bindings,
            cwd_shadow_observations=shadows, metadata_commands=metadata_commands,
            actual_loader_resolution_measured=False,
            required_adapter_gate='Validate all effective ELF search candidates and exact actual loaded libraries; reject shadows before each child'))
    resource_path = MAIN / 'fixtures/public/xnu-kernel-resource-headers/qualified-component.json'
    resource = json.loads(resource_path.read_text())
    assert sha(resource_path) == 'ec099fee0aedf494d8ec277394800b0dfd299695c19ab33bf164b7d96f4d4ddd'
    bundle = resource['resource_bundle']
    resource_files = []
    for name, expected in bundle['headers'].items():
        path = MAIN / bundle['root'] / name
        assert sha(path) == expected
        resource_files.append(bind(path))
    compiler_descriptor_path = MAIN / 'fixtures/public/xnu-compiler-cxx-storage/qualified-component.json'
    compiler_descriptor = json.loads(compiler_descriptor_path.read_text())
    assert compiler_descriptor['compiler']['sha256'] == recipes[0]['compiler']['sha256']
    assert compiler_descriptor['unchanged_resources'] == 'RHDR-002'
    runner = MAIN / 'worktrees/vm-009-20261106/tools/build/avf_kernel_objects.py'
    assert sha(runner) == '13213539409bade16162173c7b39709dbb3c7e78426fe1410b3f940ea01e4e47'
    namespace_descriptor = MAIN / 'fixtures/public/avf-kernel-headers/qualified-component.json'
    namespace = json.loads(namespace_descriptor.read_text())
    state = json.loads((MAIN / 'state/lab.json').read_text())
    experiment = next((e for e in state['experiments'] if e['id'] == 'AVFFH-001'), None)
    if experiment is not None:
        assert experiment['owner'] == 'codex-guest-exec-20261106-cx' and experiment['task'] == 'VM-020'
    result = dict(schema_version=1, task='VM-020', owner='codex-guest-exec-20261106-cx',
        kind='host-test', origin='local-host', outcome='pass', status='planning_only_execution_gates_open',
        recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
        planning_command=dict(argv=sys.orig_argv, exit_code=0, builder=bind(__file__)),
        source_freeze_commit='27303145d33105170a6f9623240c5be0685675fc',
        frozen_plan=bind(frozen), admission_capsule=bind(capsule),
        producer=bind(ROOT / 'tools/build/avf_guest_firehose.py'),
        owned_output_directory=str(OUT), output_directory_exists=False,
        command_count=4, command_order='serial; stop on first non-pass; preserve partial outputs', commands=commands,
        experiment=dict(id='AVFFH-001', status=experiment['status'] if experiment else 'registration_pending',
            owner='codex-guest-exec-20261106-cx', registered=experiment is not None,
            procedure=str(BASE / 'bounded-build-plan.md'), timeout_seconds=600),
        process_engine=bind(runner), execution_adapter=dict(path=None, sha256=None,
            status='missing_reviewed_component_adapter', required_before_root_lease=True),
        resource_policy=dict(max_running_children=1, aggregate_controller_child_rss_bytes=268435456,
            min_mem_available_bytes=4294967296, stable_samples=3, sample_interval_seconds=1,
            per_command_timeout_seconds=120, actual_resource_cost_measured=False),
        compiler=bind(compiler), compiler_descriptor=bind(compiler_descriptor_path),
        archiver=dict(**bind(archiver), qualification_descriptor=bind(hosts_path),
            source_revision='904de2a71d4da6a9b30d2efaf912a10ddc7d9ddb',
            evidence='MACHOTOOLS-004', sdk_binary=False),
        elf_runtime_observations=observations, host_runtime_files=list(host_libraries.values()),
        readelf=bind(readelf),
        compiler_resource_bundle=dict(descriptor=bind(resource_path),
            root=str(MAIN / bundle['root']), files=resource_files,
            source_revision=bundle['source_revision'], inherited_qualification='RHDR-002',
            compiler_qualified_inheritance='CXXST-007 unchanged_resources',
            added_to_compile_argv=False, explicit_resource_dir_argument=None,
            scope='Bound contextual resource provenance; frozen -nostdinc FH recipes have no resource include consumer'),
        namespace_descriptor=bind(namespace_descriptor),
        namespace_index=dict(path=str(MAIN / namespace['artifact_index']), sha256=namespace['artifact_index_sha256'],
            all_sources_rehashed_in_planning=False, require_runtime_exact_index_validation=True),
        sdk=dict(used=False, qualified=False, proprietary_sdk_supplied=False,
            public_guest_namespace='Existing accepted VM008 source/public header context only'),
        compiler_or_archiver_executed=False, loader_or_ldd_executed=False,
        qemu_executed=False, device_executed=False, accepted_for_execution=False,
        missing_gates=['INT003 independently reviewed component adapter path/hash',
            'Effective ELF search-candidate and actual loaded-library closure verification',
            'Fresh shared common boundary and explicit root lease binding exact plan/adapter/runtime',
            'Actual admitted four-command execution and independent artifact/ABI assessment'])
    dump(PLAN / 'plan.json', result)
    print(json.dumps(dict(plan=bind(PLAN / 'plan.json'), experiment=result['experiment'], commands=4, executed=False), indent=2))


if __name__ == '__main__':
    main()
