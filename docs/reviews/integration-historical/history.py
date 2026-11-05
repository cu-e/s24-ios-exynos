#!/usr/bin/env python3
"""Derive VM013 history with independent parent-to-commit no-rename diffs."""
import hashlib,json,os,subprocess
from pathlib import Path
ROOT=Path('/home/egor/dev/pet/s24-ios-exynos')
WT=ROOT/'worktrees/vm-013-20261106'
ENV=dict(os.environ,GIT_NO_LAZY_FETCH='1',GIT_OPTIONAL_LOCKS='0',GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='/dev/null',LC_ALL='C',PYTHONUTF8='1',PYTHONNOUSERSITE='1')
def git(*args):return subprocess.check_output(['git',*args],cwd=WT,env=ENV,timeout=20)
base='aac27cfbc0d71b34eda33ddf366c72427507ae0b'
tip='62d5ad1ac6f348c595b3b65c1c1d9305d8caf336'
commits=git('rev-list','--reverse',base+'..'+tip).decode().splitlines()
net=set(git('diff','--no-ext-diff','--no-textconv','--no-renames','--name-only','-z',base,tip).decode().strip('\0').split('\0'))
union=set();records=[]
for commit in commits:
 parent=git('rev-parse',commit+'^').decode().strip()
 paths=set(git('diff','--no-ext-diff','--no-textconv','--no-renames','--name-only','-z',parent,commit).decode().strip('\0').split('\0'))
 union|=paths
 records.append({'commit':commit,'parent':parent,'paths':sorted(paths)})
historical=union-net
assert len(commits)==8
assert historical=={'fixtures/public/avf-object-shards/iokit/inspect.py'}
result={'kind':'source-review','outcome':'pass','base':base,'tip':tip,'commits':records,'net_paths':sorted(net),'all_touched_paths':sorted(union),'exact_historical_paths':sorted(historical),'method':'Independent parent-to-commit Git diff --no-renames; not producer diff-tree implementation','compiler_guest_common_started':False}
Path(__file__).with_name('vm013-history.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'commits':len(commits),'net_paths':len(net),'touched_union':len(union),'historical_paths':sorted(historical)}))
