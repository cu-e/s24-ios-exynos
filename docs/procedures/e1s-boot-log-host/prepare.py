#!/usr/bin/env python3
"""STR020 source-only host fixture/command preparation. Never execute commands."""
import hashlib
import json
import shutil
from pathlib import Path

MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
ROOT = Path(__file__).resolve().parents[3]
SOURCE = MAIN / 'worktrees/str-019-e1s-boot-log-20261106/artifacts/e1s-boot-log/source-002'
OUT = ROOT / 'artifacts/e1s-boot-log-host/prepare-001'
sha = lambda p: hashlib.file_digest(Path(p).open('rb'), 'sha256').hexdigest()
assert sha(ROOT/'docs/procedures/e1s-boot-log/evidence.json') == 'b9f8cc26154fcc660dc5fa18a97ef974706afc463822ffc276349826d13d60e4'
assert sha(ROOT/'patches/e1s-boot-log/0001-loader-owned-diagnostics.patch') == '569663074fb7de230b4760a613562841afe311352ed32e78275c55708aa21328'
OUT.mkdir(parents=True, exist_ok=False)
source_binding = json.loads((SOURCE/'proposal-bindings.json').read_text())
for rel, row in source_binding['files'].items():
    assert sha(SOURCE/'applied'/rel) == row['proposal_sha256'], rel
    target = OUT/'source'/rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SOURCE/'applied'/rel, target)
loader = (OUT/'source/shim/e1s-xnu/loader.c').read_text()
def between(first, last):
    start = loader.index(first)
    end = loader.index(last, start)
    return loader[start:end], {'start_line': loader[:start].count('\n')+1,
                               'end_line_exclusive': loader[:end].count('\n')+1}
parts = []
ranges = {}
for name, first, last in [
    ('abi', '#define BOOT_LINE_LENGTH', 'uint64_t boot_args_pa;'),
    ('actual_record', '/* CPU-local loader diagnostic record.', 'static uint64_t fb_base;'),
    ('actual_logging', 'static void log_init(', 'static void clean('),
    ('actual_extent', '/* Preserve the existing payload reserve,', 'static int\nchoose_window('),
]:
    part, ranges[name] = between(first, last)
    ranges[name]['sha256'] = hashlib.sha256(part.encode()).hexdigest()
    parts.append(part)
macros = ''.join(line+'\n' for line in loader.splitlines() if line.startswith(
    ('#define LOG_MAGIC\t', '#define LOG_HEADER\t', '#define LOG_MAX\t')))
assert len(macros.splitlines()) == 3
(OUT/'actual-loader-log.inc').write_text(macros + '\n' + '\n'.join(parts))
for f in ['host-controls.c', 'decode-controls.py']:
    shutil.copyfile(ROOT/'fixtures/public/e1s-boot-log-host'/f, OUT/f)
vectors = json.loads((ROOT/'fixtures/public/e1s-boot-log-host/extent-vectors.json').read_text())
lines = ['struct extent_case { uintptr_t image, end, payload; int valid; uint64_t size; };',
         'static const struct extent_case extent_cases[] = {']
for v in vectors['vectors']:
    n = lambda key: 'UINT64_C('+v[key]+')'
    lines.append('    { '+', '.join([n('image'), n('actual_linker_end'), n('selected_payload'),
                 str(int(v['expected_success'])), 'UINT64_C('+(v['expected_reserved_size'] or '0')+')'])+' },')
lines.append('};')
(OUT/'extent-cases.inc').write_text('\n'.join(lines)+'\n')
accepted_plan_path = MAIN/'worktrees/str-005-e1s-framebuffer-fix1-20261106/artifacts/e1s-framebuffer/prepare-3/plan.json'
accepted = json.loads(accepted_plan_path.read_text())
compiler = Path(accepted['commands'][0]['argv'][0])
resource_arg = accepted['commands'][0]['argv'][2]
assert resource_arg.startswith('-resource-dir=')
resource = Path(resource_arg.split('=', 1)[1])
tool_pins = {str(compiler): accepted['input_sha256'][str(compiler)]}
for path, digest in accepted['input_sha256'].items():
    if path.startswith(str(resource)+'/lib/x86_64-unknown-linux-gnu/'):
        tool_pins[path] = digest
assert len(tool_pins) == 5
for path, digest in tool_pins.items():
    assert sha(path) == digest, 'qualified compiler/runtime changed: '+path
flags = ['--target=x86_64-unknown-linux-gnu', resource_arg, '-std=c11', '-O1', '-g',
         '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-Wall', '-Wextra', '-Werror']
binary = OUT/'host-controls'
record = OUT/'records.bin'
env = {'LC_ALL': 'C', 'PYTHONUTF8': '1', 'PYTHONNOUSERSITE': '1',
       'PYTHONDONTWRITEBYTECODE': '1', 'ASAN_OPTIONS': 'detect_leaks=1:halt_on_error=1',
       'UBSAN_OPTIONS': 'halt_on_error=1:print_stacktrace=1'}
commands = [
 {'id': 'compile-actual-functions', 'argv': [str(compiler), *flags, '-MD', '-MF', str(OUT/'host.d'),
      '-I'+str(OUT), str(OUT/'host-controls.c'), '-o', str(binary)], 'expected_exit_code': 0},
 {'id': 'actual-host-controls', 'argv': [str(binary), '--records', str(record)], 'expected_exit_code': 0},
 {'id': 'independent-decoder', 'argv': ['/usr/bin/python3.12', '-B', '-s', str(OUT/'decode-controls.py'),
      str(OUT/'source/tools/e1s/read_log.py'), str(record), str(OUT/'decoder-evidence.json')], 'expected_exit_code': 0},
 {'id': 'negative-asan-control', 'argv': [str(binary), '--negative-asan'], 'expected_exit_code': 1,
      'required_combined_log_substrings': ['AddressSanitizer', 'heap-buffer-overflow']},
 {'id': 'negative-ubsan-control', 'argv': [str(binary), '--negative-ubsan'], 'expected_exit_code': 1,
      'required_combined_log_substrings': ['runtime error:', 'signed integer overflow']},
]
for command in commands:
    command.update(cwd=str(OUT), env=env, timeout_seconds=120)
pins = dict(tool_pins)
for path in OUT.rglob('*'):
    if path.is_file(): pins[str(path)] = sha(path)
for path in [ROOT/'fixtures/public/e1s-boot-log-host/extent-vectors.json', Path(__file__),
             ROOT/'patches/e1s-boot-log/0001-loader-owned-diagnostics.patch',
             ROOT/'docs/procedures/e1s-boot-log/evidence.json', accepted_plan_path,
             Path('/usr/bin/python3.12')]: pins[str(path)] = sha(path)
plan = {'schema': 'e1s-boot-log-host-plan-v2', 'task': 'STR-020', 'source_review_task': 'STR-019',
    'experiment': 'STR020HOST-001', 'owner': 'codex-e1s-boot-log-host-20261106-sr20',
    'phase': 'planned-not-executed-no-grant', 'source_commit': '20fe6376473bd638ec1705e8efd610753bab94fd',
    'commands': commands, 'input_sha256': pins, 'actual_source_ranges': ranges,
    'source_compose_evidence_sha256': sha(ROOT/'docs/procedures/e1s-boot-log/evidence.json'),
    'max_jobs': 1, 'max_owned_rss_bytes': 268435456, 'child_timeout_seconds': 120,
    'whole_timeout_seconds': 600, 'sanitizer_requires_RSS_only_no_small_RLIMIT_AS': True,
    'supervisor': 'existing root-qualified finite RSS supervisor; no new executor',
    'actual_MD_closure_required_after_compile': True,
    'negative_exit_codes_and_diagnostics_are_required_not_ignored': True,
    'outputs_absent_at_preparation': all(not p.exists() for p in [binary, record, OUT/'host.d', OUT/'decoder-evidence.json']),
    'target_object_link_layout_and_native_kernel_diagnostic_gates': 'pending separate review/grant, no target command in this plan'}
assert plan['outputs_absent_at_preparation']
runner = {
 'supervisor': {'path': str(MAIN/'tools/build/qemu_host.py'), 'sha256': 'faaa9b707a8bb48b1ee502a2c58c9b876eb7859ad5b0ff6541bae27c20ed9f99', 'apis': ['sample','pressured','run','terminate']},
 'cancellation': {'path': str(MAIN/'worktrees/vm-022-link-cursor-20261106/tools/build/avf_guest_link_inputs.py'), 'sha256': '9f80e32305ce84e33ab27bcf37d589465a97c2d03c5eb6830fd3540f204400c5', 'apis': ['owned_cancellation','proc_status']},
 'work_guard': {'path': str(MAIN/'worktrees/vm-022-diagnostic-20261106/fixtures/public/avf-guest-link-inputs/run-link-diagnostic.py'), 'sha256': '23b88dcc7c2ca20064b4ad8204d9cc713783f79f858d7e25791b85f58a8803d5', 'apis': ['install_work_guard']},
}
for binding in runner.values(): assert sha(binding['path']) == binding['sha256']
plan['runner_bindings'] = runner
plan['measurement_driver'] = 'pending root narrow adapter; legacy framebuffer driver rejects all nonzero exits and cannot be used unchanged'
plan['expected_negative_raw_exit_and_outcome_preserved'] = True
plan['env_application_required'] = True
plan['supervisor_combines_stderr_into_stdout_log'] = True
plan['worktree_base_commit'] = '7b09b3164bd2266fe577c2d5f9d31685de660609'
(OUT/'plan.json').write_text(json.dumps(plan, indent=2)+'\n')
print(json.dumps({'outcome': 'pass', 'preparation_only': True, 'commands_executed': 0,
                  'plan': str(OUT/'plan.json'), 'plan_sha256': sha(OUT/'plan.json'),
                  'input_pins': len(pins), 'actual_source_sections': len(ranges),
                  'outputs_absent': plan['outputs_absent_at_preparation']}))
