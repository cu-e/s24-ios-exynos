#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""scD: scC (NAT-141) with the NAT-143 touch kernel (every STM press/release logged with its time) and a longer fed kernel window,
so that the iOS home screen is up for about two minutes before the timed return instead of about ten seconds (NAT-142: home screen
at ~243 s, timed return at ~252 s with loader_return_after=150).

Time rules (NAT-079 rule, NAT-115 pixel-report term), checked by the chain and again here:
    receive cap 240 + loader_return_after 270 + loader work 60 + pixel report 25 = 595 <= deadline 595 <= 600
The kernel cuts loader_return_after back to 63 s by itself whenever the watchdog feed is not proven (NAT-115's e1s_wdt_window).
rec_secs=270 keeps the screen recording on over the same window (rec_mb=64 unchanged: a ring of about 70 frames at 1/3 scale).
Engine, root, ramdisk and every other cmdline token are scC's. Host build only.

  python3 docs/procedures/nat-143/build.py --out artifacts/nat-143/build-NNN --loader-source artifacts/nat-020/build-003/source \
          --ramdisk artifacts/nat-110/pid1-sc2-hb/root.apfs
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
NAME = 'loader-diag-xnu-scD-md1'
TAG = 'nat_attempt=NAT143-scD'
KERNEL_DIR = ROOT / 'artifacts/nat-143/kernel-001'
RETURN_AFTER = 270
DEADLINE = 595
RX_CAP = 240
REC_TOKENS = ('rec_secs=270', 'rec_mb=64')
spec = importlib.util.spec_from_file_location('nat143_build141', HERE.parent / 'nat-141/build.py')
b141 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b141)
b123 = b141.b123
b115 = b123.b119.b115


def main():
    assert RX_CAP + RETURN_AFTER + 60 + 25 <= DEADLINE <= 600, 'time rules'
    assert len(NAME) == len(b141.NAME) and len(TAG) == len(b141.TAG)
    assert b115.RETURN_AFTER_NEW == 150 and b115.DEADLINE_NEW == 475 and b115.RX_CAP == RX_CAP
    assert b115.REC_TOKENS == ('rec_secs=150', 'rec_mb=64')
    args = list(sys.argv)
    out = list(args)
    for k, v in (('--return-after-s', RETURN_AFTER), ('--deadline-s', DEADLINE)):
        if k in out:
            raise SystemExit('%s is fixed by this build' % k)
        out += [k, str(v)]
    saved = (b141.NAME, b141.TAG, b141.KERNEL_DIR, b115.RETURN_AFTER_NEW, b115.DEADLINE_NEW, b115.REC_TOKENS)
    b141.NAME, b141.TAG, b141.KERNEL_DIR = NAME, TAG, KERNEL_DIR
    b115.RETURN_AFTER_NEW, b115.DEADLINE_NEW, b115.REC_TOKENS = RETURN_AFTER, DEADLINE, REC_TOKENS
    sys.argv = out
    try:
        b141.main()
    finally:
        sys.argv = args
        b141.NAME, b141.TAG, b141.KERNEL_DIR, b115.RETURN_AFTER_NEW, b115.DEADLINE_NEW, b115.REC_TOKENS = saved
    if '--check-only' in args or '--out' not in args:
        return
    path = Path(args[args.index('--out') + 1]) / 'build.json'
    report = json.loads(path.read_text())
    cmd = report['payload_fixes'][NAME]['cmdline']
    tokens = cmd.split()
    for t in REC_TOKENS + (TAG, 'loader_return_after=%d' % RETURN_AFTER, 'e1s_wdt_pet=1', 'msgbuf=1048576', 'e1spmic=2'):
        assert tokens.count(t) == 1, t
    for t in ('rec_secs=150', 'loader_return_after=150', 'nat_attempt=NAT141-scC'):
        assert t not in tokens, t
    assert len(cmd.encode()) <= 255, len(cmd.encode())
    rec = json.loads((KERNEL_DIR / 'rebuild.json').read_text())
    assert rec['expect_strings'].get('e1s-touch: %s %u: finger %u x %u y %u') == 1
    report['nat143_changes'] = dict(kernel=rec['no_storage_sha256'], kernel_dir=str(KERNEL_DIR.relative_to(ROOT)),
                                    return_after_s=RETURN_AFTER, deadline_s=DEADLINE, rx_cap_s=RX_CAP, rec_tokens=list(REC_TOKENS),
                                    cmdline_bytes=len(cmd.encode()),
                                    purpose='home screen up for about two minutes; every STM press/release logged with its time')
    report['nat143_sources'] = {'build.py': hashlib.sha256((HERE / 'build.py').read_bytes()).hexdigest()}
    path.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
