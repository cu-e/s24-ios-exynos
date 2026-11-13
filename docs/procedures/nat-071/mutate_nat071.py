#!/usr/bin/env python3
"""NAT-071 mutation pass: each mutant of the e1s_wdt block (in the patched loader_return.c) must be killed by test_nat071.py."""
import json, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import test_nat071 as T  # noqa: E402

MUTANTS = [
    ('enabled check', 'enabled == 0) {\n\t\tgoto unfed;', 'enabled == 2) {\n\t\tgoto unfed;'),
    ('WTCON mask', '#define E1S_WDT_ENABLED_RESET   0x21u', '#define E1S_WDT_ENABLED_RESET   0x01u'),
    ('WTDAT lower bound', 'dat < 64 ||', 'dat < 1 ||'),
    ('WTDAT upper bound', 'dat > 0xffff)', 'dat > 0x1ffff)'),
    ('mapping check', 'if (w == NULL) {', 'if (0) {'),
    ('watchdog address', '#define E1S_WDT_PA              0x10040000ULL', '#define E1S_WDT_PA              0x10050000ULL'),
    ('grace', '#define E1S_WDT_GRACE_S         5', '#define E1S_WDT_GRACE_S         50'),
    ('unfed cap', '#define E1S_WDT_UNFED_MAX_S     63', '#define E1S_WDT_UNFED_MAX_S     83'),
    ('unfed cap applied', 'return E1S_WDT_UNFED_MAX_S;', 'return seconds;'),
    ('deadline compare', 'mach_absolute_time() >= e1s_wdt_until', 'mach_absolute_time() > e1s_wdt_until + 1000000000ull'),
    ('stop is final', 'if (e1s_wdt == NULL || e1s_wdt_stopped) {', 'if (e1s_wdt == NULL) {'),
    ('WTCNT reload in feed', 'e1s_wdt[E1S_WDT_WTCNT] = e1s_wdt[E1S_WDT_WTDAT];', 'e1s_wdt[E1S_WDT_WTCNT] = 0x7fff;'),
    ('WTCLRINT in feed', 'e1s_wdt[E1S_WDT_WTCLRINT] = 0;', ''),
    ('first reload', 'w[E1S_WDT_WTCNT] = dat;', ''),
    ('read-back check', 'if (cnt1 > dat || cnt1 < dat - (dat >> 6)) {', 'if (cnt1 > dat) {'),
    ('window uses seconds', 'clock_interval_to_deadline(seconds + E1S_WDT_GRACE_S,', 'clock_interval_to_deadline(seconds * 2 + E1S_WDT_GRACE_S,'),
    ('armed only after checks', '\te1s_wdt = w;\n\tprintf', '\tprintf'),
]


def main():
    src = T.patched_source()
    res = []
    for name, old, new in MUTANTS:
        if src.count(old) != 1:
            raise SystemExit(f'mutant {name!r}: pattern found {src.count(old)} times')
        with tempfile.TemporaryDirectory() as d:
            m = Path(d)/'m.c'
            m.write_text(src.replace(old, new))
            r = subprocess.run([sys.executable, '-B', '-I', str(HERE/'test_nat071.py'), '--src', str(m)], capture_output=True, text=True)
            res.append((name, r.returncode != 0))
    survived = [n for n, k in res if not k]
    print(json.dumps({'total': len(res), 'killed': len(res) - len(survived), 'survived': survived}))
    return 1 if survived else 0


if __name__ == '__main__':
    raise SystemExit(main())
