#!/usr/bin/env python3
"""Controlled validation counterexamples; historical objects are negative controls only."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from types import ModuleType, SimpleNamespace

MAIN=Path('/home/egor/dev/pet/s24-ios-exynos')
AUTHOR=MAIN/'worktrees/vm-036-dz-fix1-20261106'
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def imported(path,expected,name):
    data=path.read_bytes()
    assert hashlib.sha256(data).hexdigest()==expected
    m=ModuleType(name);m.__file__=str(path);exec(compile(data,str(path),'exec'),m.__dict__);return m
def member(name,body):
    n=(name+'/').ljust(16)
    assert len(n)==16
    return (n+'0'.ljust(12)+'0'.ljust(6)+'0'.ljust(6)+'100644'.ljust(8)+str(len(body)).ljust(10)+'`\n').encode()+body+(b'\n'if len(body)%2 else b'')

p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
record={'kind':'host-test','origin':'local-host','task':'INT-003','experiment':'PLATCOMP-001',
        'recorded_at':datetime.now(timezone.utc).isoformat(),'command':sys.orig_argv,
        'summary':'Independent controlled object-identity and archive-member validation probes; no component compilation.',
        'compiler_executed':False,'archiver_executed':False,'historical_objects_are_negative_controls_not_guest_products':True}
try:
    m=imported(AUTHOR/'tools/build/avf_guest_components.py',
               '5152e733f95da9b0d2a01da6e1eb9b1b22d9bd75bc47187387e19d29e515d718','corrected_adapter')
    helper=imported(MAIN/'worktrees/vm-035-20261106/tools/build/avf_kernel_objects.py',
                    '5c7b9c549e2740f3fad2a80c060e558dff3c9aa15e98bb2d9a56b33684e687d8','accepted_real_macho_helper')
    bad_source=MAIN/'worktrees/vm-018-20261106/artifacts/avf-object-shards/platform-support/execute-001/objects/pexpert/bootargs.o'
    good_source=MAIN/'artifacts/xnu-kernel-firehose-headers/contracts-session2/genuine-provider.o'
    record['inputs']={str(p):sha(p)for p in [bad_source,good_source]}
    target=a.out/'provider.o';shutil.copyfile(bad_source,target)
    command={'id':'firehose/provider','object':str(target)}
    try:m.inspect_object(command,'firehose',helper)
    except ValueError as error:record['ordinary_bad_object_rejected']=str(error)
    else:raise AssertionError('Baseline bad object unexpectedly qualifies')
    replacement=a.out/'native-control-replacement.o';shutil.copyfile(good_source,replacement)
    def parse_then_replace(path,**kwargs):
        genuine=helper.macho(path,**kwargs)
        os.replace(replacement,path)
        return genuine
    metadata=m.inspect_object(command,'firehose',SimpleNamespace(macho=parse_then_replace))
    restore=a.out/'guest-control-restore.o';shutil.copyfile(bad_source,restore);os.replace(restore,target)
    actual=m.object_details(target,helper)
    actual_defs={x['name']for x in actual['symbols']if x['external']and not x['undefined']and not x['type']&224}
    assert metadata['sha256']==sha(target)==sha(bad_source)
    assert '___firehose_buffer_create'in metadata['definitions'] and '___firehose_buffer_create'not in actual_defs
    race_archive=a.out/'race-control.a';race_archive.write_bytes(b'!<arch>\n'+member('provider.o',target.read_bytes()))
    archive_command={'archive':str(race_archive),'members':[str(target)]}
    archive=m.inspect_archive(archive_command,{str(target):metadata})
    record['object_snapshot_counterexample']={'accepted_sha256':metadata['sha256'],'actual_sha256':sha(target),
        'reported_provider_definition':True,'actual_provider_definition':False,
        'archive_accepted_wrong_object_bytes':archive['members']==[{'name':'provider.o','sha256':sha(target)}],
        'method':'Real helper validates/hashes the genuine guest negative-control object, then deterministic pathname replacement occurs before adapter reopen. Restore original guest object before archive inspection. No helper or adapter source bytes changed.'}
    # A second independent exact-member gate probe needs no pathname race.
    genuine=a.out/'genuine.o';shutil.copyfile(good_source,genuine)
    good_meta=m.inspect_object({'id':'firehose/provider','object':str(genuine)},'firehose',helper)
    extra=a.out/'reserved-prefix-extra.a';extra.write_bytes(b'!<arch>\n'+member('genuine.o',genuine.read_bytes())+member('__.SYMDEF_bad',b'foreign non-symbol-table payload'))
    got=m.inspect_archive({'archive':str(extra),'members':[str(genuine)]},{str(genuine):good_meta})
    record['reserved_prefix_member_counterexample']={'accepted_members':got['members'],
        'unreported_member_name':'__.SYMDEF_bad','unreported_member_payload':'foreign non-symbol-table payload',
        'archive_reader_accepts_and_omits_extra':len(got['members'])==1}
    record['outcome']='fail';record['exit_code']=0
except Exception as error:
    record.update(outcome='inconclusive',error=repr(error),exit_code=1)
finally:
    record['finished_at']=datetime.now(timezone.utc).isoformat()
    record['process_memory']=[x for x in Path('/proc/self/status').read_text().splitlines()if x.startswith(('VmRSS:','VmHWM:'))]
    (a.out/'evidence.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record,indent=2))
sys.exit(record['exit_code'])
