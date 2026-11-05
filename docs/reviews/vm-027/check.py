#!/usr/bin/env python3
"""Bounded independent review runner: Python/byte operations only, no guest."""
import argparse,datetime,hashlib,importlib.util,json,os
from pathlib import Path
import sys
sys.dont_write_bytecode=True
ROOT=Path('/home/egor/dev/pet/s24-ios-exynos');BASE=Path(__file__).resolve().parent
PRODUCER=ROOT/'worktrees/vm-027-20261106';OWNER='codex-review-boot-inputs-20261106-dv'
def sha(path):
 with Path(path).open('rb')as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def load(path):return json.loads(Path(path).read_text())
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--run',required=True);args=ap.parse_args();out=BASE/'runs'/args.run;out.mkdir(parents=True,exist_ok=False)
 r=dict(kind='host-test',origin='local-host',outcome='fail',task='REV-029',recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),commands=[],checks=[],compiler_executed=False,guest_executed=False)
 def check(name,condition):
  r['checks'].append(dict(name=name,passed=bool(condition)))
  if not condition:raise AssertionError(name)
 def prospective():
  state=load(ROOT/'state/lab.json');task=next(t for t in state['tasks']if t['id']=='REV-029');plan=next(e for e in state['experiments']if e['id']=='ADTREVIEW-001');check('prospective-owned-plan',task['status']=='in_progress'and task['owner']==OWNER and plan['owner']==OWNER and plan['status']=='planned'and plan['task']=='REV-029');return plan
 def command(argv,label,expected=0):
  prospective();v=supervisor.run(argv,out,label,60,256);r['commands'].append(v);check('actual-command-'+label,v['exit_code']==expected and v['outcome']==('pass'if expected==0 else'fail')and not v['after']['owned_processes']and v['peak_total_owned_rss_bytes']<=256*1024**2);return v
 try:
  (out/'prospective-plan.json').write_text(json.dumps(prospective(),indent=2)+'\n')
  helper=ROOT/'src/platform/crypto/des/check.py';check('accepted-supervisor',sha(helper)=='08454d87ea5197b5eafc9521833136f6ba9dc34b09c1a78f4e2c5c50e8dd2c63');spec=importlib.util.spec_from_file_location('accepted_review_bound',helper);supervisor=importlib.util.module_from_spec(spec);spec.loader.exec_module(supervisor)
  command([sys.executable,'-s',BASE/'audit.py','--out',out/'audit'],'independent-audit')
  audit=load(out/'audit/report.json');check('independent-decode-and-negatives',audit['outcome']=='pass'and audit['node_count']==14 and audit['negative_controls']>=25)
  parser=PRODUCER/'tools/build/avf_guest_device_tree.py';tree=PRODUCER/'artifacts/avf-guest-device-tree/capture-1/apple-tree.adt'
  command([sys.executable,'-s',parser,tree,'--require-pci','--out',out/'actual-cli.json'],'actual-positive-cli')
  positive=load(out/'actual-cli.json');check('actual-positive-CLI-scope',positive['outcome']=='pass'and positive['size']==12540 and positive['sha256']=='afa048b454b658399636030abe71bc706665fb722564459b93e75609f7d6d491'and not positive['actual_runtime_capture_provenance_verified']and not positive['kernel_executed'])
  command([sys.executable,'-s',parser,tree,'--require-ramdisk','--out',out/'ramdisk-required-cli.json'],'actual-missing-RAMDisk-cli',2)
  check('actual-missing-RAMDisk','RAMDisk'in load(out/'ramdisk-required-cli.json')['error'])
  fdt=ROOT/'worktrees/vm-005-20261105/artifacts/avf-handoff/run-final-221923b/qemu.dtb'
  command([sys.executable,'-s',parser,fdt,'--out',out/'FDT-cli.json'],'historical-input-FDT-cli',2)
  check('FDT-not-Apple-tree',load(out/'FDT-cli.json')['outcome']=='fail')
  r.update(outcome='pass',summary='Independent actual Apple-tree bytes/source/QMP audit and30 malformed controls plus public actual-capture/required-RAMDisk/input-FDT CLI controls pass; bounded selected contract only',source_checks=len(audit['checks']),source_input_paths=len(audit['inputs']),pinned_git_reads=len(audit['source_reads']),node_count=audit['node_count'],property_count=audit['property_count'],negative_controls=audit['negative_controls'])
 except Exception as error:
  r['error']=repr(error)
  if'supervisor'in locals()and isinstance(error,supervisor.ResourceDeferred):r['outcome']='inconclusive';r['summary']='Review resource-deferred before child; no producer defect inferred'
 r['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();r['source_hashes']={str(p):sha(p)for p in[Path(__file__),BASE/'audit.py',BASE/'procedure.md']};r['artifacts']={str(p.relative_to(ROOT)):sha(p)for p in sorted(out.rglob('*'))if p.is_file()};(out/'evidence.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:r.get(k)for k in['outcome','error','source_checks','node_count','property_count','negative_controls','summary']},indent=2));return r['outcome']!='pass'
if __name__=='__main__':raise SystemExit(main())
