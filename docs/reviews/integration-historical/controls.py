#!/usr/bin/env python3
"""Independent real-Git controls, only disposable roots; never publishes."""
import argparse,copy,datetime,hashlib,importlib.util,json,os,resource,subprocess,sys,tempfile,time
from pathlib import Path

START=time.monotonic()
BASE=Path(__file__).resolve().parent
ENV=dict(os.environ,GIT_NO_LAZY_FETCH='1',GIT_OPTIONAL_LOCKS='0',GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='/dev/null',LC_ALL='C',PYTHONUTF8='1',PYTHONNOUSERSITE='1',GIT_AUTHOR_DATE='2001-01-01T00:00:00+00:00',GIT_COMMITTER_DATE='2001-01-01T00:00:00+00:00')
COMMANDS=[]

def git(root,*args,candidate=False):
 env=dict(ENV)
 if candidate:env['GIT_COMMITTER_DATE']='2002-01-01T00:00:00+00:00'
 r=subprocess.run(['git','-c','core.hooksPath=/dev/null','-c','commit.gpgsign=false',*args],cwd=root,env=env,capture_output=True,timeout=15)
 COMMANDS.append({'cwd':str(root),'argv':['git',*args],'exit_code':r.returncode,'stdout':r.stdout.decode(errors='replace'),'stderr':r.stderr.decode(errors='replace')})
 if r.returncode:raise RuntimeError(COMMANDS[-1])
 return r.stdout.decode().strip()

def load(path,name):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 module.ENV=dict(module.ENV,GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='/dev/null')
 return module

def check(value,message):
 if not value:raise AssertionError(message)
 if time.monotonic()-START>180:raise TimeoutError('180-second overall deadline')
 hwm=next(int(s.split()[1])*1024 for s in Path('/proc/self/status').read_text().splitlines() if s.startswith('VmHWM:'))
 if hwm>256*1024**2:raise MemoryError('Controller VmHWM exceeds256MiB')

class Fixture:
 def __init__(self,mode='rename',transient='transient.py'):
  self.temp=tempfile.TemporaryDirectory(prefix='rev030-');self.root=Path(self.temp.name);r=self.root
  (r/'state').mkdir();(r/'artifacts').mkdir()
  (r/'.gitignore').write_text('worktrees/\nartifacts/\nstate/.integration.lock\ntransient.py\nkept.py\nlink\nredirect/\n')
  (r/'source.txt').write_text('base source\n');(r/'state/lab.json').write_text('base ledger\n')
  if mode=='restore' and not (r/transient).exists():(r/transient).parent.mkdir(parents=True,exist_ok=True);(r/transient).write_text('base historical\n')
  git(r,'init','-b','main');git(r,'config','user.name','Independent history review');git(r,'config','user.email','fixture@example.invalid');git(r,'add','.');git(r,'commit','-m','fixture base')
  self.base=git(r,'rev-parse','HEAD');s=r/'worktrees/source';c=r/'worktrees/candidate'
  git(r,'worktree','add','-b','source',str(s));git(r,'worktree','add','-b','candidate',str(c));self.source=s;self.candidate=c
  if mode=='legacy':
   (s/'source.txt').write_text('legacy candidate\n');git(s,'commit','-am','legacy source');sources=[git(s,'rev-parse','HEAD')]
  else:
   target=s/transient;target.parent.mkdir(parents=True,exist_ok=True);target.write_text('transient reviewed bytes\n');(s/'source.txt').write_text('candidate anchor\n')
   git(s,'add','-f','source.txt',transient);git(s,'commit','-m','add or change historical source');sources=[git(s,'rev-parse','HEAD')]
   if mode=='rename':git(s,'mv',transient,'kept.py')
   elif mode=='delete':git(s,'rm',transient)
   elif mode=='restore':
    original=git(r,'show',self.base+':'+transient)+'\n';target.write_text(original);git(s,'add','-f',transient)
   else:raise ValueError(mode)
   git(s,'commit','-m','rename delete or restore historical source');sources.append(git(s,'rev-parse','HEAD'))
  candidates=[]
  for source in sources:git(c,'cherry-pick',source,candidate=True);candidates.append(git(c,'rev-parse','HEAD'))
  self.sources=sources;self.candidates=candidates;self.tip=candidates[-1]
  net=set(filter(None,git(r,'diff','--name-only','--no-renames','-z',self.base,self.tip).split('\0')))
  union=set()
  for commit in candidates:union.update(filter(None,git(r,'diff','--name-only','--no-renames','-z',commit+'^',commit).split('\0')))
  capsule=r/'artifacts/receipt.json';capsule.write_text('{"fixture":"independent"}\n')
  self.plan={'base_head':self.base,'candidate_head':self.tip,'candidate_worktree':'worktrees/candidate','commits':candidates,'commit_map':[{'source':a,'candidate':b} for a,b in zip(sources,candidates)],'paths':sorted(net),'bindings':[{'path':'artifacts/receipt.json','sha256':hashlib.sha256(capsule.read_bytes()).hexdigest()}]}
  self.historical=sorted(union-net);self.union=sorted(union)
 def close(self):self.temp.cleanup()


def audit(module,fixture,plan):
 module.GIT_COMMANDS.clear();before=git(fixture.root,'rev-parse','HEAD');ledger=(fixture.root/'state/lab.json').read_bytes()
 try:
  with module.integration_lock(fixture.root):value=module.audit(fixture.root,plan)
  accepted=True;error=None
 except Exception as exc:accepted=False;error=repr(exc);value=None
 check(git(fixture.root,'rev-parse','HEAD')==before,'Audit changed fixture HEAD')
 check((fixture.root/'state/lab.json').read_bytes()==ledger,'Audit changed fixture ledger')
 return {'accepted':accepted,'error':error,'audit':value,'git_commands':copy.deepcopy(module.GIT_COMMANDS),'source_commits':fixture.sources,'candidate_commits':fixture.candidates,'plan':plan,'independent_union':fixture.union,'independent_historical':fixture.historical}


def main():
 p=argparse.ArgumentParser();p.add_argument('--gate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--baseline-only',action='store_true');args=p.parse_args()
 check(not args.output.exists(),'Fresh report output required')
 module=load(args.gate.resolve(),'reviewed_history_gate');cases=[];result={'kind':'host-test','origin':'local-host','outcome':'fail','recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'argv':[sys.executable,*sys.argv],'gate_path':str(args.gate.resolve()),'gate_sha256':hashlib.file_digest(args.gate.open('rb'),'sha256').hexdigest(),'publication_common_compiler_guest_started':False,'cases':cases}
 def case(name,mode='rename',transient='transient.py',mutate=None,expected=True,historical=True):
  f=Fixture(mode,transient)
  try:
   plan=copy.deepcopy(f.plan)
   if historical:plan['historical_paths']=f.historical
   if mutate:mutate(f,plan)
   record=audit(module,f,plan);record['name']=name;record['expected_acceptance']=expected;record['pass']=record['accepted'] is expected;cases.append(record)
   check(record['pass'],name+': '+str(record['error']))
  finally:f.close()
 try:
  case('legacy omitted historical stays accepted',mode='legacy',historical=False)
  case('legacy explicit empty historical stays accepted',mode='legacy')
  case('transient omitted stays rejected',historical=False,expected=False)
  if args.baseline_only:
   case('baseline cannot admit explicit actual transient',expected=False)
  else:
   case('explicit add then rename source history accepted')
   case('explicit add then delete source history accepted',mode='delete')
   case('explicit changed then restored tracked history accepted',mode='restore',transient='existing.txt')
   case('missing historical declaration rejected',mutate=lambda f,p:p.update(historical_paths=[]),expected=False)
   case('unused historical declaration rejected',mutate=lambda f,p:p['historical_paths'].append('unused.py'),expected=False)
   case('historical/net overlap rejected',mutate=lambda f,p:p['historical_paths'].append(p['paths'][0]),expected=False)
   case('duplicate historical declaration rejected',mutate=lambda f,p:p['historical_paths'].append(p['historical_paths'][0]),expected=False)
   for value in ['./transient.py','transient.py/','a/../transient.py','/tmp/transient.py','', 'a//b.py']:
    case('noncanonical historical rejected '+repr(value),mutate=lambda f,p,v=value:p.update(historical_paths=[v]),expected=False)
   for value in ['state/lab.json','state/.integration.lock','state/.lab.lock','state/board.json','planning/tasks/test.md','BOARD.md','STATUS.md']:
    case('forbidden transient rejected '+value,mode='restore' if value=='state/lab.json' else 'delete',transient=value,expected=False)
   def ignored(f,p):(f.root/'transient.py').write_text('preserve ignored transient data\n')
   case('ignored new historical collision rejected',mutate=ignored,expected=False)
   def dirty(f,p):(f.root/'existing.txt').write_text('preserve dirty historical data\n')
   case('dirty tracked historical collision rejected',mode='restore',transient='existing.txt',mutate=dirty,expected=False)
   def untracked(f,p):(f.root/'notignored.py').write_text('preserve untracked transient data\n')
   case('untracked historical collision rejected',transient='notignored.py',mutate=untracked,expected=False)
   def link(f,p):
    (f.root/'redirect').mkdir();(f.root/'link').symlink_to('redirect',target_is_directory=True)
   case('ignored symlink parent historical rejected',mode='delete',transient='link/missing.py',mutate=link,expected=False)
   def dirtyledger(f,p):(f.root/'state/lab.json').write_text('unrelated live ledger\n')
   case('unrelated dirty ledger preserved with exact historical union',mutate=dirtyledger)
   case('wrong source mapping rejected',mutate=lambda f,p:p['commit_map'][0].update(source=f.base),expected=False)
   def stale(f,p):
    (f.root/'newmain.txt').write_text('new primary commit\n');git(f.root,'add','newmain.txt');git(f.root,'commit','-m','move fixture HEAD')
   case('stale primary HEAD rejected',mutate=stale,expected=False)
   case('missing ordered candidate commit rejected',mutate=lambda f,p:p.update(commits=p['commits'][1:]),expected=False)
   def staged(f,p):
    (f.root/'unrelated.txt').write_text('staged unrelated\n');git(f.root,'add','unrelated.txt')
   case('staged index rejected with historical union',mutate=staged,expected=False)
  result['outcome']='pass'
 except Exception as error:result['error']=repr(error)
 finally:
  status=Path('/proc/self/status').read_text().splitlines();usage={s.split(':')[0]:int(s.split()[1])*1024 for s in status if s.startswith(('VmHWM:','VmRSS:'))}
  result.update(elapsed_seconds=round(time.monotonic()-START,3),current_image_peak_rss_bytes=usage['VmHWM'],current_rss_bytes=usage['VmRSS'],raw_rusage_maxrss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,fixture_git_commands=COMMANDS)
  args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ('cases','fixture_git_commands')}|{'cases':len(cases)}))
 return 0 if result['outcome']=='pass' else 1
if __name__=='__main__':raise SystemExit(main())
