#!/usr/bin/env python3
"""Independent pinned-source/transform/recipe review; no compiler or guest."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
FH = MAIN / 'worktrees/vm-020-20261106'
PTH = MAIN / 'worktrees/vm-021-20261106'
NAMESPACE = MAIN / 'worktrees/vm-008-20261105/artifacts/avf-kernel-headers'
COMMITS = {'VM020': '76db6b216fcb03c0e2035d37760464acbaca89ca',
           'VM021': 'f10dda9c713c7b6a1516ff77f9d62d8340205805'}
ENV = dict(os.environ, GIT_NO_LAZY_FETCH='1', GIT_OPTIONAL_LOCKS='0',
           GIT_TERMINAL_PROMPT='0', PYTHONDONTWRITEBYTECODE='1')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        while block := f.read(1024 * 1024):
            h.update(block)
    return h.hexdigest()


def must(test, message):
    if not test:
        raise ValueError(message)


def load(path):
    return json.loads(Path(path).read_text())


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    run_name = sys.argv[1]
    must(re.fullmatch(r'[A-Za-z0-9_-]+', run_name), 'Invalid run name')
    out = HERE / 'runs' / run_name
    out.mkdir(parents=True, exist_ok=False)
    local = out / 'local'; local.mkdir()
    r = dict(kind='source-review', origin='local-host', outcome='fail', task='INT-003',
             recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
             source_commits=COMMITS, commands=[], bindings={}, admission=[], checks=[], guard_observations=[],
             compiler_executed=False, archive_created=False, guest_executed=False,
             compiled_layout_qualified=False, provider_closure_qualified=False,
             registry_mutated=False, main_published=False)

    def check(name, condition):
        r['checks'].append(dict(name=name, passed=bool(condition)))
        must(condition, name)

    def bind(path, expected=None):
        path = Path(path)
        actual = sha(path)
        must(expected is None or actual == expected, 'Bound file changed: ' + str(path))
        must(str(path) not in r['bindings'] or r['bindings'][str(path)] == actual, 'Conflicting file identity')
        r['bindings'][str(path)] = actual
        return actual

    def command(argv, label, accepted=(0,)):
        argv = list(map(str, argv))
        started = time.monotonic()
        p = subprocess.run(argv, env=ENV, capture_output=True, timeout=30)
        (out / (label + '.stderr')).write_bytes(p.stderr)
        r['commands'].append(dict(argv=argv, exit_code=p.returncode, elapsed_seconds=time.monotonic()-started,
                                 stdout_sha256=hashlib.sha256(p.stdout).hexdigest(),
                                 stderr_sha256=hashlib.sha256(p.stderr).hexdigest()))
        must(p.returncode in accepted, 'Source command failed: ' + label)
        return p.stdout

    def git(repo, *args, label):
        return command(['git', '-c', 'core.hooksPath=/dev/null', '-C', repo, *args], label)

    def git_tree(repo, revision, label):
        rows = {}
        for entry in git(repo, 'ls-tree', '-rz', revision, label=label).split(b'\0'):
            if not entry:
                continue
            meta, name = entry.split(b'\t', 1)
            mode, kind, blob = meta.decode().split()
            must(kind == 'blob' and mode in ['100644', '100755'], 'Unexpected source member type')
            rows[name.decode()] = blob
        return rows

    def blob(path, expected):
        data = Path(path).read_bytes()
        actual = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        check('canonical-Git-blob-' + str(path), actual == expected)
        bind(path)

    def replay_patch(root, patch, label):
        git(root, 'init', '--quiet', label=label+'-init')
        git(root, 'apply', '--check', patch, label=label+'-check')
        git(root, 'apply', patch, label=label+'-apply')

    try:
        bind(__file__); bind(HERE / 'README.md')
        for i in range(3):
            n = int(re.search(r'^MemAvailable:\s+(\d+)', Path('/proc/meminfo').read_text(), re.M)[1])
            r['admission'].append(dict(at=datetime.now(timezone.utc).isoformat(), MemAvailable_KiB=n))
            must(n >= 4194304, 'Resource-deferred before source child: below4GiB')
            if i < 2:
                time.sleep(1)
        for name, wt, prefixes in [('VM020', FH, ['tools/build/avf_guest_firehose.py', 'fixtures/public/avf-guest-firehose', 'docs/procedures/avf-guest-firehose']),
                                   ('VM021', PTH, ['tools/build/avf_guest_pthread.py', 'fixtures/public/avf-guest-pthread', 'docs/procedures/avf-guest-pthread'])]:
            names = git(MAIN, 'ls-tree', '-r', '--name-only', COMMITS[name], *prefixes, label=name+'-committed-files').decode().splitlines()
            for i, path in enumerate(names):
                data = git(MAIN, 'show', COMMITS[name]+':'+path, label=name+'-frozen-'+str(i))
                bind(wt / path, hashlib.sha256(data).hexdigest())
        policy = load(PTH / 'fixtures/public/avf-guest-pthread/source-policy.json')
        handoff_path = MAIN / policy['handoff_relative']; bind(handoff_path, policy['handoff_sha256'])
        handoff = load(handoff_path)
        bind(handoff['object_manifest'], policy['graph_sha256'])
        rows = load(handoff['object_manifest'])
        check('1080-distinct-new-guest-source-rows', len(rows) == len({x['id'] for x in rows}) == 1080)
        bind(handoff['prepared']['path'], handoff['prepared']['sha256'])
        prepared = load(handoff['prepared']['path']); kernel = Path(prepared['kernel_root'])
        check('prepared-root-is-new-guest-namespace', kernel.is_relative_to(NAMESPACE))
        headers_pin = handoff['parents']['headers']; bind(headers_pin['path'], headers_pin['sha256'])
        headers = load(headers_pin['path']); bind(headers['manifest'], headers['manifest_sha256'])
        installed = [x for x in load(headers['manifest']) if x['status'] == 'installed']
        check('1869-guest-installed-headers', len(installed) == 1869)
        for row in installed:
            check('installed-in-new-namespace-' + row['output'], Path(row['output']).is_relative_to(NAMESPACE))
            bind(row['output'], row['output_sha256'])
        board = kernel / 'pexpert/pexpert/arm64/board_config.h'
        bind(board, prepared['prepared_source_files']['pexpert/pexpert/arm64/board_config.h'])
        selected = board.read_text().split('#ifdef ARM64_BOARD_CONFIG_BCM2837', 1)[1].split('#endif', 1)[0]
        limits = {k: int(re.search(r'^#define\s+'+k+r'\s+(\d+)', selected, re.M)[1]) for k in ['MAX_CPUS', 'MAX_CPU_CLUSTERS']}
        check('BCM2837-source-limits8-and1', limits == {'MAX_CPUS': 8, 'MAX_CPU_CLUSTERS': 1})
        r['selected_board_source'] = dict(path=str(board), sha256=sha(board), limits=limits, compiled=False)

        fhpins = load(FH / 'fixtures/public/avf-guest-firehose/inputs.json')
        fhs = MAIN / 'references/xnu-kernel-firehose'
        tree = git_tree(fhs, fhpins['source_revision'], 'firehose-tree')
        for name, expected in fhpins['source_sha256'].items():
            blob(fhs / name, tree[name]); bind(fhs / name, expected)
        fhe = load(FH / 'docs/procedures/avf-guest-firehose/preparation-session3/evidence.json')
        fhplan = load(fhe['plan']['path']); bind(fhe['plan']['path'], fhe['plan']['sha256'])
        for tool in ['compiler', 'unifdef']:
            bind(MAIN / fhpins[tool]['path'], fhpins[tool]['sha256'])
        for command_row in fhe['commands']:
            for stream in ['stdout', 'stderr']:
                bind(command_row[stream]['path'], command_row[stream]['sha256'])
        export = local / 'firehose-export.h'
        command([MAIN / fhpins['unifdef']['path'], *fhe['header_export']['flags'], '-o', export,
                 fhs / 'os/firehose_buffer_private.h'], 'independent-firehose-unifdef', (0, 1))
        bind(export, fhpins['exported_header_sha256']); bind(fhe['header_export']['path'], sha(export))
        guest_row = next(x for x in rows if x['id'] == 'bsd/subr_log.o')
        bind(guest_row['bound_source'], guest_row['bound_source_sha256'])
        bind(guest_row['configuration'], guest_row['configuration_sha256'])
        baseargv = guest_row['next_owned_compile_argv_template']
        check('guest-kernel-DEVELOPMENT-and-builtins-retained', '-DDEVELOPMENT' in baseargv and '-DXNU_NO_TYPE_BUILTINS=0' in baseargv)
        backend = ['-DDISPATCH_USE_DTRACE=0', '-DOS_ATOMIC_CONFIG_MEMORY_ORDER_DEPENDENCY=1', '-DOS_ATOMIC_CONFIG_STARVATION_FREE_ONLY=0']
        for recipe in fhplan['recipes']:
            bind(recipe['source']['path'], recipe['source']['sha256'])
            actual = recipe['argv_template']; expected = baseargv.copy()
            expected[expected.index(guest_row['bound_source'])] = recipe['source']['path']
            stem = recipe['id'].split('/', 1)[1]
            expected[expected.index('-o')+1] = '@OWNED_OUTPUT@/'+stem+'.o'
            expected[expected.index('-MF')+1] = '@OWNED_OUTPUT@/'+stem+'.d'
            expected[1:1] = ['-I', str(Path(fhe['header_export']['path']).parents[1]), '-I', str(fhs/'src/firehose'), '-I', str(kernel/'libkern/firehose'), *backend]
            for part in ['osfmk','bsd','libkern','iokit','pexpert','libsa','security','san','osfmk/libsa']:
                expected += ['-I', str(kernel/part)]
            check('firehose-exact-guest-recipe-'+stem, actual == expected)
            check('firehose-no-native-archive-or-namespace-'+stem, not any(a.endswith('.a') or 'ARM64_BOARD_CONFIG_E1S' in a or '/artifacts/xnu-kernel-objects/' in a for a in actual))
        check('firehose-archive-excludes-layout-interface-probes', fhplan['archive_policy'] == 'Archive only provider.o; exclude layout and interface probes')
        for probe in fhe['probe_inputs']:
            bind(probe['snapshot']['path'], probe['snapshot']['sha256'])
        provider = Path(fhe['probe_inputs'][0]['snapshot']['path']).read_text()
        check('future-provider-probe-asserts8-and1', 'MAX_CPUS == 8' in provider and 'MAX_CPU_CLUSTERS == 1' in provider)

        pbase = PTH / 'artifacts/avf-guest-pthread/prepare-2'
        pe = load(pbase / 'evidence.json'); plan = load(pbase / 'component-plan.json')
        for path, expected in pe['outputs'].items():
            bind(path, expected)
        psource = MAIN / 'references/xnu-kernel-pthread'; ptree = git_tree(psource, policy['pthread_revision'], 'pthread-tree')
        manifest = load(pbase / 'source-manifest.json')
        check('206-full-pinned-pthread-sources', len(ptree) == len(manifest) == 206)
        byname = {x['path']: x for x in manifest}
        for name, object_id in ptree.items():
            blob(psource/name, object_id)
            bind(psource/name, byname[name]['base_sha256'])
            bind(pbase/'source/pthread'/name, byname[name]['prepared_sha256'])
        patched = local / 'pthread'; patched.mkdir()
        for name in policy['expected_patched_pthread']:
            destination = patched/name; destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((psource/name).read_bytes())
        for number in ['0002','0003']:
            patch = next(MAIN/p for p in policy['patches'] if Path(p).name.startswith(number))
            bind(patch, policy['patches'][str(patch.relative_to(MAIN))])
            replay_patch(patched, patch, number)
        for name, expected in policy['expected_patched_pthread'].items():
            bind(patched/name, expected)
        target_repo = MAIN/'references/puredarwin-build-inputs'; relative = 'src/Libraries/AvailabilityVersions/include/TargetConditionals.h'
        target_blob = git(target_repo, 'ls-tree', policy['target_revision'], '--', relative, label='target-blob').decode().split()[2]
        blob(target_repo/relative, target_blob)
        target = local/'target'; (target/relative).parent.mkdir(parents=True)
        (target/relative).write_bytes((target_repo/relative).read_bytes())
        patch = next(MAIN/p for p in policy['patches'] if Path(p).name.startswith('0001'))
        bind(patch, policy['patches'][str(patch.relative_to(MAIN))]); replay_patch(target, patch, 'target')
        bind(target/relative, policy['expected_target_sha256'])
        cfg = (psource/'xcodescripts/kext.xcconfig').read_text()
        definitions = sum([re.search(r'^GCC_PREPROCESSOR_DEFINITIONS_'+v+r' = (.+)$', cfg, re.M)[1].split() for v in ['kext','kext_development']], [])
        check('native-development-definitions-are-genuine', plan['native_definitions'] == definitions and definitions[-2:] == ['MACH_ASSERT','DEBUG'])
        check('native-development-LTO-disabled', 'LLVM_LTO_development = NO' in cfg and plan['native_development_LTO'] is False)
        for row in plan['translation_units']:
            argv = row['argv_template']; bind(row['source'], row['source_sha256'])
            check('pthread-development-not-weakened-'+Path(row['source']).name,
                  all('-D'+d in argv for d in definitions) and '-DARM64_BOARD_CONFIG_BCM2837' in argv and
                  '-DXNU_NO_TYPE_BUILTINS=0' in argv and '-Werror=implicit-function-declaration' in argv and
                  '-Werror=incompatible-pointer-types' in argv and not any(x in argv for x in ['-UNDEBUG','-DNDEBUG','-UDEBUG','-UMACH_ASSERT','-flto']))
            check('pthread-no-native-archive-or-header-fallback-'+Path(row['source']).name,
                  not any(x.endswith('.a') or '/EXPORT_HDRS/' in x or 'ARM64_BOARD_CONFIG_E1S' in x for x in argv))
        witness = load(pbase/'callback-alias-source-witness.json')
        bind(witness['source'], witness['source_sha256']); bind(witness['installed'], witness['installed_sha256'])
        for alias in witness['alias_inputs']:
            bind(alias['path'], alias['sha256'])
        exports = '\n'.join(Path(x['path']).read_text() for x in witness['alias_inputs'])
        for left, right in policy['native_aliases'].items():
            check('actual-export-alias-'+left, re.search(r'^'+re.escape(left+':'+right)+r'$', exports, re.M) is not None)
        pm = module(PTH/'tools/build/avf_guest_pthread.py', 'reviewed_pthread')
        fm = module(FH/'tools/build/avf_guest_firehose.py', 'reviewed_firehose')
        check('raw-installed-declaration-surface-match', pm.fields(Path(witness['source']).read_text()) == pm.fields(Path(witness['installed']).read_text()) == witness['callback_declarations'])
        r['declarations_only'] = {k: len(v) for k,v in witness['callback_declarations'].items()}
        wrong = deepcopy(plan)
        for row in wrong['translation_units']:
            row['argv_template'] = [x for x in row['argv_template'] if x not in ['-DMACH_ASSERT','-DDEBUG']]
        pm.validate_plan(wrong)
        r['guard_observations'].append(dict(component='VM021', actual_plan_correct=True, weakened_mutation_accepted=True,
                                           mutation='remove both -DMACH_ASSERT and -DDEBUG', scope='source predicate alone; not an execution boundary'))
        wrong = deepcopy(guest_row); wrong['next_owned_compile_argv_template'].append('-UDEVELOPMENT')
        fm.validate_guest_row(wrong, MAIN, Path(baseargv[0]))
        r['guard_observations'].append(dict(component='VM020', actual_plan_correct=True, weakened_mutation_accepted=True,
                                           mutation='append -UDEVELOPMENT after the required -DDEVELOPMENT', scope='source predicate alone; future executor must bind exact argv'))
        check('source-only-no-compiled-promotion', not fhe['compiled'] and not fhe['archive_created'] and not fhe['accepted_for_execution'] and
              plan['compiled_objects'] == [] and not plan['archive']['produced'] and not witness['compiled_ABI_or_provider_closure_qualified'])
        r['outcome'] = 'pass'
        r['summary'] = 'Exact source preparations and transforms agree with pinned new guest namespace/development profile; two narrow mutable-plan guard gaps reproduced; no compiled/ABI/provider acceptance'
    except Exception as error:
        r['error'] = repr(error)
        r['summary'] = 'Bounded source review failed/deferred; retain evidence and do not infer component acceptance'
    finally:
        r['finished_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
        r['process_memory'] = [x for x in Path('/proc/self/status').read_text().splitlines() if x.startswith(('VmHWM:', 'VmRSS:'))]
        r['artifacts'] = [str(p.relative_to(MAIN)) for p in out.iterdir() if p.is_file()]
        r['artifact_hashes'] = {str(p.relative_to(MAIN)): sha(p) for p in out.iterdir() if p.is_file()}
        (out/'evidence.json').write_text(json.dumps(r, indent=2)+'\n')
    print(json.dumps({k:r.get(k) for k in ['outcome','summary','error','guard_observations','process_memory']}, indent=2))
    return r['outcome'] != 'pass'


if __name__ == '__main__':
    raise SystemExit(main())
