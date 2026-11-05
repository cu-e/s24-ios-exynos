"""Non-executing real ELF copy probe for tool-byte binding in runtime snapshots."""
import argparse,hashlib,json,pathlib,shutil,sys
from datetime import datetime,timezone
from types import ModuleType
M=pathlib.Path('/home/egor/dev/pet/s24-ios-exynos')
A=M/'worktrees/vm-036-dz-fix1-20261106'
def sha(p):
    with pathlib.Path(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def imported(path,expected,name):
    body=path.read_bytes();assert hashlib.sha256(body).hexdigest()==expected
    r=ModuleType(name);r.__file__=str(path);exec(compile(body,str(path),'exec'),r.__dict__);return r
p=argparse.ArgumentParser();p.add_argument('--out',type=pathlib.Path,required=True);a=p.parse_args()
r={'kind':'host-test','origin':'local-host','task':'INT-003','experiment':'PLATCOMP-001',
   'recorded_at':datetime.now(timezone.utc).isoformat(),'command':sys.orig_argv,
   'summary':'Non-executing controlled tool-copy integrity counterexample; no real tool or shared input changed.',
   'compiler_or_archiver_or_loader_executed':False,'original_tool_mutated':False}
try:
    mod=imported(A/'tools/build/avf_guest_components.py','5152e733f95da9b0d2a01da6e1eb9b1b22d9bd75bc47187387e19d29e515d718','adapter')
    helper=imported(M/'worktrees/vm-035-20261106/tools/build/avf_kernel_objects.py','5c7b9c549e2740f3fad2a80c060e558dff3c9aa15e98bb2d9a56b33684e687d8','accepted_helper')
    unit=mod.load(M/'worktrees/vm-020-20261106/docs/procedures/avf-guest-firehose/bounded-plan-session1/plan.json','1243849185135bb9ab7f861faf4d8fe2fed0c9dcae1e57165a2e9ff7a86008dc')
    original=M/'artifacts/xnu-macho-tools/macho-session4/prefix/bin/aarch64-apple-darwin-libtool'
    copied=a.out/'archiver-control-copy';shutil.copyfile(original,copied)
    before_sha=sha(copied);assert before_sha=='e9b544277b2194a879a1d186c425d2a1b4620e210b9906a72f0a4a02ba0a8005'
    cache=helper.Digests();before=mod.runtime_snapshot(copied,a.out,unit,helper,cache)
    with copied.open('ab')as f:f.write(b'UNQUALIFIED_TOOL_BYTE_CHANGE')
    after_sha=sha(copied);after=mod.runtime_snapshot(copied,a.out,unit,helper,cache)
    assert before_sha!=after_sha and before==after and str(copied)not in after['candidate_files']
    assert sha(original)==before_sha
    r.update(outcome='fail',exit_code=0,tool_before_sha256=before_sha,tool_after_sha256=after_sha,
             runtime_snapshots_equal=True,actual_tool_binary_missing_from_content_bindings=True,
             original_tool_sha256_after=sha(original),method='Append bytes only to an owned copy of the real qualified ELF libtool. Its ELF dynamic lookup metadata remains identical, so both actual runtime_snapshot calls pass and compare equal despite changed tool bytes. The copy is never executed.')
except Exception as error:r.update(outcome='inconclusive',exit_code=1,error=repr(error))
finally:
    r['process_memory']=[s for s in pathlib.Path('/proc/self/status').read_text().splitlines()if s.startswith(('VmRSS:','VmHWM:'))]
    (a.out/'evidence.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
sys.exit(r['exit_code'])
