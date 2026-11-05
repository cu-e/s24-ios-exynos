"""Independent bounded replay of the three real P2s on the isolated correction."""
import argparse,ast,errno,hashlib,json,os,pathlib,shutil,sys
from datetime import datetime,timezone
from types import ModuleType,SimpleNamespace
M=pathlib.Path('/home/egor/dev/pet/s24-ios-exynos');A=M/'worktrees/vm-036-dz-fix2-20261106'
def sha(p):
    with pathlib.Path(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def imported(path,expected,name):
    data=path.read_bytes();assert hashlib.sha256(data).hexdigest()==expected
    r=ModuleType(name);r.__file__=str(path);exec(compile(data,str(path),'exec'),r.__dict__);return r
def member(name,body):
    label=(name+'/').ljust(16);assert len(label)==16
    return (label+'0'.ljust(12)+'0'.ljust(6)+'0'.ljust(6)+'100644'.ljust(8)+str(len(body)).ljust(10)+'`\n').encode()+body+(b'\n'if len(body)%2 else b'')
p=argparse.ArgumentParser();p.add_argument('--out',type=pathlib.Path,required=True);a=p.parse_args()
r={'kind':'host-test','origin':'local-host','task':'INT-003','experiment':'PLATCOMP-002',
   'recorded_at':datetime.now(timezone.utc).isoformat(),'command':sys.orig_argv,'checks':[],
   'summary':'Independent source-only P2 regression check; historical objects/archives are parser controls, never new guest proof.',
   'compiler_archiver_loader_or_guest_executed':False,'original_inputs_mutated':False}
def yes(name,value):
    r['checks'].append({'name':name,'pass':bool(value)})
    if not value:raise AssertionError(name)
def reject(name,fn):
    try:fn()
    except (ValueError,OSError)as error:r['checks'].append({'name':name,'pass':True,'actual_rejection':str(error)})
    else:raise AssertionError('Still admitted '+name)
try:
    m=imported(A/'tools/build/avf_guest_components.py','3ae89e8a19f239a762580b818ab45602721257a528ecf6f9b7a3db54e1735c4f','corrected')
    h=imported(M/'worktrees/vm-035-20261106/tools/build/avf_kernel_objects.py','5c7b9c549e2740f3fad2a80c060e558dff3c9aa15e98bb2d9a56b33684e687d8','real_helper')
    old=M/'worktrees/vm-036-dz-fix1-20261106/tools/build/avf_guest_components.py'
    def funcs(path):return {x.name:ast.dump(x,include_attributes=False)for x in ast.parse(path.read_text()).body if isinstance(x,(ast.FunctionDef,ast.ClassDef))}
    before,after=funcs(old),funcs(pathlib.Path(m.__file__))
    yes('only six old boundaries change; all authority/quarantine/process/recipe/dependency code retained',
        {n for n in before if before[n]!=after.get(n)}=={'elf','runtime_snapshot','object_details','inspect_object','archive_members','inspect_archive'})
    yes('old5152 physical source unchanged',sha(old)=='5152e733f95da9b0d2a01da6e1eb9b1b22d9bd75bc47187387e19d29e515d718')
    yes('process remains explicitly quarantined',m.load(m.POLICY,m.POLICY_SHA256)['prospective_process']['independently_accepted']is False)
    guest=M/'worktrees/vm-018-20261106/artifacts/avf-object-shards/platform-support/execute-001/objects/pexpert/bootargs.o'
    native=M/'artifacts/xnu-kernel-firehose-headers/contracts-session2/genuine-provider.o'
    layout=M/'artifacts/xnu-kernel-firehose-headers/contracts-session2/provider-layout.o'
    cctools=M/'artifacts/xnu-macho-tools/macho-session4/fixtures/libfixture.a'
    tool=M/'artifacts/xnu-macho-tools/macho-session4/prefix/bin/aarch64-apple-darwin-libtool'
    r['historical_inputs']={str(x):sha(x)for x in [guest,native,layout,cctools,tool]}
    target=a.out/'provider.o';swap=a.out/'swap.o';cmd={'id':'firehose/provider','object':str(target)}
    shutil.copyfile(guest,target);shutil.copyfile(native,swap);calls=[]
    def swap_after_actual_helper(path,**kwargs):
        result=h.macho(path,**kwargs);calls.append(str(path));os.replace(swap,target);return result
    reject('original P2-1 cannot borrow replacement provider symbols',lambda:m.inspect_object(cmd,'firehose',SimpleNamespace(macho=swap_after_actual_helper)))
    yes('real replacement happened while helper saw only captured fd',len(calls)==1 and calls[0].startswith('/proc/self/fd/')and sha(target)==sha(native))
    shutil.copyfile(native,target);shutil.copyfile(guest,swap)
    captured=m.inspect_object(cmd,'firehose',SimpleNamespace(macho=swap_after_actual_helper))
    yes('valid metadata and digest both from one immutable original snapshot',captured['sha256']==sha(native) and captured['snapshot_sealed'] and sha(target)==sha(guest))
    arc=a.out/'race.a';arc.write_bytes(b'!<arch>\n'+member('provider.o',target.read_bytes()))
    reject('original P2-1 archive continuation cannot authorize restored bad bytes',lambda:m.inspect_archive({'archive':str(arc),'members':[str(target)]},{str(target):captured}))
    shutil.copyfile(native,target);denials=[]
    def attempted_snapshot_write(path,**kwargs):
        try:os.pwrite(int(pathlib.Path(path).name),b'X',0)
        except OSError as error:
            if error.errno!=errno.EPERM:raise
            denials.append(error.errno)
        else:raise AssertionError('Snapshot writable')
        return h.macho(path,**kwargs)
    m.object_details(target,SimpleNamespace(macho=attempted_snapshot_write));yes('actual memfd is sealed against writes',denials==[errno.EPERM])
    shutil.copyfile(layout,target);shutil.copyfile(guest,swap)
    probe=m.object_details(target,SimpleNamespace(macho=swap_after_actual_helper));original_probe=m.object_details(layout,h)
    yes('probe payload stays in same captured snapshot',probe['sha256']==sha(layout) and probe['sections']==original_probe['sections']and any('captured_data_hex'in s for s in probe['sections']))
    # Repeat the exact hidden-member counterexample, without executing ar/libtool.
    shutil.copyfile(native,target);good=m.inspect_object(cmd,'firehose',h)
    arc.write_bytes(b'!<arch>\n'+member('provider.o',target.read_bytes())+member('__.SYMDEF_bad',b'foreign non-symbol-table payload'))
    reject('original P2-2 extraordinary reserved prefix is rejected',lambda:m.inspect_archive({'archive':str(arc),'members':[str(target)]},{str(target):good}))
    real=m.archive_members(cctools,True);yes('actual selected cctools format remains readable',bool(real['members'])and real['toc_name']in m.TOC_NAMES)
    r['actual_cctools_format_control']={'path':str(cctools),'sha256':sha(cctools),'parsed':real}
    for extent in ['-1','0','+1','999999']:
        label=('#1/'+extent).ljust(16);arc.write_bytes(b'!<arch>\n'+(label+'0'.ljust(12)+'0'.ljust(6)+'0'.ljust(6)+'100644'.ljust(8)+'4'.ljust(10)+'`\n').encode()+b'tiny')
        reject('invalid BSD name extent '+extent,lambda:m.archive_members(arc))
    unit=m.load(M/'worktrees/vm-020-20261106/docs/procedures/avf-guest-firehose/bounded-plan-session1/plan.json','1243849185135bb9ab7f861faf4d8fe2fed0c9dcae1e57165a2e9ff7a86008dc')
    copy=a.out/'archiver-copy';shutil.copyfile(tool,copy);cache=h.Digests();rt=m.runtime_snapshot(copy,a.out,unit,h,cache)
    yes('actual executable bytes and stable identity now bound',rt['executable']['sha256']==sha(copy)and str(copy)in rt['host_file_bindings']and len(rt['executable']['identity'])==5)
    with copy.open('ab')as f:f.write(b'UNQUALIFIED_TOOL_BYTE_CHANGE')
    reject('original P2-3 tool append rejected',lambda:m.runtime_snapshot(copy,a.out,unit,h,cache))
    shutil.copyfile(tool,copy);changed=m.runtime_snapshot(copy,a.out,unit,h,cache)
    yes('same-content rewrite is not same runtime identity',changed!=rt and changed['executable']['sha256']==rt['executable']['sha256'])
    swap.write_bytes(copy.read_bytes()+b'change');actual_elf=m.elf
    def elf_then_swap(path,stream=None):
        facts=actual_elf(path,stream)
        if pathlib.Path(path)==copy:os.replace(swap,copy)
        return facts
    m.elf=elf_then_swap
    try:reject('same-fd ELF parse/path identity replacement rejected',lambda:m.runtime_snapshot(copy,a.out,unit,h,cache))
    finally:m.elf=actual_elf
    yes('all original inputs untouched',all(sha(path)==digest for path,digest in r['historical_inputs'].items()))
    yes('corrected source still exact frozen bytes',sha(pathlib.Path(m.__file__))=='3ae89e8a19f239a762580b818ab45602721257a528ecf6f9b7a3db54e1735c4f')
    r.update(outcome='pass',exit_code=0,summary='All three original independent P2 counterexamples reject; immutable snapshots, actual cctools format and unchanged quarantine verified. No actual execution adoption.')
except Exception as error:r.update(outcome='fail',exit_code=1,error=repr(error))
finally:
    r['finished_at']=datetime.now(timezone.utc).isoformat();r['process_memory']=[s for s in pathlib.Path('/proc/self/status').read_text().splitlines()if s.startswith(('VmRSS:','VmHWM:'))]
    (a.out/'evidence.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'outcome':r['outcome'],'checks':len(r['checks']),'error':r.get('error')}))
sys.exit(r['exit_code'])
