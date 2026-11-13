#!/usr/bin/env python3
"""NAT-115 mutation pass over analyze116.py: every mutant must be killed by test_nat115.py (Analyse tests)."""
import json, subprocess, sys, tempfile, shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
MUTANTS = [
    ('logo hash', 'LOGO_FNV = 0xd5b719ed', 'LOGO_FNV = 0xd5b719ee'),
    ('window needs feed', 'r["fed"] is not None and', ''),
    ('window refuses cut', 'and r["cut"] is None', ''),
    ('window needs expiry', 'and r["expired"]', ''),
    ('window needs pixels', 'and pixels.get("complete") is True', ''),
    ('new frame needs bytes', 'and f.get("nzb", 0) > 0', 'and f.get("nzb", 0) >= 0'),
    ('runnable test', 'if main["state"] & TH_RUN and not main["state"] & TH_WAIT:', 'if main["state"] & TH_WAIT:'),
    ('port owner hints', 'main["hint"] in (HINT_PORT_RECEIVE, HINT_PORT_SEND)', 'main["hint"] in (HINT_PORT_SEND,)'),
    ('turnstile owner', 'if owner is None and main["ts"] == "P" and main["ts_ctx"] > 0:', 'if False:'),
    ('backboardd is display', 'oname == BACKBOARDD or ', ''),
    ('first thread', 'key=lambda t: t["n"])\n    bb', 'key=lambda t: -t["n"])\n    bb'),
    ('backboardd fb wait', 'if bb and bb[0]["state"] & TH_WAIT and any(h in bb[0]["svc"] for h in FB_HINTS):', 'if False:'),
]


def main():
    src = (HERE/'analyze116.py').read_text()
    res = []
    for name, old, new in MUTANTS:
        if src.count(old) != 1:
            raise SystemExit('mutant %r: pattern found %d times' % (name, src.count(old)))
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            for f in ('test_nat115.py', 'kernel-combined.patch', '0002-wait-dump.patch', 'derive115.py'):
                shutil.copy(HERE/f, d/f)
            (d/'analyze116.py').write_text(src.replace(old, new))
            # run only the analyser tests from the copy (ROOT-relative fixtures resolve through the original tree)
            code = ("import sys,unittest;sys.path.insert(0,%r);import test_nat115 as T;T.ROOT=%r;"
                    "T.NAT113_TEXT=T.ROOT/'artifacts/nat-113/analysis/kernel-text.txt';T.NAT113_PIX=T.ROOT/'artifacts/nat-113/analysis/pixels.json';"
                    "r=unittest.TextTestRunner(verbosity=0).run(unittest.defaultTestLoader.loadTestsFromTestCase(T.Analyse));"
                    "sys.exit(0 if r.wasSuccessful() else 1)") % (str(d), str(HERE.parents[2]))
            from pathlib import PosixPath  # noqa: F401
            r = subprocess.run([sys.executable, '-B', '-c', code.replace("T.ROOT=%r" % str(HERE.parents[2]), "T.ROOT=__import__('pathlib').Path(%r)" % str(HERE.parents[2]))],
                               capture_output=True, text=True)
            res.append((name, r.returncode != 0))
    survived = [n for n, k in res if not k]
    print(json.dumps({'total': len(res), 'killed': len(res) - len(survived), 'survived': survived}))
    return 1 if survived else 0


if __name__ == '__main__':
    raise SystemExit(main())
