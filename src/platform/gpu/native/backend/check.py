#!/usr/bin/env python3
"""Host checks for the SGPU backend core. No SDK, device, QEMU or GPU.

Runs the dispatcher tests under ASan/UBSan and TSan, then applies single-line
mutations to the core and requires the tests to catch each one. A surviving
mutant fails the check, because it means a stated rule has no test behind it.
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
ABI = SOURCE.parent.parent / 'abi'
SOURCES = [ABI/'sgpu_abi.h', ABI/'sgpu_abi.c', SOURCE/'sgpu_backend.h', SOURCE/'sgpu_backend.c', SOURCE/'test_backend.c', SOURCE/'check.py']
WARN = ['-Wall', '-Wextra', '-Werror', '-Wpedantic']

# (rule, original text, mutated text). Each must occur exactly once.
MUTATIONS = [
    ('unverified profile refused', '} else if (be->config.profile_verified) {', '} else if (1) {'),
    ('BO owner checked', 'b->generation == generation && b->client == client) ? b : 0', 'b->generation == generation) ? b : 0'),
    ('BO generation checked', 'return (b->live && !b->zombie && b->generation == generation && b->client == client) ? b : 0', 'return (b->live && !b->zombie && b->client == client) ? b : 0'),
    ('fence owner checked', 'return (f->live && f->generation == generation && f->client == client) ? f : 0', 'return (f->live && f->generation == generation) ? f : 0'),
    ('handle type checked', "if ((uint32_t)(handle >> 56) != type || low == 0 || low > limit) return 0;", "if (low == 0 || low > limit) return 0;"),
    ('handle slot bounded', "if ((uint32_t)(handle >> 56) != type || low == 0 || low > limit) return 0;", "if ((uint32_t)(handle >> 56) != type || low == 0) return 0;"),
    ('generation advances on release', 'if (*generation < GENERATION_MAX) ++*generation;', '(void)GENERATION_MAX;'),
    ('client generation checked', 'if (!be->clients[slot].live || be->clients[slot].generation != (id >> 16)) return 0;', 'if (!be->clients[slot].live) return 0;'),
    ('client slot retires instead of wrapping', 'slot_free(be->clients[slot].live, be->clients[slot].generation) && be->clients[slot].generation < 0xFFFFu', 'slot_free(be->clients[slot].live, be->clients[slot].generation)'),
    ('budget enforced', 'if (backing > be->config.budget_bytes - be->budget_used) return SGPU_LIMIT;', ''),
    ('max allocation enforced', 'if (size > be->config.max_alloc_bytes) return SGPU_LIMIT;', ''),
    ('backing rounded to CPU page', '!round_up(gpu_bytes, be->config.cpu_vm_page, &backing)', '!round_up(gpu_bytes, SGPU_GPU_PAGE, &backing)'),
    ('alignment raised to CPU page', 'if (alignment < be->config.cpu_vm_page) alignment = be->config.cpu_vm_page;', ''),
    ('failed backing not charged', 'if (be->ops.backing_alloc(be->hw, backing, alignment, &token)) return SGPU_BACKEND_ERROR;', 'if (be->ops.backing_alloc(be->hw, backing, alignment, &token)) { be->budget_used += backing; return SGPU_BACKEND_ERROR; }'),
    ('budget released on free', 'be->budget_used -= b->backing;', ''),
    ('free blocked while in flight', 'if (b->pending || b->cpu_maps || b->gpu_maps) return SGPU_LIMIT;', 'if (b->cpu_maps || b->gpu_maps) return SGPU_LIMIT;'),
    ('free blocked by GPU mapping', 'if (b->pending || b->cpu_maps || b->gpu_maps) return SGPU_LIMIT;', 'if (b->pending || b->cpu_maps) return SGPU_LIMIT;'),
    ('free blocked by CPU mapping', 'if (b->pending || b->cpu_maps || b->gpu_maps) return SGPU_LIMIT;', 'if (b->pending || b->gpu_maps) return SGPU_LIMIT;'),
    ('context destroy blocked when referenced', 'if (c->pending || c->gpu_maps) return SGPU_LIMIT;', ''),
    ('CPU map range bounded', '((offset | bytes) & (page - 1u)) || !bytes || !range_within(offset, bytes, b->backing)) return SGPU_BAD_FIELD;', '((offset | bytes) & (page - 1u)) || !bytes) return SGPU_BAD_FIELD;'),
    ('CPU map granule enforced', '((offset | bytes) & (page - 1u)) || !bytes || !range_within(offset, bytes, b->backing)) return SGPU_BAD_FIELD;', '!bytes || !range_within(offset, bytes, b->backing)) return SGPU_BAD_FIELD;'),
    ('CPU map access bounded by BO', 'if (!b || (access & ~b->access) || (access & SGPU_EXEC) || ', 'if (!b || (access & SGPU_EXEC) || '),
    ('CPU map refused in flight', 'if (b->pending || b->cpu_maps) return SGPU_LIMIT;', 'if (b->cpu_maps) return SGPU_LIMIT;'),
    ('one CPU mapping per BO', 'if (b->pending || b->cpu_maps) return SGPU_LIMIT;', 'if (b->pending) return SGPU_LIMIT;'),
    ('CPU write refused while GPU dirty', 'if ((access & SGPU_WRITE) && b->gpu_dirty) return SGPU_BAD_FIELD;', ''),
    ('CPU write marks dirty', 'if (access & SGPU_WRITE) b->cpu_dirty = 1;', ''),
    ('CPU unmap refused in flight', "if (be->bos[m->bo].pending) return SGPU_LIMIT;\n    be->ops.cpu_unmap", "be->ops.cpu_unmap"),
    ('VA window lower bound', 'if (address < be->config.va_start || end > window_end || ', 'if (end > window_end || '),
    ('VA window upper bound', 'if (address < be->config.va_start || end > window_end || ', 'if (address < be->config.va_start || '),
    ('GPU map inside BO', '|| !range_within(offset, bytes, b->bytes)) return SGPU_BAD_FIELD;\n    if (b->pending) return SGPU_LIMIT;\n    for (i = 0; i < SGPU_BE_MAX_GPU_MAPS; ++i) {', ') return SGPU_BAD_FIELD;\n    if (b->pending) return SGPU_LIMIT;\n    for (i = 0; i < SGPU_BE_MAX_GPU_MAPS; ++i) {'),
    ('GPU map access bounded by BO', 'if (!c || !b || (access & ~b->access) || !bytes) return SGPU_BAD_FIELD;', 'if (!c || !b || !bytes) return SGPU_BAD_FIELD;'),
    ('GPU map refused in flight', 'SGPU_BAD_FIELD;\n    if (b->pending) return SGPU_LIMIT;\n    for (i = 0; i < SGPU_BE_MAX_GPU_MAPS; ++i) {', 'SGPU_BAD_FIELD;\n    for (i = 0; i < SGPU_BE_MAX_GPU_MAPS; ++i) {'),
    ('VA overlap rejected', 'if (be->contexts[other->context].client == client && address < other->va + other->bytes && other->va < end) return SGPU_BAD_FIELD;', ''),
    ('VA overlap is per client', 'if (be->contexts[other->context].client == client && address <', 'if (other->context == (uint32_t)(c - be->contexts) && address <'),
    ('TLB failure unwinds PTEs', 'if (be->ops.vm_unmap(be->hw, c->hw_context, address, bytes)) {\n            /* The PTE', 'if (0) {\n            /* The PTE'),
    ('failed unwind quarantines', 'm->access = access; m->va = address; m->offset = offset; m->bytes = bytes;\n            ++b->gpu_maps; ++c->gpu_maps;\n            be->faulted = 1;', 'm->access = access; m->va = address; m->offset = offset; m->bytes = bytes;\n            ++b->gpu_maps; ++c->gpu_maps;'),
    ('failed unwind retains mapping', 'm->access = access; m->va = address; m->offset = offset; m->bytes = bytes;\n            ++b->gpu_maps; ++c->gpu_maps;\n            be->faulted = 1;', 'be->faulted = 1;'),
    ('GPU unmap refused in flight', 'if (be->bos[m->bo].pending) return SGPU_LIMIT;\n            return remove_gpu_map', 'return remove_gpu_map'),
    ('failed unmap retains mapping', 'if (be->ops.vm_unmap(be->hw, c->hw_context, m->va, m->bytes) || be->ops.tlb_flush(be->hw, c->hw_context, m->va, m->bytes)) {\n        be->faulted = 1;\n        be->fault_reason = SGPU_BE_REASON_FAULT;\n        return 0;\n    }', '(void)be->ops.vm_unmap(be->hw, c->hw_context, m->va, m->bytes);'),
    ('failed unmap quarantines', 'm->bytes)) {\n        be->faulted = 1;\n        be->fault_reason = SGPU_BE_REASON_FAULT;\n        return 0;', 'm->bytes)) {\n        return 0;'),
    ('TLB flushed on unmap', 'be->ops.vm_unmap(be->hw, c->hw_context, m->va, m->bytes) || be->ops.tlb_flush(be->hw, c->hw_context, m->va, m->bytes)', 'be->ops.vm_unmap(be->hw, c->hw_context, m->va, m->bytes)'),
    ('cache needs idle CPU mapping', 'if (b->pending || !b->cpu_maps) return SGPU_LIMIT;', 'if (b->pending) return SGPU_LIMIT;'),
    ('cache refused in flight', 'if (b->pending || !b->cpu_maps) return SGPU_LIMIT;', 'if (!b->cpu_maps) return SGPU_LIMIT;'),
    ('cache conflict refused', 'if (direction == SGPU_TO_GPU ? b->gpu_dirty : b->cpu_dirty) return SGPU_BAD_FIELD;', ''),
    ('cache range bounded', 'if (!b || !bytes || !range_within(offset, bytes, b->bytes)) return SGPU_BAD_FIELD;\n    if (b->pending || !b->cpu_maps)', 'if (!b || !bytes) return SGPU_BAD_FIELD;\n    if (b->pending || !b->cpu_maps)'),
    ('failed sync leaves dirty state', 'if (be->ops.cache_sync(be->hw, b->token, offset, bytes, direction)) return SGPU_BACKEND_ERROR;', 'if (be->ops.cache_sync(be->hw, b->token, offset, bytes, direction)) { b->cpu_dirty = 0; return SGPU_BACKEND_ERROR; }'),
    ('TO_GPU clears CPU dirty', 'if (direction == SGPU_TO_GPU) b->cpu_dirty = 0;', 'if (direction == SGPU_TO_GPU) { }'),
    ('TO_CPU clears GPU dirty', 'else b->gpu_dirty = 0;', 'else { }'),
    ('submit refuses CPU dirty', 'if (!b || (access & ~b->access) || b->cpu_dirty) return SGPU_BAD_FIELD;', 'if (!b || (access & ~b->access)) return SGPU_BAD_FIELD;'),
    ('submit needs mapped BO', 'if (!mapped) return SGPU_BAD_FIELD;\n', ''),
    ('use access bounded by mapping', 'm->bo == (uint32_t)(b - be->bos) && (m->access & access) == access;', 'm->bo == (uint32_t)(b - be->bos);'),
    ('mapping checked per context', 'mapped = m->live && m->context == context_slot && ', 'mapped = m->live && '),
    ('IB needs covering map', 'if (!map) return SGPU_BAD_FIELD;', 'if (!map) map = &be->gpu_maps[0];'),
    ('IB range covered, start', 'offset >= m->offset\n            && bytes <= m->bytes', '1\n            && bytes <= m->bytes'),
    ('IB range covered, end', '&& bytes <= m->bytes && offset - m->offset <= m->bytes - bytes) return m;', ') return m;'),
    ('IB covering map per context', 'if (m->live && m->context == context && m->bo == bo && (m->access', 'if (m->live && m->bo == bo && (m->access'),
    ('IB address translated', 'hw_ibs[i].va = map->va + (offset - map->offset);', 'hw_ibs[i].va = map->va + offset;'),
    ('dependency ownership checked', 'if (!d || d->state == FENCE_ERROR) return SGPU_BAD_FIELD;', 'if (!d) continue;'),
    ('errored dependency refused', 'if (!d || d->state == FENCE_ERROR) return SGPU_BAD_FIELD;', 'if (!d) return SGPU_BAD_FIELD;'),
    ('hazard: last writer', 'if (b->writer && be->fences[b->writer - 1].state == FENCE_PENDING && !dependency_covers(dep_slots, dep_count, b->writer)) return SGPU_BAD_FIELD;', ''),
    ('hazard: readers before a write', 'if (!dependency_covers(dep_slots, dep_count, b->readers[reader])) return SGPU_BAD_FIELD;', '(void)reader;'),
    ('reader table bounded', '} else if (b->reader_count == SGPU_BE_MAX_READERS) {\n            return SGPU_LIMIT;\n        }', '}'),
    ('fence table limit', 'if (!choose_fence_slot(be, &slot)) return SGPU_LIMIT;', 'if (!choose_fence_slot(be, &slot)) slot = 0;'),
    ('pending fences not evicted', 'if (f->live && f->state != FENCE_PENDING && !f->waiters && f->generation', 'if (f->live && !f->waiters && f->generation'),
    ('oldest retired fence evicted first', '&& (best == SGPU_BE_MAX_FENCES || f->sequence < be->fences[best].sequence)) best = i;', ') best = i;'),
    ('failed submit burns no sequence', '    sequence = be->next_sequence + 1;\n    if (be->ops.submit', '    sequence = ++be->next_sequence;\n    if (be->ops.submit'),
    ('failed submit evicts nothing', 'if (!choose_fence_slot(be, &slot)) return SGPU_LIMIT;', 'if (!choose_fence_slot(be, &slot)) return SGPU_LIMIT;\n    if (be->fences[slot].live) release_slot(&be->fences[slot].live, &be->fences[slot].generation);'),
    ('submit takes references', '        ++b->pending;\n', ''),
    ('submit counts context work', '    ++c->pending;\n', ''),
    ('timeout does not retire', 'if (now >= deadline) { status = SGPU_TIMEOUT; break; }', 'if (now >= deadline) { retire_fence(be, f, 0); status = SGPU_TIMEOUT; break; }'),
    ('stop wakes waiters', 'case SGPU_STOP: owner->stopped = 1; be->ops.wake(be->hw); status = SGPU_OK; break;', 'case SGPU_STOP: owner->stopped = 1; status = SGPU_OK; break;'),
    ('wait stops for a stopped client', 'if (!owner || owner->stopped) { status = SGPU_STOPPED; break; }', '(void)owner;'),
    ('retire wakes waiters', 'reap_zombies(be);\n    be->ops.wake(be->hw);\n}', 'reap_zombies(be);\n}'),
    ('close wakes waiters', 'owner->generation = (owner->generation + 1) & 0xFFFFu;\n    be->ops.wake(be->hw);', 'owner->generation = (owner->generation + 1) & 0xFFFFu;'),
    ('retire needs a pending fence', 'if (f->live && f->state == FENCE_PENDING && f->sequence == sequence) {\n            retire_fence', 'if (f->live && f->sequence == sequence) {\n            retire_fence'),
    ('retire matches sequence', 'if (f->live && f->state == FENCE_PENDING && f->sequence == sequence) {\n            retire_fence', 'if (f->live && f->state == FENCE_PENDING) {\n            retire_fence'),
    ('retire drops references', '        --b->pending;\n', ''),
    ('GPU write marks dirty', 'if (f->uses[i].access & SGPU_WRITE) b->gpu_dirty = 1;', ''),
    ('error reason reported', 'f->state = reason ? FENCE_ERROR : FENCE_RETIRED;', 'f->state = FENCE_RETIRED;'),
    ('stopped client refused', 'return (c->stopped || be->faulted) ? SGPU_STOPPED : SGPU_OK;', 'return be->faulted ? SGPU_STOPPED : SGPU_OK;'),
    ('faulted device refused', 'return (c->stopped || be->faulted) ? SGPU_STOPPED : SGPU_OK;', 'return c->stopped ? SGPU_STOPPED : SGPU_OK;'),
    ('no client opens while faulted', 'if (be->faulted) { be->ops.unlock(be->hw); return SGPU_STOPPED; }', ''),
    ('quarantine blocks reaping', 'if (!be->zombies || (be->faulted && !be->quiesced)) return;', 'if (!be->zombies) return;'),
    ('quiesce needs quarantine', 'accepted = be->faulted && !be->quiesced;', 'accepted = !be->quiesced;'),
    ('quiesce only once', 'accepted = be->faulted && !be->quiesced;', 'accepted = be->faulted;'),
    ('quiesce retires pending work', 'if (f->live && f->state == FENCE_PENDING) retire_fence(be, f, SGPU_BE_REASON_QUIESCED);', ''),
    ('quiesce reaps zombies', '        reap_zombies(be);\n    }\n    be->ops.unlock(be->hw);\n    return accepted ? 0 : -1;', '    }\n    be->ops.unlock(be->hw);\n    return accepted ? 0 : -1;'),
    ('close keeps busy BO', 'if (b->live && b->zombie && !b->pending && !b->gpu_maps && !b->cpu_maps) destroy_bo(be, b);', 'if (b->live && b->zombie) destroy_bo(be, b);'),
    ('close keeps busy context', 'if (c->live && c->zombie && !c->pending && !c->gpu_maps) destroy_context(be, c);', 'if (c->live && c->zombie) destroy_context(be, c);'),
    ('close keeps busy mappings', 'if (m->live && be->bos[m->bo].zombie && !be->bos[m->bo].pending) (void)remove_gpu_map(be, m);', 'if (m->live && be->bos[m->bo].zombie) (void)remove_gpu_map(be, m);'),
    ('close unmaps CPU views', 'be->ops.cpu_unmap(be->hw, be->bos[m->bo].token, m->offset, m->bytes);\n            --be->bos[m->bo].cpu_maps;\n            release_slot', '--be->bos[m->bo].cpu_maps;\n            release_slot'),
    ('init rejects max_alloc over budget', '|| config->max_alloc_bytes > config->budget_bytes ', ''),
    ('init rejects zero VA', '|| !config->va_start || !config->va_bytes', '|| !config->va_bytes'),
    ('init rejects unverified values', '} else if (config->budget_bytes || config->max_alloc_bytes', '} else if (0 && config->max_alloc_bytes'),
    ('query hides values when unverified', 'if (be->config.profile_verified) {\n        sgpu_put64(r->payload + 8', 'if (1) {\n        sgpu_put64(r->payload + 8'),
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
    out = ROOT/'artifacts/gpu-backend'/args.run
    out.mkdir(parents=True, exist_ok=False)
    report = dict(schema_version=1, kind='host-test', origin='local-host', outcome='inconclusive',
                  recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                  commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=SOURCE, text=True).strip(),
                  commands=[], mutations=[], device_io=False, gpu_executed=False, apple_sdk_used=False, sha256={})

    def run(argv, timeout=60, check=True):
        argv = [str(a) for a in argv]
        try:
            result = subprocess.run(argv, cwd=out, capture_output=True, text=True, timeout=timeout)
            code, stdout, stderr = result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired as error:
            code, stdout, stderr = 'timeout', error.stdout or '', error.stderr or ''
        report['commands'].append(dict(argv=argv, exit_code=code, stdout=stdout[-2000:], stderr=stderr[-2000:]))
        if check and code != 0:
            raise RuntimeError(f'{argv[0]}: {code}: {stderr or stdout}')
        return code, stdout

    try:
        snapshot = out/'source'
        snapshot.mkdir()
        for source in SOURCES:
            shutil.copyfile(source, snapshot/source.name)
            report['sha256'][source.name] = sha(source)
        files = [snapshot/'sgpu_backend.c', snapshot/'sgpu_abi.c', snapshot/'test_backend.c']
        run(['cc', '-std=c11', *WARN, '-O2', '-c', snapshot/'sgpu_backend.c', '-I', snapshot, '-o', out/'core-gcc.o'])
        run(['nm', '-u', out/'core-gcc.o'])
        report['core_undefined_host'] = report['commands'][-1]['stdout'].split()

        def build(flags, name, sources=files):
            run([args.host_clang, '-std=c11', *WARN, '-g', '-O1', '-fno-omit-frame-pointer', *flags, *sources, '-I', snapshot, '-lpthread', '-o', out/name])

        build(['-fsanitize=address,undefined', '-fno-sanitize-recover=all'], 'test-asan')
        _, stdout = run([out/'test-asan'], timeout=120)
        report['tests'] = json.loads(stdout)
        build(['-fsanitize=thread'], 'test-tsan')
        _, stdout = run([out/'test-tsan'], timeout=300)
        report['tests_tsan'] = json.loads(stdout)

        original = (snapshot/'sgpu_backend.c').read_text()
        survivors = []
        for rule, before, after in MUTATIONS:
            if original.count(before) != 1:
                raise ValueError(f'Mutation text must occur once ({original.count(before)}): {rule}')
            work = out/'mutant'
            shutil.rmtree(work, ignore_errors=True)
            work.mkdir()
            source = work/'sgpu_backend.c'
            source.write_text(original.replace(before, after))
            result = {'rule': rule}
            built = subprocess.run([str(args.host_clang), '-std=c11', '-g', '-O1', '-w', '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                                    str(source), str(snapshot/'sgpu_abi.c'), str(snapshot/'test_backend.c'), '-I', str(snapshot), '-lpthread', '-o', str(work/'test')],
                                   capture_output=True, text=True, timeout=60)
            if built.returncode:
                result.update(state='build-error', detail=built.stderr[-400:])
                survivors.append(rule)
            else:
                try:
                    executed = subprocess.run([str(work/'test')], capture_output=True, text=True, timeout=30)
                    result.update(state='killed' if executed.returncode else 'survived', exit_code=executed.returncode, detail=(executed.stderr or executed.stdout)[:200])
                except subprocess.TimeoutExpired:
                    result.update(state='killed', exit_code='timeout', detail='test exceeded 30s')
                if result['state'] == 'survived':
                    survivors.append(rule)
            report['mutations'].append(result)
        shutil.rmtree(out/'mutant', ignore_errors=True)
        report['mutation_count'] = len(MUTATIONS)
        report['mutation_survivors'] = survivors
        report['outcome'] = 'fail' if survivors else 'pass'
    except Exception as error:
        report['outcome'] = 'fail'
        report['error'] = repr(error)
    (out/'evidence.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'outcome': report['outcome'], 'tests': report.get('tests'), 'tests_tsan': report.get('tests_tsan'), 'mutations': len(report['mutations']), 'survivors': report.get('mutation_survivors'), 'error': report.get('error')}, indent=1))
    return 0 if report['outcome'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
