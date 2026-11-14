#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-157: NAT-152's scH build with the fix installed (fix_msg.wrap_cc on the chain's nat-052 cc), host only, never run on the phone.
Shows that a full image build takes the hook: the loader objects then carry no absolute relocation but the header's (relocscan), and
NAT-152's own gate (the loader's checkpoint check, constants on the NAT-143 symbols) still passes. Same arguments as nat-152/build.py.

  python3 -B docs/procedures/nat-157/build_demo.py --out artifacts/nat-157/build-001 --loader-source artifacts/nat-020/build-003/source \
          --ramdisk artifacts/nat-110/pid1-sc2-hb/root.apfs
"""
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


fix = _load('nat157_fix_b', HERE / 'fix_msg.py')
reloc = _load('nat157_reloc_b', HERE / 'relocscan.py')
b152 = _load('nat157_b152', HERE.parent / 'nat-152/build.py')


def chain_modules(root):
    """Every module reachable from root through module attributes: the chain loads its bases with module_from_spec and does not
    always register them in sys.modules, so the instance that compiles is found this way, not by name."""
    seen, todo = {}, [root]
    while todo:
        m = todo.pop()
        if id(m) in seen:
            continue
        seen[id(m)] = m
        todo += [v for v in vars(m).values() if type(v) is type(sys) and getattr(v, '__file__', '') and '/docs/procedures/' in v.__file__]
    return list(seen.values())


def main():
    b52 = [m for m in chain_modules(b152) if m.__file__.endswith('nat-052/build.py')]
    assert len(b52) >= 1, 'no nat-052 build module in the chain'
    for m in b52:
        m.cc = fix.wrap_cc(m.cc)
    b152.main()
    out = Path(sys.argv[sys.argv.index('--out') + 1])
    img = out / b152.NAME
    found = reloc.scan(img)
    bad = [r for r in found if not r['allowed']]
    text = (img / 'source/shim/e1s-xnu/ckpt3.c').read_text()
    rec = dict(relocations=len(found), bad=bad, fixed_source='static const char site[6][40]' in text,
               table_of_pointers='static const char *const site[]' in text)
    (out / 'nat157.json').write_text(json.dumps(rec, indent=1) + '\n')
    print(json.dumps(rec))
    if bad or not rec['fixed_source'] or rec['table_of_pointers']:
        raise SystemExit('NAT-157 hook not effective')


if __name__ == '__main__':
    main()
