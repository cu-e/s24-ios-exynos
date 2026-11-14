#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""scJ: scH (NAT-152, run in NAT-153) with boot-arg fb_filter=0 (MiniIOMobileFramebuffer scales nearest-neighbour instead of
bilinear: NAT-156 lever 3) put where scH had the recording tokens `rec_secs=270 rec_mb=64`. The 255-byte line has no room for both
(scH: 253 bytes). Dropping the recording does not touch what scJ is compared with: in NAT-153 the recording filled its 64 MB at
345 s ("recording finished: 73 frames, 63 MB"), and the steady 70.7 ms windows came after that, with record() returning at once.

Also built in: NAT-157's loader message fix (fix_msg.wrap_cc on every nat-052 module of the chain), with relocscan as a gate next to
NAT-152's own (check_loader_sites rc 0, loader constants on the NAT-143 symbols). Kernel, ramdisk, root and ADT are scH's. Host build only.

  python3 -B docs/procedures/nat-158/build.py --out artifacts/nat-158/build-NNN --loader-source artifacts/nat-020/build-003/source \
          --ramdisk artifacts/nat-110/pid1-sc2-hb/root.apfs
"""
import hashlib
import importlib.util
import inspect
import json
import sys
import textwrap
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
NAME = 'loader-diag-xnu-scJ-md1'
TAG = 'nat_attempt=NAT158-scJ'
OLD_REC = ('rec_secs=270', 'rec_mb=64')
NEW = ('fb_filter=0',)
SCH_BUILD = ROOT / 'artifacts/nat-152/build-001'
# NAT-145's own check that its image records the screen; scJ must instead carry fb_filter=0 and no recording token
CHECK145_OLD = "    assert 'loader_return_after=270' in tokens and 'rec_secs=270' in tokens\n"
CHECK145_NEW = ("    assert 'loader_return_after=270' in tokens and 'fb_filter=0' in tokens and "
                "not any(t.startswith('rec_') for t in tokens)\n")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


fix = _load('nat158_fix157', HERE.parent / 'nat-157/fix_msg.py')
reloc = _load('nat158_reloc157', HERE.parent / 'nat-157/relocscan.py')
demo = _load('nat158_demo157', HERE.parent / 'nat-157/build_demo.py')
b152 = demo.b152
b148 = b152.b148
b145 = b148.b145
b143 = b152.b143


def main145_source():
    """nat-145/build.py main() with its one recording assertion replaced (counted: exactly one), nothing else."""
    src = textwrap.dedent(inspect.getsource(b145.main))
    assert src.count(CHECK145_OLD) == 1, 'NAT-145 main() changed'
    return src.replace(CHECK145_OLD, CHECK145_NEW)


def make_main145():
    """The function runs on nat-145's own module globals (b148 sets b145.NAME/TAG on them before calling it)."""
    code = compile(main145_source(), '<nat-158: nat-145 main, fb_filter check>', 'exec')
    fn = [c for c in code.co_consts if isinstance(c, types.CodeType) and c.co_name == 'main']
    assert len(fn) == 1
    return types.FunctionType(fn[0], vars(b145), 'main')


def expected_cmdline():
    """scH's line as built (NAT-152 build-001) with the recording tokens replaced in place and the tag changed."""
    old = json.loads((SCH_BUILD / 'build.json').read_text())['payload_fixes'][b152.NAME]['cmdline']
    assert old.count(' '.join(OLD_REC)) == 1 and old.count(b152.TAG) == 1
    return old.replace(' '.join(OLD_REC), ' '.join(NEW)).replace(b152.TAG, TAG)


def main():
    assert len(NAME) == len(b152.NAME) and len(TAG) == len(b152.TAG)
    assert b143.REC_TOKENS == OLD_REC, b143.REC_TOKENS
    want = expected_cmdline()
    b52 = [m for m in demo.chain_modules(b152) if m.__file__.endswith('nat-052/build.py')]
    assert b52, 'no nat-052 build module in the chain'
    saved = (b152.NAME, b152.TAG, b143.REC_TOKENS, b145.main, [m.cc for m in b52])
    b152.NAME, b152.TAG, b143.REC_TOKENS, b145.main = NAME, TAG, NEW, make_main145()
    for m in b52:
        m.cc = fix.wrap_cc(m.cc)
    args = list(sys.argv)
    try:
        b152.main()
    finally:
        sys.argv = args
        b152.NAME, b152.TAG, b143.REC_TOKENS, b145.main = saved[:4]
        for m, cc in zip(b52, saved[4]):
            m.cc = cc
    if '--check-only' in args or '--out' not in args:
        return
    out = Path(args[args.index('--out') + 1])
    path = out / 'build.json'
    report = json.loads(path.read_text())
    cmd = report['payload_fixes'][NAME]['cmdline']
    if cmd != want:
        raise SystemExit('cmdline is not scH\'s with fb_filter=0 in place of the recording:\n %r\n %r' % (cmd, want))
    assert len(cmd.encode()) <= 255, len(cmd.encode())
    img = out / NAME
    found = reloc.scan(img)
    bad = [r for r in found if not r['allowed']]
    text = (img / 'source/shim/e1s-xnu/ckpt3.c').read_text()
    if bad or 'static const char site[6][40]' not in text:
        raise SystemExit('NAT-157 fix not in the loader: %r' % bad)
    sch = SCH_BUILD / b152.NAME
    same = {n: hashlib.sha256((img / n).read_bytes()).hexdigest() == hashlib.sha256((sch / n).read_bytes()).hexdigest()
            for n in sorted(p.name for p in img.glob('[0-9][0-9]-*.o'))}
    report['nat158_changes'] = dict(
        cmdline_bytes=len(cmd.encode()), replaced=list(OLD_REC), by=list(NEW), tag=TAG,
        note='nat143_changes.rec_tokens holds fb_filter=0: NAT-143\'s recording slot is where this build puts it',
        relocations=len(found), relocations_not_allowed=0, loader_objects_same_as_scH=same,
        purpose='nearest-neighbour scaling on the single-core software path: driver ms per frame and frames/s against NAT-153')
    report['nat158_sources'] = {n: hashlib.sha256((HERE / n).read_bytes()).hexdigest() for n in ('build.py',)}
    path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(cmdline_bytes=len(cmd.encode()), relocations=len(found),
                          differing_objects=[k for k, v in same.items() if not v])))


if __name__ == '__main__':
    main()
