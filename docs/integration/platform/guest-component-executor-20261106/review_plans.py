#!/usr/bin/env python3
"""Read-only comparison of the two concrete component proposals, without builds."""
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
HERE = Path(__file__).resolve().parent
REPORT = {'kind': 'source-review', 'origin': 'local-host', 'task': 'INT-003',
          'recorded_at': datetime.now(timezone.utc).isoformat(),
          'command': sys.orig_argv, 'bindings': {}, 'checks': [], 'commands': [],
          'compiler_executed': False, 'archiver_executed': False,
          'guest_executed': False, 'registry_mutated': False,
          'original_source_matrix_repeated': False, 'execution_admitted': False}


def sha(path):
    path = Path(path)
    with path.open('rb') as stream:
        result = hashlib.file_digest(stream, 'sha256').hexdigest()
    REPORT['bindings'][str(path)] = result
    return result


def check(name, result):
    REPORT['checks'].append({'name': name, 'pass': bool(result)})
    if not result:
        raise ValueError(name)


def load(path, expected=None):
    if expected:
        check(str(path) + ' exact bytes', sha(path) == expected)
    else:
        sha(path)
    return json.loads(Path(path).read_text())


def git_file(worktree, commit, name, expected):
    command = ['git', 'show', commit + ':' + name]
    result = subprocess.run(command, cwd=worktree,
                            env=dict(os.environ, GIT_NO_LAZY_FETCH='1', GIT_OPTIONAL_LOCKS='0'),
                            capture_output=True, timeout=30)
    REPORT['commands'].append({'argv': command, 'cwd': str(worktree),
                               'exit_code': result.returncode,
                               'stdout_sha256': hashlib.sha256(result.stdout).hexdigest(),
                               'stderr': result.stderr.decode()})
    check('committed plan ' + commit, result.returncode == 0 and
          hashlib.sha256(result.stdout).hexdigest() == expected)


def compare(component, original, concrete, output, token, expected_names):
    check(component + ' four commands', len(concrete) == 4)
    check(component + ' fresh output remains absent', not output.exists() and not output.is_symlink())
    for index, (old, new, name) in enumerate(zip(original, concrete, expected_names)):
        args = old['argv_template']
        expected = list(args)
        for flag, suffix in [('-o', '.o'), ('-MF', '.d')]:
            check(component + flag + name + ' unique', args.count(flag) == 1)
            slot = args.index(flag) + 1
            check(component + flag + name + ' declared token', args[slot] == token + '/' + name + suffix)
            expected[slot] = str(output / (name + suffix))
        check(component + ' exact argv ' + name, new['argv'] == expected)
        check(component + ' exact cwd ' + name,
              new['cwd'] == old.get('cwd', str(output)))
        check(component + ' no materialized product ' + name,
              not (output / (name + '.o')).exists() and not (output / (name + '.d')).exists())
        source = old['source']
        source_path, digest = ((source['path'], source['sha256']) if isinstance(source, dict)
                               else (source, old['source_sha256']))
        check(component + ' actual selected source ' + name, sha(source_path) == digest)
    return concrete[3]


def archive(component, command, output, names, library):
    argv = command['argv']
    check(component + ' exact archive flags', argv[1:4] == ['-static', '-csD', '-filelist'])
    check(component + ' exact archive shape', len(argv) == 7 and argv[5] == '-o')
    check(component + ' archive output', argv[6] == str(output / library) and command['cwd'] == str(output))
    path = Path(argv[4])
    sha(path)
    check(component + ' exact filelist bytes', path.read_bytes() ==
          ''.join(str(output / (name + '.o')) + '\n' for name in names).encode())
    check(component + ' genuine pinned archiver', sha(argv[0]) ==
          'e9b544277b2194a879a1d186c425d2a1b4620e210b9906a72f0a4a02ba0a8005')


def main():
    admission = []
    for index in range(3):
        available = int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines()
                             if x.startswith('MemAvailable:'))) * 1024
        admission.append({'at': datetime.now(timezone.utc).isoformat(), 'MemAvailable_bytes': available})
        check('prospective source-read memory sample ' + str(index), available >= 4 * 1024**3)
        if index != 2:
            time.sleep(1)
    REPORT['admission'] = admission
    sha(__file__)
    sha(sys.executable)
    sha(HERE / 'contract.md')
    old_review = MAIN / 'worktrees/int-platform-20261106/docs/integration/platform/guest-source-20261106/qualified-review.json'
    load(old_review, '3c3a1fcd36c03b4e112e8390daef3eb47de0d2ef9f247cfb86feb18b874c66ff')
    fh = MAIN / 'worktrees/vm-020-20261106'
    pt = MAIN / 'worktrees/vm-021-20261106'
    fh_name = 'docs/procedures/avf-guest-firehose/bounded-plan-session1/plan.json'
    pt_name = 'fixtures/public/avf-guest-pthread/compile-plan.json'
    fh_digest = '1243849185135bb9ab7f861faf4d8fe2fed0c9dcae1e57165a2e9ff7a86008dc'
    pt_digest = '35d7f9a7f2db1db41d8c5c0e83423c1d0d00feff3788d16e3b086bb362f0699b'
    f = load(fh / fh_name, fh_digest)
    p = load(pt / pt_name, pt_digest)
    git_file(fh, '85406c00af5aedfadd64e144da3160791d13d046', fh_name, fh_digest)
    git_file(pt, '5f902346aac0195e19e10c8eeeea0df71ea052d7', pt_name, pt_digest)
    f_original = load(fh / 'docs/procedures/avf-guest-firehose/preparation-session3/compile-plan.json',
                      'f6c1f5ef1dd60353ae887bc257f0c900f0c8ba0fdf8f5bb1c3e31c62b940b197')
    p_original = load(pt / 'artifacts/avf-guest-pthread/prepare-2/component-plan.json',
                      '96065bf4ebe697cfd1a0d43eb52d0ae315275f25efe619e60ae14d66ae350298')
    canonical = hashlib.sha256(json.dumps(p_original, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    check('pthread original canonical freeze', canonical ==
          'bfb88d88d6f44d936fd1fc5758b687ba29ca50f19626e6750224d6db2d69f475')
    f_out = fh / 'docs/procedures/avf-guest-firehose/execution-session1'
    p_out = pt / 'artifacts/avf-guest-pthread/compile-1'
    fa = compare('firehose', f_original['recipes'], f['commands'], f_out,
                 '@OWNED_OUTPUT@', ['provider', 'provider-layout', 'interface'])
    pa = compare('pthread', p_original['translation_units'], p['commands'], p_out,
                 '@OWNED_OUT@', ['kern_init', 'kern_support', 'kern_synch'])
    archive('firehose', fa, f_out, ['provider'], 'libfirehose_kernel.a')
    archive('pthread', pa, p_out, ['kern_init', 'kern_support', 'kern_synch'], 'libpthread_kext.a')
    check('firehose unadmitted', f['accepted_for_execution'] is False and
          f['compiler_or_archiver_executed'] is False)
    check('pthread unadmitted', p['status'] == 'proposed-not-executable' and
          p['compiler_archive_commands_executed'] is False and p['actual_output_hashes'] is None)
    # Read-only task/experiment observation, not a task or experiment mutation.
    ledger = json.loads((MAIN / 'state/lab.json').read_text())
    experiments = ledger['experiments']
    experiments = list(experiments.values()) if isinstance(experiments, dict) else experiments
    REPORT['original_owner_registrations'] = []
    for identity, owner in [('AVFFH-001', 'codex-guest-exec-20261106-cx'),
                            ('AVFPTH-003', 'codex-guest-exec-20261106-cy')]:
        rows = [x for x in experiments if x['id'] == identity]
        check(identity + ' original planned registration', len(rows) == 1 and
              rows[0]['owner'] == owner and rows[0]['status'] == 'planned')
        REPORT['original_owner_registrations'].append(rows[0])
    old_runner = MAIN / 'worktrees/vm-009-20261106/tools/build/avf_kernel_objects.py'
    new_runner = MAIN / 'tools/build/avf_kernel_objects.py'
    check('historical physical process tool', sha(old_runner) ==
          '13213539409bade16162173c7b39709dbb3c7e78426fe1410b3f940ea01e4e47')
    check('accepted current process tool', sha(new_runner) ==
          '5c7b9c549e2740f3fad2a80c060e558dff3c9aa15e98bb2d9a56b33684e687d8')
    trees = [{x.name: ast.dump(x, include_attributes=False) for x in ast.parse(q.read_text()).body
              if isinstance(x, ast.FunctionDef)} for q in [old_runner, new_runner]]
    for name in ['run_child', 'landlock', 'stable_memory', 'supervisor', 'actual_controller_memory']:
        check('unchanged process helper AST ' + name, trees[0][name] == trees[1][name])
    check('accepted supervisor', sha(MAIN / 'tools/build/qemu_host.py') ==
          'faaa9b707a8bb48b1ee502a2c58c9b876eb7859ad5b0ff6541bae27c20ed9f99')
    REPORT['summary'] = 'Both frozen proposals retain exact 3 TU argv/output substitutions plus qualified exact-member filelist archive; registrations are planned only. Shared executor/runtime closure still required.'


out = HERE / 'runs' / sys.argv[1]
out.mkdir(parents=True, exist_ok=False)
status = 0
try:
    main()
    REPORT['outcome'] = 'pass'
except Exception as error:
    REPORT.update(outcome='fail', error=repr(error))
    status = 1
finally:
    REPORT['finished_at'] = datetime.now(timezone.utc).isoformat()
    REPORT['process_memory'] = [s for s in Path('/proc/self/status').read_text().splitlines()
                                if s.startswith(('VmRSS:', 'VmHWM:'))]
    REPORT['exit_code'] = status
    (out / 'evidence.json').write_text(json.dumps(REPORT, indent=2) + '\n')
    print(json.dumps({'outcome': REPORT['outcome'], 'checks': len(REPORT['checks']),
                      'evidence': str(out / 'evidence.json'), 'error': REPORT.get('error')}))
sys.exit(status)
