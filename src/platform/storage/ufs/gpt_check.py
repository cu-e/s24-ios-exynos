#!/usr/bin/env python3
"""Host checks for gpt.c: sanitizers plus single-line mutation. No device, MMIO or storage."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

SOURCE = Path(__file__).resolve().parent
ROOT = SOURCE.parents[3]
WARN = ['-Wall', '-Wextra', '-Werror', '-Wpedantic']
FILES = ['gpt.h', 'gpt.c', 'gpt_test.c', 'host.h', 'host.c', 'gpt_check.py']
MUTATIONS = [
    ('crc polynomial', 'UINT32_C(0xEDB88320)', 'UINT32_C(0xEDB88321)'),
    ('crc field counts as zero', '(i >= 16 && i < 20) ? 0 : h[i]', 'h[i]'),
    ('full signature checked', "h[6] != 'R' || h[7] != 'T') return UFS_GPT_SIGNATURE;", "h[6] != 'R') return UFS_GPT_SIGNATURE;"),
    ('revision checked', 'if (get32(h + 8) != REVISION || get32', 'if (get32'),
    ('header size checked', 'get32(h + 12) != UFS_GPT_HEADER_BYTES || get32(h + 20)) return', 'get32(h + 20)) return'),
    ('reserved dword checked', 'get32(h + 12) != UFS_GPT_HEADER_BYTES || get32(h + 20)) return', 'get32(h + 12) != UFS_GPT_HEADER_BYTES) return'),
    ('tail of block zero', 'if (!all_zero(h + UFS_GPT_HEADER_BYTES, bytes - UFS_GPT_HEADER_BYTES)) return UFS_GPT_HEADER;', ''),
    ('tail covers whole block', 'all_zero(h + UFS_GPT_HEADER_BYTES, bytes - UFS_GPT_HEADER_BYTES)', 'all_zero(h + UFS_GPT_HEADER_BYTES, 16)'),
    ('header CRC checked', 'if (header_crc(h) != get32(h + 16)) return UFS_GPT_CRC;', ''),
    ('entries CRC checked', 'if (ufs_gpt_crc32(entries, (size_t)count * UFS_GPT_ENTRY_BYTES) != get32(h + 88)) return UFS_GPT_CRC;', ''),
    ('header block size', 'if (bytes != disk->block_bytes) return UFS_GPT_ARGUMENT;', ''),
    ('my LBA is 1', 'if (get64(h + 24) != 1) return UFS_GPT_BOUNDS;', ''),
    ('alternate inside LUN', 'if (alternate >= disk->lun_blocks) return UFS_GPT_BOUNDS;', ''),
    ('usable range ordered', 'if (first_usable > last_usable || last_usable >= alternate) return UFS_GPT_BOUNDS;', 'if (last_usable >= alternate) return UFS_GPT_BOUNDS;'),
    ('usable range before backup', 'if (first_usable > last_usable || last_usable >= alternate) return UFS_GPT_BOUNDS;', 'if (first_usable > last_usable) return UFS_GPT_BOUNDS;'),
    ('array after header', 'if (entries_lba < 2 || entries_lba >= first_usable) return UFS_GPT_BOUNDS;', 'if (entries_lba >= first_usable) return UFS_GPT_BOUNDS;'),
    ('array before usable', 'if (entries_lba < 2 || entries_lba >= first_usable) return UFS_GPT_BOUNDS;', 'if (entries_lba < 2) return UFS_GPT_BOUNDS;'),
    ('entry size checked', 'if (size != UFS_GPT_ENTRY_BYTES || !count || count > UFS_GPT_MAX_ENTRIES) return UFS_GPT_ENTRIES;', 'if (!count || count > UFS_GPT_MAX_ENTRIES) return UFS_GPT_ENTRIES;'),
    ('entry count nonzero', 'if (size != UFS_GPT_ENTRY_BYTES || !count || count > UFS_GPT_MAX_ENTRIES) return UFS_GPT_ENTRIES;', 'if (size != UFS_GPT_ENTRY_BYTES || count > UFS_GPT_MAX_ENTRIES) return UFS_GPT_ENTRIES;'),
    ('entry count bounded', 'if (size != UFS_GPT_ENTRY_BYTES || !count || count > UFS_GPT_MAX_ENTRIES) return UFS_GPT_ENTRIES;', 'if (size != UFS_GPT_ENTRY_BYTES || !count) return UFS_GPT_ENTRIES;'),
    ('array buffer length matches', 'if (entries_bytes != array_bytes) return UFS_GPT_ARGUMENT;', 'if (entries_bytes < array_bytes) return UFS_GPT_ARGUMENT;'),
    ('array rounded up to blocks', 'array_blocks = array_bytes / disk->block_bytes + (array_bytes % disk->block_bytes != 0);', 'array_blocks = array_bytes / disk->block_bytes;'),
    ('array fits before usable', 'if (array_blocks > first_usable - entries_lba) return UFS_GPT_BOUNDS;', ''),
    ('unused entry all zero', 'if (!all_zero(e, UFS_GPT_ENTRY_BYTES)) return UFS_GPT_ENTRIES;', ''),
    ('partition ordered', 'if (first > last || first < first_usable || last > last_usable) return UFS_GPT_BOUNDS;', 'if (first < first_usable || last > last_usable) return UFS_GPT_BOUNDS;'),
    ('partition above usable start', 'if (first > last || first < first_usable || last > last_usable) return UFS_GPT_BOUNDS;', 'if (first > last || last > last_usable) return UFS_GPT_BOUNDS;'),
    ('partition below usable end', 'if (first > last || first < first_usable || last > last_usable) return UFS_GPT_BOUNDS;', 'if (first > last || first < first_usable) return UFS_GPT_BOUNDS;'),
    ('overlap rejected', 'if (first <= get64(o + 40) && get64(o + 32) <= last) return UFS_GPT_OVERLAP;', ''),
    ('overlap inclusive at end', 'first <= get64(o + 40) && get64(o + 32) <= last', 'first < get64(o + 40) && get64(o + 32) <= last'),
    ('overlap inclusive at start', 'first <= get64(o + 40) && get64(o + 32) <= last', 'first <= get64(o + 40) && get64(o + 32) < last'),
    ('userdata refused', 'if (same_text(name, wanted, refused, sizeof refused - 1, 1)) return UFS_GPT_REFUSED;', ''),
    ('userdata refused in any case', 'same_text(name, wanted, refused, sizeof refused - 1, 1)', 'same_text(name, wanted, refused, sizeof refused - 1, 0)'),
    ('duplicates rejected', 'if (matches > 1) return UFS_GPT_AMBIGUOUS;', ''),
    ('lookup is case sensitive', 'same_text(candidate, length, name, wanted, 0)', 'same_text(candidate, length, name, wanted, 1)'),
    ('name length compared', 'if (a_length != b_length) return 0;', ''),
    ('wide unit never matches', 'if (unit[1]) return 0;', ''),
    ('extent is inclusive', 'out->blocks = last - first + 1;', 'out->blocks = last - first;'),
    ('output zeroed first', 'out->first_block = 0; out->blocks = 0;', ''),
    ('block size allowlist', 'if (disk->block_bytes != 512 && disk->block_bytes != 4096) return UFS_GPT_ARGUMENT;', ''),
    ('LUN size nonzero', 'if (!disk->lun_blocks) return UFS_GPT_ARGUMENT;', ''),
    ('input name is ASCII', 'if ((unsigned char)name[wanted] > 0x7Fu) return UFS_GPT_ARGUMENT;', ''),
    ('input name bounded', 'if (!wanted || wanted > UFS_GPT_NAME_CHARS) return UFS_GPT_ARGUMENT;', 'if (!wanted) return UFS_GPT_ARGUMENT;'),
    ('input name nonempty', 'if (!wanted || wanted > UFS_GPT_NAME_CHARS) return UFS_GPT_ARGUMENT;', 'if (wanted > UFS_GPT_NAME_CHARS) return UFS_GPT_ARGUMENT;'),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    parser.add_argument('--host-clang', type=Path, default=Path('/home/egor/.local/bin/clang'))
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', args.run):
        raise ValueError('Invalid run name')
    out = ROOT/'artifacts/ufs-gpt'/args.run
    out.mkdir(parents=True, exist_ok=False)
    snapshot = out/'source'
    snapshot.mkdir()
    report = dict(schema_version=1, kind='host-test', origin='local-host', outcome='inconclusive', recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                  commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=SOURCE, text=True).strip(), commands=[], mutations=[], sha256={},
                  device_io=False, mmio=False, storage_access=False, real_gpt_examined=False)
    flags = ['-std=c11', *WARN, '-g', '-O1', '-fno-omit-frame-pointer', '-fsanitize=address,undefined', '-fno-sanitize-recover=all']
    try:
        for name in FILES:
            shutil.copyfile(SOURCE/name, snapshot/name)
            report['sha256'][name] = hashlib.sha256((SOURCE/name).read_bytes()).hexdigest()
        build = [str(args.host_clang), *flags, str(snapshot/'gpt.c'), str(snapshot/'host.c'), str(snapshot/'gpt_test.c'), '-I', str(snapshot), '-o', str(out/'gpt-asan')]
        done = subprocess.run(build, capture_output=True, text=True, timeout=60)
        report['commands'].append(dict(argv=build, exit_code=done.returncode, stderr=done.stderr[-1500:]))
        if done.returncode:
            raise RuntimeError(done.stderr)
        done = subprocess.run([str(out/'gpt-asan')], capture_output=True, text=True, timeout=60)
        report['commands'].append(dict(argv=[str(out/'gpt-asan')], exit_code=done.returncode, stdout=done.stdout, stderr=done.stderr[-1500:]))
        if done.returncode:
            raise RuntimeError(done.stderr or done.stdout)
        report['tests'] = json.loads(done.stdout)
        original = (snapshot/'gpt.c').read_text()
        survivors = []
        for rule, before, after in MUTATIONS:
            if original.count(before) != 1:
                raise ValueError(f'Mutation text must occur once ({original.count(before)}): {rule}')
            work = out/'mutant'
            shutil.rmtree(work, ignore_errors=True)
            work.mkdir()
            (work/'gpt.c').write_text(original.replace(before, after))
            built = subprocess.run([str(args.host_clang), '-std=c11', '-g', '-O1', '-w', '-fsanitize=address,undefined', '-fno-sanitize-recover=all', str(work/'gpt.c'), str(snapshot/'host.c'), str(snapshot/'gpt_test.c'), '-I', str(snapshot), '-o', str(work/'test')], capture_output=True, text=True, timeout=60)
            result = dict(rule=rule)
            if built.returncode:
                result.update(state='build-error', detail=built.stderr[-300:]); survivors.append(rule)
            else:
                try:
                    ran = subprocess.run([str(work/'test')], capture_output=True, text=True, timeout=30)
                    result.update(state='killed' if ran.returncode else 'survived', exit_code=ran.returncode, detail=(ran.stderr or ran.stdout)[:200])
                except subprocess.TimeoutExpired:
                    result.update(state='killed', exit_code='timeout')
                if result['state'] == 'survived':
                    survivors.append(rule)
            report['mutations'].append(result)
        shutil.rmtree(out/'mutant', ignore_errors=True)
        report['mutation_count'] = len(MUTATIONS)
        report['mutation_survivors'] = survivors
        report['outcome'] = 'fail' if survivors else 'pass'
    except Exception as error:
        report.update(outcome='fail', error=repr(error))
    (out/'evidence.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(outcome=report['outcome'], tests=report.get('tests'), mutations=len(report['mutations']), survivors=report.get('mutation_survivors'), error=report.get('error')), indent=1))
    return 0 if report['outcome'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
