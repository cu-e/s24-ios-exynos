"""Independent frozen PID1 admission audit and bounded copy-only controls."""
import copy, datetime, hashlib, importlib.util, json, os
from pathlib import Path
import struct, subprocess, sys, time

MAIN=Path('/home/egor/dev/pet/s24-ios-exynos')
PROD=MAIN/'worktrees/vm-025-admission-20261106'
HERE=Path(__file__).resolve().parent
TIP='cdcaebaf759d4f4a62a20959fda5bd024ceb203f'
TOOL=PROD/'tools/build/avf_guest_pid1.py'
FIXTURE=PROD/'fixtures/public/avf-guest-pid1/inputs.json'
ENV=dict(os.environ,LC_ALL='C',PYTHONUTF8='1',PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',GIT_NO_LAZY_FETCH='1',GIT_OPTIONAL_LOCKS='0')
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(p,d):p.write_text(json.dumps(d,indent=2)+'\n')
def bounded(p):
 assert p.stat().st_size<=1048576
 with p.open('rb') as f:data=f.read(1048577)
 assert len(data)<=1048576
 return data

def run(out):
 out.mkdir(parents=True,exist_ok=False)
 report={'outcome':'fail','started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'commands':[],'checks':[],'controls':[]}
 def check(name,condition):
  report['checks'].append({'name':name,'pass':bool(condition)})
  assert condition,name
 def git(*args):
  p=subprocess.run(['git',*args],cwd=MAIN,env=ENV,capture_output=True,timeout=15)
  report['commands'].append({'argv':['git',*args],'exit_code':p.returncode,'stdout_sha256':hashlib.sha256(p.stdout).hexdigest(),'stderr_sha256':hashlib.sha256(p.stderr).hexdigest()})
  assert p.returncode==0
  return p.stdout
 try:
  plan=next(x for x in json.loads((MAIN/'state/lab.json').read_text())['experiments'] if x['id']=='REVPID1ADM-001')
  check('prospective registered original owner',plan['status']=='planned' and plan['owner']=='codex-review-boot-inputs-20261106-du')
  report['prospective_plan']=plan
  source_evidence=PROD/'docs/procedures/avf-guest-pid1/admission-002-evidence.json'
  check('exact continuation evidence',sha(source_evidence)=='29c8b44e66d21f6f01987c51f805f5094f290702da83e38240677d13843ac2d5')
  producer=json.loads(bounded(source_evidence));fixture=json.loads(bounded(FIXTURE))
  for rel in ['tools/build/avf_guest_pid1.py','fixtures/public/avf-guest-pid1/inputs.json','docs/procedures/avf-guest-pid1/admission-002-evidence.json']:
   check('exact committed '+rel,hashlib.sha256(git('show',TIP+':'+rel)).hexdigest()==sha(PROD/rel))
  index=PROD/'artifacts/avf-guest-pid1/admission-continuation-1610ed2/artifact-index.json'
  check('continuation artifact index SHA',sha(index)==producer['artifact_index_sha256'])
  rows=json.loads(bounded(index))
  for row in rows:check('preserved artifact '+row['path'],sha(MAIN/row['path'])==row['sha256'])
  report['indexed_artifacts_verified']=len(rows)
  for row in fixture['inputs']:check('fixture pin '+row['path'],sha(MAIN/row['path'])==row['sha256'])
  check('historical compiler hash streamed',sha(Path(fixture['historical_compiler']['path']))==fixture['historical_compiler']['sha256'])
  check('forty plus compiler',len(fixture['inputs'])+1==41)
  report['input_binding_count']=41
  historical={k:{**v,'actual_sha256':sha(MAIN/v['path'])} for k,v in fixture['historical_vm025'].items() if isinstance(v,dict)}
  before={v['path']:sha(MAIN/v['path']) for v in historical.values()}
  procedure=MAIN/plan['procedure'];registered_original=MAIN/'worktrees/vm-025-20261106/docs/procedures/avf-guest-pid1/admission-002.md'
  before[str(registered_original.relative_to(MAIN))]=sha(registered_original)
  for k,v in historical.items():check('frozen physical baseline '+k,v['actual_sha256']==v['sha256'])
  baseline=json.loads(bounded(MAIN/fixture['historical_vm025']['fixture']['path']))
  check('literal historical input prefix',fixture['inputs'][:len(baseline['inputs'])]==baseline['inputs'])
  check('legacy descriptor and empty historical allowlist',fixture['legacy']==baseline['legacy'] and baseline['qualified_candidates']==[])
  candidate_path=MAIN/fixture['candidate_reviews'][0]['candidate_descriptor']['path']
  candidate=json.loads(bounded(candidate_path));endorsement=fixture['candidate_reviews'][0]
  check('singleton exact descriptor allowlist',fixture['qualified_candidates']==[candidate] and endorsement['candidate']==candidate)
  admission=json.loads(bounded(MAIN/endorsement['compiled_admission']['path']))
  review=json.loads(bounded(MAIN/endorsement['review_evidence']['path']))
  raw=json.loads(bounded(MAIN/endorsement['raw_build_evidence']['path']))
  check('exact accepted review and raw candidate',admission['compiled_ABI_review_pass'] is True and admission['candidate']==candidate==raw['candidate'] and review['task']=='REV-026' and review['outcome']=='pass')
  pins={r['path']:r['sha256'] for r in fixture['inputs']}
  check('entire independent review pin map retained',all(pins.get(p)==h for p,h in review['sha256'].items()))
  image=bounded(MAIN/candidate['path']);check('exact actual image',hashlib.sha256(image).hexdigest()=='fac53e7a7799b06e9ced2ef944d079803c49ebbdd60a5f294f92bdd0726775f3')
  header=struct.unpack_from('<8I',image);check('independent actual MachO header',header[:4]==(0xfeedfacf,0x100000c,0,2) and header[6:]==(1,0))
  offset=32;segments=[];thread=None
  for _ in range(header[4]):
   cmd,length=struct.unpack_from('<II',image,offset)
   if cmd==0x19:
    name=image[offset+8:offset+24].split(b'\0')[0].decode();va,vm,fo,fs=struct.unpack_from('<4Q',image,offset+24);segments.append({'name':name,'va':va,'vm':vm,'fileoff':fo,'filesize':fs,'offset':offset})
   if cmd==5:thread=offset;entry=struct.unpack_from('<Q',image,offset+16+32*8)[0]
   offset+=length
  check('independent command table',offset==32+header[5] and thread is not None)
  text=next(x for x in segments if x['name']=='__TEXT');entryfile=text['fileoff']+entry-text['va']
  check('actual entry mapping',text['va']<=entry<text['va']+text['filesize'] and entryfile+4<=len(image))
  report['actual_image_view']={'size':len(image),'entry_hex':hex(entry),'entry_file_offset':entryfile,'segments':segments}
  spec=importlib.util.spec_from_file_location('reviewed_pid1_admission',TOOL);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  module.macho(image)
  def cli(name,expected,desc=candidate_path,fx=FIXTURE,needle=None):
   argv=[sys.executable,'-s',str(TOOL),'--main',str(MAIN),'--fixture',str(fx),'--out',str(out/name)]
   if desc is not None:argv+=['--candidate',str(desc)]
   start=time.monotonic();p=subprocess.run(argv,cwd=HERE,env=ENV,capture_output=True,timeout=15)
   (out/(name+'.stdout.txt')).write_bytes(p.stdout);(out/(name+'.stderr.txt')).write_bytes(p.stderr)
   record=json.loads((out/name/'report.json').read_text())
   good=p.returncode==expected and record['exit_code']==expected and (needle is None or needle in str(record))
   report['commands'].append({'argv':argv,'cwd':str(HERE),'exit_code':p.returncode,'expected_exit':expected,'elapsed_seconds':round(time.monotonic()-start,6),'stdout_sha256':hashlib.sha256(p.stdout).hexdigest(),'stderr_sha256':hashlib.sha256(p.stderr).hexdigest()})
   report['controls'].append({'name':name,'pass':good,'actual_exit':p.returncode,'abi_admission':record.get('abi_admission'),'error':record.get('error'),'memory':record['memory']})
   check('actual CLI '+name,good)
   check('no runtime promotion '+name,not any(record.get(k,False) for k in ['guest_executed','compiler_executed','pid1_observed','native_device_qualified','runtime_syscalls_qualified','stack_signing_console_qualified']))
   return record
  positive=cli('exact-positive',0,needle='compiled-only');check('positive41inputs',len(positive['inputs'])==41)
  cli('legacy-default',2,desc=None,needle='rejected')
  changed=copy.deepcopy(fixture);changed['qualified_candidates'].append(changed['legacy']);p=out/'legacy-listed.json';save(p,changed);cli('legacy-listed',2,desc=None,fx=p,needle='rejected')
  p=out/'descriptor-whitespace.json';p.write_bytes(bounded(candidate_path)+b'\n');cli('descriptor-whitespace',1,desc=p,needle='descriptor bytes changed')
  changed=copy.deepcopy(candidate);changed['extra_field']='not part of reviewed descriptor';p=out/'extra-field.json';save(p,changed);cli('extra-field',2,desc=p,needle='unqualified')
  changed=copy.deepcopy(candidate);source=out/'same-source.c';source.write_bytes(bounded(MAIN/candidate['source_path']));changed['source_path']=str(source.relative_to(MAIN));p=out/'source-alias.json';save(p,changed);cli('source-alias',2,desc=p,needle='unqualified')
  altered=bytearray(image);altered[entryfile:entryfile+4]=b'\x1f\x20\x03\xd5';check('actual instruction changed',altered!=image);module.macho(altered)
  p=out/'changed-instruction';p.write_bytes(altered);changed=copy.deepcopy(candidate);changed['path']=str(p.relative_to(MAIN));changed['sha256']=sha(p);q=out/'changed-image.json';save(q,changed);cli('changed-image',2,desc=q,needle='unqualified')
  changed=copy.deepcopy(fixture);changed['inputs'][0]['role']+=' changed';p=out/'baseline-metadata.json';save(p,changed);cli('baseline-metadata',1,fx=p,needle='baseline was not retained')
  changed=copy.deepcopy(fixture);changed['candidate_reviews'][0]['compiled_admission']['sha256']='0'*64;p=out/'endorsement-substitution.json';save(p,changed);cli('endorsement-substitution',1,fx=p,needle='Unpinned review binding')
  variants={}
  altered=bytearray(image);struct.pack_into('<Q',altered,text['offset']+32,2**64-text['va']);variants['wrapping-vm-extent']=altered
  altered=bytearray(image);struct.pack_into('<I',altered,text['offset']+64,struct.unpack_from('<I',image,text['offset']+64)[0]+1);variants['section-count-mismatch']=altered
  altered=bytearray(image);end=32+header[5];check('duplicate thread copy fits genuine header padding',end+288<=entryfile);altered[end:end+288]=image[thread:thread+288];struct.pack_into('<II',altered,16,header[4]+1,header[5]+288);variants['duplicate-thread-entry']=altered
  report['parser_controls']=[]
  for name,data in variants.items():
   p=out/(name+'.bin');p.write_bytes(data)
   try:module.macho(data)
   except (ValueError,UnicodeError,struct.error) as e:report['parser_controls'].append({'name':name,'outcome':'rejected','reason':str(e),'sha256':sha(p)})
   else:raise AssertionError('Independent parser mutation accepted: '+name)
  after={p:sha(MAIN/p) for p in before};check('physical historical and registered paths unchanged',before==after);report['historical_before_after']={'before':before,'after':after}
  report['outcome']='pass'
 except Exception as error:
  report['error']=repr(error)
 finally:
  report['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();report['memory']=module.hwm() if 'module' in locals() else {};save(out/'report.json',report)
 print(json.dumps({'outcome':report['outcome'],'checks':len(report['checks']),'cli_cases':len(report['controls']),'error':report.get('error'),'memory':report['memory']}))
 return 0 if report['outcome']=='pass' else 1
if __name__=='__main__':raise SystemExit(run(Path(sys.argv[1]).resolve()))
