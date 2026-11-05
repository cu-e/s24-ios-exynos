#!/usr/bin/env python3
"""Use the frozen accepted finite source-process boundary; no compiler command."""
import hashlib
import importlib.util
import json
from pathlib import Path
import os
import subprocess
import sys

MAIN=Path('/home/egor/dev/pet/s24-ios-exynos')
HERE=Path(__file__).resolve().parent
process=MAIN/'worktrees/vm-035-20261106/tools/build/avf_kernel_objects.py'
def sha(p):
    with Path(p).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
assert sha(process)=='5c7b9c549e2740f3fad2a80c060e558dff3c9aa15e98bb2d9a56b33684e687d8'
spec=importlib.util.spec_from_file_location('accepted_process',process)
engine=importlib.util.module_from_spec(spec);spec.loader.exec_module(engine)
out=HERE/'runs'/sys.argv[1];out.mkdir(parents=True,exist_ok=False)
record={'kind':'source-review','origin':'local-host','task':'INT-003','experiment':'PLATFHNS-001',
        'command':sys.orig_argv,'process_path':str(process),'process_sha256':sha(process),
        'script_sha256':sha(HERE/'review.py'),'supervisor_script_sha256':sha(__file__)}
author=MAIN/'worktrees/vm-038-20261106'
frozen='2e9956ce4d02dd13932513f3049ab2e22b4ee90d'
record['read_only_git_commands']=[]
for name,cwd,argv in [
    ('qualifier-source.py',author,['git','show',frozen+':tools/build/avf_firehose_namespace.py']),
    ('fixture-source.json',author,['git','show',frozen+':fixtures/public/avf-firehose-namespace/inputs.json']),
    ('source-blobs.txt',MAIN/'references/xnu-kernel-firehose',
     ['git','ls-tree','a641558f447659d90ad002ef0ee6f0212273fbfc','--','os/firehose_buffer_private.h',
      'xcodeconfig/libfirehose_kernel.xcconfig','libdispatch.xcodeproj/project.pbxproj','LICENSE'])]:
    child=subprocess.run(argv,cwd=cwd,env=dict(os.environ,GIT_NO_LAZY_FETCH='1',GIT_OPTIONAL_LOCKS='0'),
                         capture_output=True,timeout=30)
    (out/name).write_bytes(child.stdout)
    record['read_only_git_commands'].append({'argv':argv,'cwd':str(cwd),'exit_code':child.returncode,
                                             'stdout_sha256':sha(out/name),'stderr':child.stderr.decode()})
    if child.returncode: raise RuntimeError('Read-only Git capture failed')
result=engine.run_child([sys.executable,'-B','-s',str(HERE/'review.py'),'--out',str(out)],
                        HERE,out,'review',engine.supervisor(MAIN),timeout=150,admit=True)
record.update(outcome=result['outcome'],child=result)
(out/'supervised.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({'outcome':result['outcome'],'exit_code':result.get('exit_code'),
                  'peak_owned_RSS':result.get('peak_total_owned_rss_bytes'),
                  'evidence':str(out/'supervised.json')}))
sys.exit(0 if result['outcome']=='pass' else 1)
