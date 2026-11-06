#!/usr/bin/env python3
"""Independently reconstruct the exact two-file diff; no producer checker run."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import time

WT = Path(__file__).resolve().parents[4]
MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
AUTHOR = MAIN / 'worktrees/str-034-e1s-kernel-log-20261106'
CORE = WT / 'docs/integration/platform/native93-libkern-review/read-products.py'
assert hashlib.sha256(CORE.read_bytes()).hexdigest() == '9d7a7e31855d3f1db649685f8054a84fe6972182bf8b521599d59152bb4f381e'
spec = importlib.util.spec_from_file_location('cn_bounded_source_hashes', CORE)
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)
req, data, pin, load = core.req, core.data, core.pin, core.load

def main():
    out = WT / 'artifacts/e1s-kernel-log-str034-review/source-001'
    out.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    overlay = load(AUTHOR / 'fixtures/public/e1s-kernel-log/source-overlay.json', '9cda8f05b5a1173a9f49cfdd789c347036f91451ca63abe32a08c82f4be02fda')
    inputs = load(overlay['input_spec']['path'], overlay['input_spec']['sha256'])
    req(inputs['patch_sha256'] == overlay['patch']['sha256'] == 'c1f02bdd5f817fd5f5924f469b6333522f775cb84808412dff82e0c82fee6911', 'Exact narrow patch')
    patch = data(overlay['patch']['path'], overlay['patch']['sha256']).decode().splitlines(keepends=True)
    for name, digest in inputs['inputs'].items():
        pin(name, digest)
    source = Path(inputs['source_root'])
    old, after, products = {}, {}, {}
    i = 0
    # This parser copies only context explicitly present in this frozen unified
    # diff and rejects offsets/context/count mismatches. It never calls git apply.
    while i < len(patch):
        req(patch[i].startswith('--- a/'), 'Exact old-file patch header')
        name = patch[i][6:].strip()
        i += 1
        req(patch[i] == '+++ b/' + name + '\n' and name in inputs['files'] and name not in after, 'Exact allowed new-file patch header')
        i += 1
        lines = data(source / name, inputs['files'][name]['before_sha256']).decode().splitlines(keepends=True)
        old[name] = ''.join(lines)
        result, cursor = [], 0
        while i < len(patch) and patch[i].startswith('@@'):
            match = re.fullmatch(r'@@ -(\d+),(\d+) \+(\d+),(\d+) @@\n', patch[i])
            req(match is not None, 'Exact fixed hunk grammar')
            a, count_old, b, count_new = map(int, match.groups())
            req(a - 1 >= cursor, 'Ordered nonoverlapping original hunks')
            result += lines[cursor:a - 1]
            cursor = a - 1
            req(len(result) == b - 1, 'Exact postimage hunk position')
            i += 1
            consumed, produced = 0, 0
            while i < len(patch) and not patch[i].startswith(('@@', '--- a/')):
                tag, content = patch[i][0], patch[i][1:]
                req(tag in ' +-', 'Only ordinary unified-diff lines')
                if tag != '+':
                    req(cursor < len(lines) and lines[cursor] == content, 'Exact original context/deletion bytes')
                    cursor += 1
                    consumed += 1
                if tag != '-':
                    result.append(content)
                    produced += 1
                i += 1
            req((consumed, produced) == (count_old, count_new), 'Exact hunk extent counts')
        result += lines[cursor:]
        after[name] = ''.join(result)
        path = out / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(after[name])
        pin(path, inputs['files'][name]['after_sha256'])
        witness = overlay['copied_two_file_postimages'][name]
        req(data(witness['path'], witness['sha256']) == path.read_bytes(), 'Independent reconstructed postimage equals retained author witness')
        products[name] = {'path': str(path), 'sha256': pin(path)}
    req(set(after) == {'osfmk/arm64/start.s', 'bsd/dev/e1s_log.c'}, 'Exactly two affected TUs')
    asm = after['osfmk/arm64/start.s']
    original_asm = old['osfmk/arm64/start.s']
    log = after['bsd/dev/e1s_log.c']
    original_log = old['bsd/dev/e1s_log.c']
    macro = asm.split('.macro E1S_BOOT_MARK n\n')[1].split('.endm')[0]
    instructions = [x.strip() for x in macro.splitlines() if x.strip() and not x.startswith('#')]
    req(instructions == ['adrp\tx9, Le1s_boot_marker@page', 'add\tx9, x9, Le1s_boot_marker@pageoff', 'movz\tx10, #\\n', 'str\tx10, [x9]'], 'Only four flag-neutral instructions and original scratch registers')
    req(set(re.findall(r'\bx\d+\b', macro)) == {'x9', 'x10'} and 'sp' not in macro, 'No new live-register or stack contract')
    req('\t.section __DATA,__data\n\t.align 3\nLe1s_boot_marker:\n\t.quad 0x4531534d41524b00\n\t.text\n' in asm, 'Explicit initialized aligned file-backed marker source intent')
    req(asm.split('\t.globl EXT(start_first_cpu)', 1)[1] == original_asm.split('\t.globl EXT(start_first_cpu)', 1)[1], 'All real callsites, boot mappings and MMU transition unchanged')
    req(re.findall(r'^\s+E1S_BOOT_MARK (\d+)$', asm, re.M) == ['1', '2', '3', '4'], 'Exactly existing four marker calls')
    req(asm.index('E1S_BOOT_MARK 4') < asm.index('// Enable caches, MMU, ROP and JOP'), 'All four stores precede MMU enable path')
    req(original_asm[:original_asm.index('.macro E1S_BOOT_MARK')].rfind('\t.text') >= 0, 'Return .text preserves original text section kind')
    req(original_log.split('static void\n', 1)[1].split('\nvoid\ne1s_log_init', 1)[0] == log.split('static void\n', 1)[1].split('\nvoid\ne1s_log_init', 1)[0], 'Actual header/append body byte preservation')
    req(original_log.split('e1s_log_init(void)\n{', 1)[1].split('\te1s_log =', 1)[0] == log.split('e1s_log_init(void)\n{', 1)[1].split('\te1s_log =', 1)[0], 'Actual disablearg/reset branch byte preservation')
    req('static uint8_t e1s_log_storage[E1S_LOG_SIZE] __attribute__((aligned(8)));' in log and '\te1s_log = e1s_log_storage;' in log, 'Full permanent image-lifetime ring source storage')
    req(all(x not in log for x in ['ml_io_map', '0x91300000', '0x91200000', 'E1S_LOG_PA']), 'No previous fixed ring PA or mapping call')
    req('0x912f' not in asm and '#0xf000' not in asm, 'No previous fixed marker PA')
    size = int(re.search(r'#define E1S_LOG_SIZE\s+\(1U << (\d+)\)', log).group(1))
    offset = int(re.search(r'#define E1S_LOG_DATA_OFF\s+(0x[0-9a-fA-F]+)U', log).group(1), 16)
    ring = (1 << size) - offset
    req(size == 20 and offset == 256 and ring > 0 and offset + ring - 1 == (1 << size) - 1, 'Actual ring modulo/offset index bound fits full1MiB')
    startup_path = next(p for p in inputs['inputs'] if p.endswith('/osfmk/kern/startup.c'))
    startup = data(startup_path).decode()
    req(startup.index('\tvm_mem_bootstrap();') < startup.index('\te1s_log_init();') and startup.count('\te1s_log_init();') == 1, 'Existing single late init after VM bootstrap')
    loader_path = next(p for p in inputs['inputs'] if p.endswith('/source/shim/e1s-xnu/loader.c'))
    loader = data(loader_path).decode()
    req('uintptr_t entry_pa = win_base + (p->entry_va - p->virt_base);' in loader and 'uintptr_t dst = win_base + (s->vmaddr - p->virt_base);' in loader, 'Source uniform physical slide for entry and every segment')
    req('copy(dst, payload_start + s->file_off, s->file_size);' in loader and 'zero(dst + s->file_size, s->vmsize - s->file_size);' in loader and 'clean(dst, dst + s->vmsize);' in loader, 'Source file-backed copy plus full virtual-tail zero/clean behavior')
    owned = load(overlay['actual_source_checks']['path'], overlay['actual_source_checks']['sha256'])
    req(owned['outcome'] == 'pass' and len(owned['checks']) == 44 and all(x['pass'] for x in owned['checks']), 'Retained preregistered44 source checks, not rerun')
    req([x['exit_code'] for x in owned['commands']] == [0, 0, 0, 1, 1], 'Actual Git positive/negative controls retained')
    req([x['id'] for x in overlay['affected_objects']] == ['osfmk/start.o', 'bsd/e1s_log.o'], 'Exact graph2 affected IDs; no all-object relabel')
    for name, identity in core.STATS.items():
        req(core.ident(Path(name).stat()) == identity, 'Pinned source stayed unchanged through review')
    pin(__file__)
    evidence = {'kind': 'source-review', 'origin': 'local-host', 'outcome': 'pass', 'task': 'INT-003', 'owner': 'codex-integrator-platform-20261106-cn', 'recorded_at': datetime.now(timezone.utc).isoformat(), 'checks': core.N, 'elapsed_seconds': time.monotonic() - start, 'reader_memory': core.rss(), 'reconstructed_postimages': products, 'source_sha256': pin(__file__), 'artifact_sha256': core.OBS,
        'accepted_scope': 'Exact2-TU diagnostic-storage source overlay only', 'remaining_acceptance': ['Actual AArch64 object marker data/relocations/alignment and ADRP range', 'Actual full1MiB ring writable persistent image extent, not freed init data', 'Final image and payload full filesize/vmsize/zerofill/segment nonoverlap coverage', 'Uniform4096-aligned slide and ADRP page delta within[-2^20,2^20-1] pages', 'Entire storage extents inside real owned DT RAM and bootstrap/final mapping coverage'],
        'compiler_QEMU_phone_or_producer_checker_rerun': False, 'shared_source_context_objects_or_namespace_mutated': False, 'actual_layout_mapping_physical_ownership_or_runtime_qualified': False}
    p = out / 'evidence.json'
    p.write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps({'outcome': 'pass', 'checks': evidence['checks'], 'evidence_sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'reader_memory': evidence['reader_memory']}))

if __name__ == '__main__':
    main()
