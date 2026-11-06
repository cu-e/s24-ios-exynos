#!/usr/bin/env python3
"""Read-only frozen capsule intake; no control replay."""
import hashlib,json
from pathlib import Path
ROOT=Path('/home/egor/dev/pet/s24-ios-exynos');FC=ROOT/'worktrees/vm-048-20261106';HERE=Path(__file__).resolve().parent
p=FC/'docs/procedures/avf-allocator-retention/evidence.json';d=json.loads(p.read_text());rows=[]
for rel,expected in d['artifact_hashes'].items():
 path=FC/rel;h=hashlib.sha256()
 with path.open('rb') as stream:
  for block in iter(lambda:stream.read(1024**2),b''):h.update(block)
 rows.append(dict(path=str(path),sha256=h.hexdigest(),size=path.stat().st_size,pass_=h.hexdigest()==expected['sha256'] and path.stat().st_size==expected['size']))
out=dict(schema=1,outcome='pass' if all(x['pass_'] for x in rows) else 'fail',bindings=rows,control_replayed=False)
(HERE/'bindings.json').write_text(json.dumps(out,indent=2)+'\n');print(out['outcome'],len(rows));raise SystemExit(0 if out['outcome']=='pass' else 1)
