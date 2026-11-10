#!/usr/bin/env python3
from pathlib import Path
import shutil
import sys
src=Path(sys.argv[1])/'shim/e1s-xnu'
for name in ['s5e9945.c','s5e9945.h']:
    shutil.copyfile(Path('src/native/watchdog')/name,src/name)
shutil.copyfile('docs/procedures/nat-009/recovery_guard.c',src/'recovery_guard.c')
p=src/'start.S'; s=p.read_text()
old='3:\n\tmov\tx0, x19'
assert s.count(old)==1
s=s.replace(old,'3:\n\tbl\trecovery_guard\n\tcbnz\tx0, halt\n\tmov\tx0, x19')
p.write_text(s)
