"""Compile only the actual pinned E1S pure decoder; never its hardware functions."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / 'references/s24-port'
SOURCE_PATCH = UPSTREAM / 'xnu/e1s/patches/0003-e1s-touch.patch'
CORRECTION = ROOT / 'patches/display-input/0001-e1s-stm-coordinate-nibbles.patch'
PIN = 'c8860decc62c6d6180e609036d027a2997972420'


def source_file():
    head = subprocess.check_output(['git', '-C', str(UPSTREAM), 'rev-parse', 'HEAD'], text=True).strip()
    if head != PIN:
        raise ValueError('E1S source pin mismatch')
    # Extract only additions to the new source file, not every file in the patch.
    text = SOURCE_PATCH.read_text().split('diff --git a/bsd/dev/e1s_touch.c b/bsd/dev/e1s_touch.c\n', 1)[1]
    text = text.split('\ndiff --git ', 1)[0]
    return '\n'.join(line[1:] for line in text.splitlines() if line.startswith('+') and not line.startswith('+++')) + '\n'


def function(text):
    start = text.index('static void\npost_event(const uint8_t *event)\n{')
    brace = text.index('{', start)
    depth = 0
    for at in range(brace, len(text)):
        depth += (text[at] == '{') - (text[at] == '}')
        if depth == 0:
            return text[start:at + 1]
    raise ValueError('Incomplete pure decoder')


def corrected(text, work):
    path = work / 'bsd/dev/e1s_touch.c'
    path.parent.mkdir(parents=True)
    path.write_text(text)
    # A real Git root prevents silently skipped parent-relative patch paths.
    subprocess.run(['git', '-C', str(work), 'init', '--quiet'], check=True, capture_output=True)
    for check in (True, False):
        subprocess.run(['git', '-C', str(work), '-c', 'core.hooksPath=/dev/null', 'apply',
                        *(['--check'] if check else []), str(CORRECTION)], check=True, capture_output=True)
    return path.read_text()


def harness(text):
    constants = '\n'.join(line for line in text.splitlines() if line.startswith('#define STM_'))
    return r'''#include <stdint.h>
#include <stdio.h>
#define REDWOOD_TOUCH_DOWN 1
#define REDWOOD_TOUCH_MOVE 2
#define REDWOOD_TOUCH_UP 3
static uint32_t e1s_flip, down[10], last_x[10], last_y[10];
static unsigned calls, got_x, got_y;
static void redwood_touch_post(uint32_t type, uint32_t finger, uint32_t x, uint32_t y)
{ (void)type; (void)finger; ++calls; got_x=x; got_y=y; }
''' + constants + '\n' + function(text) + r'''
int main(void) {
    unsigned bad=0, total=0, x, y, flip, lowx, lowy;
    /* All 256 low-nibble pairs, varied upper bytes and each mirror policy.
       Synthetic bytes encoded from Samsung's named x/y field layout. */
    for (flip=0; flip<4; ++flip) for (lowx=0; lowx<16; ++lowx) for (lowy=0; lowy<16; ++lowy) {
        uint8_t event[16]={0}; unsigned wantx,wanty;
        x=(0x12u << 4)|lowx; y=(0xabu << 4)|lowy;
        event[0]=0x40; event[1]=(uint8_t)(x >> 4); event[2]=(uint8_t)(y >> 4);
        event[3]=(uint8_t)((lowx << 4)|lowy);
        e1s_flip=flip; calls=0; down[0]=0;
        post_event(event); ++total;
        wantx=x*65535u/4095u; wanty=y*65535u/4095u;
        if (flip&1) wantx=65535u-wantx;
        if (flip&2) wanty=65535u-wanty;
        if (calls!=1 || got_x!=wantx || got_y!=wanty) ++bad;
    }
    printf("{\"vectors\":%u,\"mismatches\":%u,\"hardware_io\":false}\n",total,bad);
    return bad ? 3 : 0;
}
'''


def compile_run(text, directory):
    source = directory / 'pure-decoder.c'
    source.write_text(harness(text))
    binary = directory / 'pure-decoder'
    commands = []
    for argv in (['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-Wpedantic', str(source), '-o', str(binary)], [str(binary)]):
        r = subprocess.run(argv, capture_output=True, text=True, timeout=30)
        commands.append(dict(argv=argv, exit_code=r.returncode, stdout=r.stdout, stderr=r.stderr))
        if argv[0] == 'cc' and r.returncode:
            raise ValueError(r.stderr)
    return json.loads(commands[-1]['stdout']), commands


class E1STouchRegression(unittest.TestCase):
    def test_actual_pinned_decoder_mismatch_and_minimal_correction(self):
        if not SOURCE_PATCH.is_file() or not shutil.which('cc'):
            self.skipTest('Explicit pinned checkout and host C compiler required')
        with tempfile.TemporaryDirectory(prefix='e1s-touch-source-') as td:
            work = Path(td)
            original = source_file()
            a, commands = compile_run(original, work)
            self.assertEqual(commands[-1]['exit_code'], 3)
            self.assertEqual(a, dict(vectors=1024, mismatches=960, hardware_io=False))
            fixed = corrected(original, work / 'patched')
            b, commands = compile_run(fixed, work)
            self.assertEqual(commands[-1]['exit_code'], 0)
            self.assertEqual(b, dict(vectors=1024, mismatches=0, hardware_io=False))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run', required=True)
    p.add_argument('--original', action='store_true')
    args = p.parse_args()
    if not args.run.replace('-', '').replace('_', '').isalnum() or len(args.run) > 80:
        raise ValueError('Invalid run name')
    out = ROOT / 'artifacts/touch-regression' / args.run
    if out.resolve() != out:
        raise ValueError('Run must not use symlinks')
    out.mkdir(parents=True, exist_ok=False)
    text = source_file()
    (out / 'original-source.c').write_text(text)
    if not args.original:
        text = corrected(text, out / 'patched')
    result, commands = compile_run(text, out)
    paths = [SOURCE_PATCH, Path(__file__), out / 'pure-decoder.c', out / 'original-source.c']
    if not args.original:
        paths += [CORRECTION, out / 'patched/bsd/dev/e1s_touch.c']
    report = dict(kind='host-test', origin='local-host', outcome='fail' if result['mismatches'] else 'pass',
                  recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                  commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                  original_source=args.original, result=result, commands=commands,
                  sha256={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths},
                  limitations=['Pure extracted post_event with explicit host capture shim only',
                               'Synthetic vectors; no kernel link, SPI/GPIO/MMIO, firmware or device execution'])
    (out / 'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report['result']))
    return commands[-1]['exit_code']


if __name__ == '__main__':
    if '--run' in __import__('sys').argv:
        raise SystemExit(main())
    unittest.main()
