#!/usr/bin/env python3
"""Host checks for the SGPU timeline. No SDK, device, QEMU or GPU.

Runs the tests under ASan/UBSan and TSan, compiles the module for ARM64 Mach-O with
the host clang, then applies single-line mutations and requires the tests to catch each.
The ARM64 compile does not use the kernel's flags and does not show the code builds in XNU.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

SOURCE = Path(__file__).resolve().parent
ROOT = SOURCE.parents[4]
MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
BACKEND = SOURCE.parent/'backend'
ABI = SOURCE.parent.parent/'abi'
SOURCES = [ABI/'sgpu_abi.h', ABI/'sgpu_abi.c', BACKEND/'sgpu_backend.h', BACKEND/'sgpu_backend.c', BACKEND/'test_backend.c',
           SOURCE/'sgpu_timeline.h', SOURCE/'sgpu_timeline.c', SOURCE/'test_timeline.c', SOURCE/'check.py']
WARN = ['-Wall', '-Wextra', '-Werror', '-Wpedantic']
NM = MAIN/'artifacts/xnu-macho-tools/macho-session4/prefix/bin/aarch64-apple-darwin-nm'

MUTATIONS = [
    ('hw lock required', '!hw->lock || ', ''),
    ('hw unlock required', '!hw->unlock || ', ''),
    ('hw clock required', '!hw->now_ns || ', ''),
    ('hw start required', ' || !hw->start)', ')'),
    ('sink retire required', '!sink->retire || ', ''),
    ('sink fault required', '!sink->fault || ', ''),
    ('sink quiesced required', ' || !sink->quiesced)', ')'),
    ('rings nonzero', 'if (!config->rings || config->rings > SGPU_TL_MAX_RINGS)', 'if (config->rings > SGPU_TL_MAX_RINGS)'),
    ('rings bounded', 'if (!config->rings || config->rings > SGPU_TL_MAX_RINGS)', 'if (!config->rings)'),
    ('depth nonzero', 'if (!config->depth || config->depth > SGPU_TL_MAX_DEPTH)', 'if (config->depth > SGPU_TL_MAX_DEPTH)'),
    ('depth bounded', 'if (!config->depth || config->depth > SGPU_TL_MAX_DEPTH)', 'if (!config->depth)'),
    ('32-bit counter allowed', 'config->counter_bits != 32 && config->counter_bits != 64', 'config->counter_bits != 64'),
    ('64-bit counter allowed', 'config->counter_bits != 32 && config->counter_bits != 64', 'config->counter_bits != 32'),
    ('other widths refused', 'config->counter_bits != 32 && config->counter_bits != 64', 'config->counter_bits < 32'),
    ('timeout nonzero', 'if (!config->job_timeout_ns) return SGPU_TL_ARGUMENT;', ''),
    ('32-bit mask used', 'config->counter_bits == 64 ? UINT64_MAX : UINT32_MAX', 'UINT64_MAX'),
    ('64-bit mask used', 'config->counter_bits == 64 ? UINT64_MAX : UINT32_MAX', 'UINT32_MAX'),
    ('initial counter validated', 'for (i = 0; i < config->rings; ++i) if (config->initial_counter[i] & ~mask) return SGPU_TL_ARGUMENT;', ''),
    ('only configured rings validated', 'for (i = 0; i < config->rings; ++i) if (config->initial_counter[i] & ~mask)', 'for (i = 0; i < SGPU_TL_MAX_RINGS; ++i) if (config->initial_counter[i] & ~mask)'),
    ('storage cleared', 'zero_bytes(tl, sizeof(*tl));', ''),
    ('initial counter applied', 'for (i = 0; i < config->rings; ++i) tl->rings[i].last_counter = config->initial_counter[i];', ''),
    ('wait compares sequence', 'if (w->sequence == j->waits[i] && w->state == JOB_ACTIVE) return 1;', 'if (w->state == JOB_ACTIVE) return 1;'),
    ('wait compares state', 'if (w->sequence == j->waits[i] && w->state == JOB_ACTIVE) return 1;', 'if (w->sequence == j->waits[i]) return 1;'),
    ('all waits checked', 'for (i = 0; i < j->wait_count; ++i) {', 'for (i = 0; i < j->wait_count && i < 1; ++i) {'),
    ('waiting index wraps', 'r->waiting_head = (r->waiting_head + 1u) % SGPU_TL_MAX_DEPTH;', 'r->waiting_head = r->waiting_head + 1u;'),
    ('waiting count falls', '--r->waiting_count;', ''),
    ('running index wraps', 'r->running_head = (r->running_head + 1u) % SGPU_TL_MAX_DEPTH;', 'r->running_head = r->running_head + 1u;'),
    ('running count falls', '--r->running_count;', ''),
    ('first fault wins', 'if (tl->faulted) return;', ''),
    ('fault reason kept', 'tl->fault_reason = reason;', ''),
    ('fault reported', 'tl->fault_pending = 1;', ''),
    ('faulted latched', 'tl->faulted = 1;', 'tl->fault_pending = 1;'),
    ('blocked job waits', 'if (job_blocked(tl, j) || r->running_count >= tl->config.depth) return 1;', 'if (r->running_count >= tl->config.depth) return 1;'),
    ('running depth enforced', 'if (job_blocked(tl, j) || r->running_count >= tl->config.depth) return 1;', 'if (job_blocked(tl, j)) return 1;'),
    ('running depth boundary', 'r->running_count >= tl->config.depth) return 1;', 'r->running_count > tl->config.depth) return 1;'),
    ('counter masked at start', '(r->last_counter + r->running_count + 1u) & tl->mask', 'r->last_counter + r->running_count + 1u'),
    ('counter advances past running', '(r->last_counter + r->running_count + 1u) & tl->mask', '(r->last_counter + 1u) & tl->mask'),
    ('counter is one past', '(r->last_counter + r->running_count + 1u) & tl->mask', '(r->last_counter + r->running_count) & tl->mask'),
    ('start failure counted', '++tl->stats.start_failures;', ''),
    ('start failure reported', 'tl->stats.start_failures;\n        return -1;', 'tl->stats.start_failures;\n        return 1;'),
    ('started job leaves waiting', '(void)pop_waiting(r);\n    if (!r->running_count)', 'if (!r->running_count)'),
    ('head clock set on first start', 'if (!r->running_count) r->head_since = tl->hw.now_ns(tl->hw_context);', ''),
    ('head clock kept by later starts', 'if (!r->running_count) r->head_since', 'r->head_since'),
    ('running push wraps', 'r->running[(r->running_head + r->running_count) % SGPU_TL_MAX_DEPTH] = (uint16_t)slot;', 'r->running[r->running_head + r->running_count] = (uint16_t)slot;'),
    ('running count grows', '++r->running_count;', ''),
    ('started counted', '++tl->stats.started;', ''),
    ('pump stops at blocked head', 'if (result > 0) break;', ''),
    ('queued start failure faults', 'if (result < 0) {\n                mark_faulted(tl, SGPU_BE_REASON_FAULT);', 'if (result < 0) {'),
    ('queued failure stops pumping', 'mark_faulted(tl, SGPU_BE_REASON_FAULT);\n                return;', 'mark_faulted(tl, SGPU_BE_REASON_FAULT);\n                break;'),
    ('every ring pumped', 'for (i = 0; i < tl->config.rings; ++i) {\n        struct tl_ring *r = &tl->rings[i];\n        while', 'for (i = 0; i < 1u; ++i) {\n        struct tl_ring *r = &tl->rings[i];\n        while'),
    ('submit refused after fault', 'if (tl->faulted) return SGPU_TL_STOPPED;', ''),
    ('sequence increases', 'if (sequence <= tl->last_sequence) return SGPU_TL_ARGUMENT;', ''),
    ('equal sequence refused', 'if (sequence <= tl->last_sequence)', 'if (sequence < tl->last_sequence)'),
    ('waits precede job', 'for (i = 0; i < wait_count; ++i) if (waits[i] >= sequence) return SGPU_TL_ARGUMENT;', ''),
    ('wait on self refused', 'if (waits[i] >= sequence)', 'if (waits[i] > sequence)'),
    ('waiting depth enforced', 'if (r->waiting_count >= tl->config.depth) return SGPU_TL_FULL;', ''),
    ('waiting depth boundary', 'if (r->waiting_count >= tl->config.depth)', 'if (r->waiting_count > tl->config.depth)'),
    ('full job table refused', 'if (slot == NO_JOB) return SGPU_TL_FULL;', ''),
    ('absent wait dropped', 'if (target != NO_JOB) {', 'if (1) {'),
    ('wait sequence stored', 'j->waits[kept] = waits[i];', ''),
    ('wait slot stored', 'j->wait_slots[kept] = (uint16_t)target;', ''),
    ('wait kept', '++kept;', ''),
    ('IBs copied', 'for (i = 0; i < count; ++i) j->ibs[i] = ibs[i];', ''),
    ('all IBs copied', 'for (i = 0; i < count; ++i) j->ibs[i]', 'for (i = 0; i < 1u; ++i) j->ibs[i]'),
    ('sequence stored', 'j->sequence = sequence;', ''),
    ('context stored', 'j->hw_context = hw_context;', ''),
    ('count stored', 'j->count = count;', ''),
    ('wait count stored', 'j->wait_count = kept;', ''),
    ('job marked active', 'j->state = JOB_ACTIVE;', ''),
    ('waiting push wraps', 'r->waiting[(r->waiting_head + r->waiting_count) % SGPU_TL_MAX_DEPTH] = (uint16_t)slot;', 'r->waiting[r->waiting_head + r->waiting_count] = (uint16_t)slot;'),
    ('waiting count grows', '++r->waiting_count;', ''),
    ('new head started', 'if (r->waiting_count == 1u && start_head', 'if (r->waiting_count == 0u && start_head'),
    ('own refusal leaves queue', '(void)pop_waiting(r);\n        j->state = JOB_FREE;', 'j->state = JOB_FREE;'),
    ('own refusal frees slot', '(void)pop_waiting(r);\n        j->state = JOB_FREE;', '(void)pop_waiting(r);'),
    ('last sequence updated', 'tl->last_sequence = sequence;', ''),
    ('submit ring bounded', 'if (ring >= tl->config.rings || !ibs || !count || count > SGPU_MAX_IBS)', 'if (!ibs || !count || count > SGPU_MAX_IBS)'),
    ('submit IBs present', 'if (ring >= tl->config.rings || !ibs || !count || count > SGPU_MAX_IBS)', 'if (ring >= tl->config.rings || !count || count > SGPU_MAX_IBS)'),
    ('submit IB count nonzero', 'if (ring >= tl->config.rings || !ibs || !count || count > SGPU_MAX_IBS)', 'if (ring >= tl->config.rings || !ibs || count > SGPU_MAX_IBS)'),
    ('submit IB count bounded', 'if (ring >= tl->config.rings || !ibs || !count || count > SGPU_MAX_IBS)', 'if (ring >= tl->config.rings || !ibs || !count)'),
    ('submit wait count bounded', 'if (wait_count > SGPU_MAX_DEPS || (wait_count && !waits))', 'if (wait_count && !waits)'),
    ('submit waits present', 'if (wait_count > SGPU_MAX_DEPS || (wait_count && !waits))', 'if (wait_count > SGPU_MAX_DEPS)'),
    ('one reporter at a time', 'if (tl->reporting) {', 'if (0) {'),
    ('reporter flag set', 'tl->reporting = 1;', ''),
    ('reporter flag cleared', 'tl->reporting = 0;', ''),
    ('report index wraps', 'tl->report_head = (tl->report_head + 1u) % SGPU_TL_MAX_JOBS;', 'tl->report_head = tl->report_head + 1u;'),
    ('report count falls', '--tl->report_count;', ''),
    ('reported slot freed', 'j->state = JOB_FREE;\n            tl->hw.unlock', 'tl->hw.unlock'),
    ('unknown retirement counted', 'if (result) ++tl->stats.unknown_retirements;', ''),
    ('retirements precede the fault', 'if (tl->report_count) {', 'if (tl->report_count && !tl->fault_pending) {'),
    ('fault precedes quiescence', '} else if (tl->fault_pending) {', '} else if (tl->fault_pending && !tl->quiesce_pending) {'),
    ('fault delivered once', 'tl->fault_pending = 0;', ''),
    ('quiescence delivered once', 'tl->quiesce_pending = 0;', ''),
    ('quiescence rejection counted', 'if (result) ++tl->stats.quiesce_rejected;', ''),
    ('observe ring bounded', 'int status = SGPU_TL_OK;\n    if (ring >= tl->config.rings) return SGPU_TL_ARGUMENT;', 'int status = SGPU_TL_OK;'),
    ('counter ignored after fault', 'if (tl->faulted) {\n        ++tl->stats.ignored_after_fault;', 'if (0) {\n        ++tl->stats.ignored_after_fault;'),
    ('ignored observation counted', '++tl->stats.ignored_after_fault;', ''),
    ('upper counter bits refused', 'if ((counter & ~tl->mask) || distance > r->running_count) {', 'if (distance > r->running_count) {'),
    ('distance bounded by running', 'if ((counter & ~tl->mask) || distance > r->running_count) {', 'if (counter & ~tl->mask) {'),
    ('distance boundary', 'distance > r->running_count) {', 'distance >= r->running_count) {'),
    ('distance masked', '(counter - r->last_counter) & tl->mask', 'counter - r->last_counter'),
    ('bad counter counted', '++tl->stats.bad_counters;', ''),
    ('bad counter faults', 'mark_faulted(tl, SGPU_BE_REASON_FAULT);\n            status = SGPU_TL_BAD_COUNTER;', 'status = SGPU_TL_BAD_COUNTER;'),
    ('spurious observation counted', '++tl->stats.spurious_observations;', ''),
    ('finished job marked done', 'tl->jobs[slot].state = JOB_DONE;', ''),
    ('report push wraps', 'tl->report[(tl->report_head + tl->report_count) % SGPU_TL_MAX_JOBS] = (uint16_t)slot;', 'tl->report[tl->report_head + tl->report_count] = (uint16_t)slot;'),
    ('report count grows', '++tl->report_count;', ''),
    ('completed counted', '++tl->stats.completed;', ''),
    ('last counter updated', 'r->last_counter = counter;', ''),
    ('head clock restarts on progress', 'r->head_since = tl->hw.now_ns(tl->hw_context);\n            pump(tl);', 'pump(tl);'),
    ('waiters started after progress', 'tl->hw.now_ns(tl->hw_context);\n            pump(tl);', 'tl->hw.now_ns(tl->hw_context);'),
    ('tick idle after fault', 'if (tl->faulted) {\n        status = SGPU_TL_STOPPED;', 'if (0) {\n        status = SGPU_TL_STOPPED;'),
    ('idle ring has no deadline', 'if (r->running_count && now > r->head_since', 'if (now > r->head_since'),
    ('clock regression ignored', 'r->running_count && now > r->head_since && now - r->head_since', 'r->running_count && now - r->head_since'),
    ('timeout boundary', 'now - r->head_since >= tl->config.job_timeout_ns', 'now - r->head_since > tl->config.job_timeout_ns'),
    ('timeout counted', '++tl->stats.timeouts;', ''),
    ('timeout faults', 'mark_faulted(tl, SGPU_BE_REASON_FAULT);\n                status = SGPU_TL_TIMED_OUT;', 'status = SGPU_TL_TIMED_OUT;'),
    ('every ring has a deadline', 'for (i = 0; i < tl->config.rings; ++i) {\n            const struct tl_ring', 'for (i = 0; i < 1u; ++i) {\n            const struct tl_ring'),
    ('zero fault reason mapped', 'reason ? reason : (uint32_t)SGPU_BE_REASON_FAULT', 'reason'),
    ('quiescence needs a fault', 'if (!tl->faulted) {\n        status = SGPU_TL_NOT_FAULTED;', 'if (0) {\n        status = SGPU_TL_NOT_FAULTED;'),
    ('quiescence delivered at most once', '} else if (!tl->quiesced) {', '} else {'),
    ('quiesced latched', 'tl->quiesced = 1;', ''),
    ('quiescence reported', 'tl->quiesce_pending = 1;', ''),
]

EQUIVALENT = [
    ('active-state filter in find_active', 'A wait on a finished job is kept or dropped with the same effect, because job_blocked rechecks the state.'),
    ('new-head condition on the submit start', 'A head that is not the new job cannot be startable during submit: nothing the submit does changes its blocker.'),
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    parser.add_argument('--host-clang', type=Path, default=Path('/home/egor/.local/bin/clang'))
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', args.run):
        raise ValueError('Invalid run name')
    out = ROOT/'artifacts/gpu-queue'/args.run
    out.mkdir(parents=True, exist_ok=False)
    report = dict(schema_version=1, kind='host-test', origin='local-host', outcome='inconclusive', recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                  commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=SOURCE, text=True).strip(), commands=[], mutations=[], device_io=False, gpu_executed=False, apple_sdk_used=False, sha256={})

    def run(argv, timeout=120):
        argv = [str(a) for a in argv]
        try:
            done = subprocess.run(argv, cwd=out, capture_output=True, text=True, timeout=timeout)
            code, stdout, stderr = done.returncode, done.stdout, done.stderr
        except subprocess.TimeoutExpired as error:
            code, stdout, stderr = 'timeout', error.stdout or '', error.stderr or ''
        report['commands'].append(dict(argv=argv, exit_code=code, stdout=stdout[-2000:], stderr=stderr[-2000:]))
        if code != 0:
            raise RuntimeError(f'{argv[0]}: {code}: {stderr or stdout}')
        return stdout

    try:
        snapshot = out/'source'
        snapshot.mkdir()
        for source in SOURCES:
            shutil.copyfile(source, snapshot/source.name)
            report['sha256'][source.name] = sha(source)
        others = [snapshot/'sgpu_backend.c', snapshot/'sgpu_abi.c', snapshot/'test_timeline.c']
        files = [snapshot/'sgpu_timeline.c', *others]
        base = [args.host_clang, '-std=c11', *WARN, '-g', '-O1', '-fno-omit-frame-pointer']
        run([*base, '-fsanitize=address,undefined', '-fno-sanitize-recover=all', *files, '-I', snapshot, '-lpthread', '-o', out/'test-asan'])
        report['tests'] = json.loads(run([out/'test-asan']))
        run([*base, '-fsanitize=thread', *files, '-I', snapshot, '-lpthread', '-o', out/'test-tsan'])
        report['tests_tsan'] = json.loads(run([out/'test-tsan'], timeout=300))
        resource = run([args.host_clang, '-print-resource-dir']).strip()
        run([args.host_clang, '--target=arm64-apple-macos13', '-ffreestanding', '-fno-builtin', '-fno-stack-protector', '-nostdinc', '-isystem', Path(resource)/'include', '-std=c11', *WARN, '-O2', '-I', snapshot, '-c', snapshot/'sgpu_timeline.c', '-o', out/'timeline-arm64.o'])
        report['arm64_undefined_symbols'] = run([NM, '-u', out/'timeline-arm64.o']).split()
        report['arm64_object_sha256'] = sha(out/'timeline-arm64.o')
        report['arm64_note'] = 'Host clang, freestanding, not the kernel flags. Not an XNU build.'
        if report['arm64_undefined_symbols']:
            raise RuntimeError('Unexpected undefined symbols in the ARM64 object')
        original = (snapshot/'sgpu_timeline.c').read_text()
        survivors = []
        for rule, before, after in MUTATIONS:
            if original.count(before) != 1:
                raise ValueError(f'Mutation text must occur once ({original.count(before)}): {rule}')
            work = out/'mutant'
            shutil.rmtree(work, ignore_errors=True)
            work.mkdir()
            (work/'sgpu_timeline.c').write_text(original.replace(before, after))
            result = dict(rule=rule)
            built = subprocess.run([str(args.host_clang), '-std=c11', '-g', '-O1', '-w', '-fsanitize=address,undefined', '-fno-sanitize-recover=all', str(work/'sgpu_timeline.c'), *[str(p) for p in others], '-I', str(snapshot), '-lpthread', '-o', str(work/'test')], capture_output=True, text=True, timeout=120)
            if built.returncode:
                result.update(state='build-error', detail=built.stderr[-400:])
                survivors.append(rule)
            else:
                try:
                    ran = subprocess.run([str(work/'test')], capture_output=True, text=True, timeout=30)
                    result.update(state='killed' if ran.returncode else 'survived', exit_code=ran.returncode, detail=(ran.stderr or ran.stdout)[:200])
                except subprocess.TimeoutExpired:
                    result.update(state='killed', exit_code='timeout', detail='test exceeded 30s')
                if result['state'] == 'survived':
                    survivors.append(rule)
            report['mutations'].append(result)
        shutil.rmtree(out/'mutant', ignore_errors=True)
        report['mutation_count'] = len(MUTATIONS)
        report['equivalent_mutants_not_run'] = [dict(rule=r, reason=w) for r, w in EQUIVALENT]
        report['mutation_survivors'] = survivors
        report['outcome'] = 'fail' if survivors else 'pass'
    except Exception as error:
        report['outcome'] = 'fail'
        report['error'] = repr(error)
    (out/'evidence.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(outcome=report['outcome'], tests=report.get('tests'), tests_tsan=report.get('tests_tsan'), mutations=len(report['mutations']), survivors=report.get('mutation_survivors'), arm64_undefined=report.get('arm64_undefined_symbols'), error=report.get('error')), indent=1))
    return 0 if report['outcome'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
