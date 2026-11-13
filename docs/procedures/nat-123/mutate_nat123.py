#!/usr/bin/env python3
"""Bounded host mutations; never alter real patches or open the phone."""
import difflib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DONOR = ROOT / 'worktrees/str-014-e1s-native-source-ports-20261106/artifacts/e1s-native-source-ports/derive-001/xnu/bsd/dev'
MUTATIONS = [
    ('readback-error-success', 'e1s_pmic', 'return error;\n\t}\n\tif (now != value)', 'return 0;\n\t}\n\tif (now != value)'),
    ('readback-equality-removed', 'e1s_pmic', 'if (now != value)', 'if (0)'),
    ('identity-not-pinned', 'e1s_pmic', 'if (chip27 != 0x01)', 'if (0)'),
    ('already-on-wrong-voltage', 'e1s_pmic', 'if ((old & E1S_PMIC_LDO_ENABLE_MASK) == E1S_PMIC_LDO_ENABLE &&\n\t    (old & E1S_PMIC_LDO_VSEL_MASK) != (sel & E1S_PMIC_LDO_VSEL_MASK))', 'if (0)'),
    ('write-allowlist-removed', 'e1s_acpm', 'if (sid != 0x0d || type != 0x05 ||', 'if (0 && (sid != 0x0d || type != 0x05 ||'),
    ('pointer-check-removed', 'e1s_acpm', 'if ((ptr & 3) != 0 || ptr > E1S_ACPM_SRAM_SIZE - 4)', 'if ((ptr & 3) != 0)'),
    ('double-base-offset', 'e1s_acpm', 'q_len = slot[12 + 28];', 'q_len = slot[ch + 28];'),
]


def main():
    originals = {name: (DONOR / (name + '.c')).read_text() for name in ('e1s_pmic', 'e1s_acpm')}
    with tempfile.TemporaryDirectory(prefix='nat123-mut-', dir=os.environ.get('TMPDIR')) as tmp:
        tmp = Path(tmp)
        patched = {}
        for name in originals:
            target = tmp / (name + '.c')
            target.write_text(originals[name])
            subprocess.run(['patch', '-s', str(target), str(HERE / (name + '.patch'))], check=True)
            patched[name] = target.read_text()
        rows = []
        for label, name, old, new in MUTATIONS:
            assert patched[name].count(old) == 1, label
            changed = patched[name].replace(old, new)
            if label == 'write-allowlist-removed':
                changed = changed.replace('(reg == 0x3d && value == 0xd8))) {', '(reg == 0x3d && value == 0xd8)))) {')
            case = tmp / label
            case.mkdir()
            for obj in originals:
                text = changed if obj == name else patched[obj]
                diff = ''.join(difflib.unified_diff(originals[obj].splitlines(True), text.splitlines(True), fromfile='a.c', tofile='b.c'))
                (case / (obj + '.patch')).write_text(diff)
            env = dict(os.environ, NAT123_PATCH_DIR=str(case))
            result = subprocess.run([sys.executable, '-B', '-I', str(HERE / 'test_nat123.py'), 'TransportTests'],
                                    env=env, capture_output=True, text=True, timeout=30)
            killed = result.returncode != 0 and 'FAIL:' in result.stderr and 'ERROR:' not in result.stderr
            rows.append(dict(mutation=label, killed=killed, exit_code=result.returncode,
                             stderr_tail=result.stderr[-500:]))
        out = ROOT / 'artifacts/nat-123/mutations.json'
        out.write_text(json.dumps(rows, indent=2) + '\n')
        print(json.dumps(dict(killed=sum(r['killed'] for r in rows), total=len(rows))))
        return 0 if all(r['killed'] for r in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
