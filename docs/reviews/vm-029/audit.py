#!/usr/bin/env python3
"""Independent source/byte/launch review; no native compiler/link/QEMU/common."""
import argparse,copy,datetime,hashlib,importlib.util,json,os,re,resource,signal,subprocess,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
WT=HERE.parents[2]
SUBJECT='5974ab73d5beebb43c170231f4c9533214bf3941'
OWNER='codex-review-boot-gates-20261106-ec'
ENV=dict(os.environ,GIT_NO_LAZY_FETCH='1',GIT_OPTIONAL_LOCKS='0',PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1',LC_ALL='C',PYTHONUTF8='1')
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(p):return json.loads(Path(p).read_text())
def mem():return {x.split(':')[0]:int(x.split()[1])*1024 for x in Path('/proc/self/status').read_text().splitlines()if x.startswith(('VmRSS:','VmHWM:'))}
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--main',type=Path,required=True);p.add_argument('--run',required=True);a=p.parse_args();m=a.main.resolve();producer=m/'worktrees/vm-029-20261106'
 if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]*',a.run):raise ValueError('fresh simple run name')
 out=HERE/'artifacts'/a.run;out.mkdir(parents=True,exist_ok=False);(out/'auditor.py').write_bytes(Path(__file__).read_bytes());resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,256*1024**2))
 r={'task':'REV-033','kind':'host-test','origin':'local-host','outcome':'fail','recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'summary':'Independent exact VM029 timer/IRQ source, byte provenance and narrow launch predicate review; no runtime interrupt qualification.','subject_commit':SUBJECT,'owner':OWNER,'commands':[],'checks':[],'launch_cases':[],'native_compiler_started':False,'linker_started':False,'qemu_started':False,'common_tests_started':False,'timer_irq_observed':False,'phone_accessed':False,'memory_start':mem()}
 def check(n,ok,**d):
  r['checks'].append(dict(name=n,passed=bool(ok),**d))
  if not ok:raise ValueError(n)
 def command(argv,label,expected=0,seconds=30):
  start=time.monotonic();stdout=out/(label+'.stdout');stderr=out/(label+'.stderr')
  with stdout.open('xb')as so,stderr.open('xb')as se:
   child=subprocess.Popen([str(x)for x in argv],stdout=so,stderr=se,cwd=WT,env=ENV,start_new_session=True)
   try:exit_code=child.wait(timeout=seconds)
   except subprocess.TimeoutExpired:
    os.killpg(child.pid,signal.SIGTERM)
    try:child.wait(timeout=2)
    except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=2)
    raise
  v={'argv':[str(x)for x in argv],'exit_code':exit_code,'expected_exit_code':expected,'pid':child.pid,'elapsed_seconds':time.monotonic()-start,'timeout_seconds':seconds,'stdout':str(stdout.relative_to(m)),'stderr':str(stderr.relative_to(m))};r['commands'].append(v);check('command-'+label,exit_code==expected);return stdout.read_bytes()
 try:
  state=load(m/'state/lab.json');t=next(x for x in state['tasks']if x['id']=='REV-033');e=next(x for x in state['experiments']if x['id']=='REV033-001');check('owned-planned-review',t['owner']==e['owner']==OWNER and t['status']=='in_progress' and e['status']=='planned' and e['task']=='REV-033');r['planning_record']=e
  r['producer_sources']={}
  paths=['tools/build/avf_guest_timer_irq.py','fixtures/public/avf-guest-timer-irq/check.py','fixtures/public/avf-guest-timer-irq/inputs.json','fixtures/public/avf-guest-timer-irq/launch.json','docs/procedures/avf-guest-timer-irq/README.md','docs/procedures/avf-guest-timer-irq/evidence.json']
  for i,path in enumerate(paths):
   raw=command(['git','-C',m,'show',SUBJECT+':'+path],'git-source-'+str(i));check('exact-frozen-producer-'+path,raw==(producer/path).read_bytes());r['producer_sources'][path]=sha(producer/path)
  evidence=load(producer/paths[-1]);r['producer_evidence_sha256']=sha(producer/paths[-1]);check('bounded-producer-claims',evidence['outcome']=='pass' and all(evidence['operations'][x]is False for x in ['compiler_started','qemu_started','guest_executed','timer_irq_observed','phone_accessed']))
  for path,digest in evidence['sha256'].items():check('retained-producer-artifact-'+path,sha(m/path)==digest)
  r['preserved_producer_failures']=evidence['preserved_failures'];r['producer_artifacts_checked']=len(evidence['sha256'])
  pin=load(producer/'fixtures/public/avf-guest-timer-irq/inputs.json');r['pin']=pin;r['verified_inputs']={}
  for name,item in pin['files'].items():
   path=m/item['path'];check('exact-declared-input-'+name,path.is_file() and not path.is_symlink() and path.stat().st_size==item['size'] and sha(path)==item['sha256']);r['verified_inputs'][name]={'path':item['path'],'sha256':sha(path),'size':path.stat().st_size}
  check('actual19-inputs',len(r['verified_inputs'])==19)
  graph=load(m/pin['files']['object_manifest']['path']);recipes=[]
  for ident in ['osfmk/gic_v3_irq.o','osfmk/machine_routines.o','osfmk/arm_init.o','osfmk/rtclock.o']:
   rows=[x for x in graph if x['id']==ident];check('single-selected-recipe-'+ident,len(rows)==1);row=rows[0];argv=row['next_owned_compile_argv_template'];boards=[x for x in argv if x.startswith('-DARM64_BOARD_CONFIG_')];check('actual-board-source-config-'+ident,boards==['-DARM64_BOARD_CONFIG_BCM2837'] and sha(row['bound_source'])==row['bound_source_sha256'] and sha(row['configuration'])==row['configuration_sha256']);recipes.append({'id':ident,'source':row['bound_source'],'source_sha256':row['bound_source_sha256'],'configuration_sha256':row['configuration_sha256'],'board_defines':boards})
  del graph;r['selected_recipes']=recipes
  texts={name:(m/item['path']).read_text()for name,item in pin['files'].items()if item.get('text')};gic=texts['guest_gic'];qemu=texts['qemu_virt'];shim=texts['shim']
  init=gic[gic.index('\ngic_v3_irq_cpu_init(void)\n{'):];handler=gic[gic.index('\ngic_irq_handler('):gic.index('\nvoid\ngic_v3_irq_quiesce(')]
  check('PPI27-three-real-source-definitions',bool(re.search(r'^#define GIC_INTID_VTIMER\s+27\b',gic,re.M)) and bool(re.search(r'^#define ARCH_TIMER_VIRT_IRQ\s+27\b',texts['qemu_bsa'],re.M)) and 'm.vtimer_intid = 16 + num;'in shim)
  check('actual-handler-IAR-dispatch-EOI',handler.index('__builtin_arm_rsr64("ICC_IAR1_EL1")')<handler.index('intid == GIC_INTID_VTIMER')<handler.index('rtclock_intr(TRUE)')<handler.index('__builtin_arm_wsr64("ICC_EOIR1_EL1", iar)'))
  check('GIC-system-register-enable-before-handler',init.index('"ICC_SRE_EL1"')<init.index('gic_find_redistributor()')<init.index('GICR_ISENABLER0')<init.index('"ICC_IGRPEN1_EL1"')<init.index('ml_install_interrupt_handler'))
  arm=texts['guest_arm_init'];boot=arm[arm.index('\narm_init(\n'):arm.index('\narm_init_cpu(\n')];secondary=arm[arm.index('\narm_init_cpu(\n'):];check('boot-and-secondary-GIC-before-timer',all(x.index('PE_init_cpu();')<x.index('fiq_context_init(TRUE);')for x in [boot,secondary]));check('PE-CPU-hook-to-generic-GIC','pe_init_fiq();'in texts['guest_identify'] and '#elif defined(GENERIC_GIC_V3_IRQ)'in texts['guest_fiq'] and 'gic_v3_irq_cpu_init();'in texts['guest_fiq'])
  check('physical-MMIO-offset-roundtrip',0x100+(0x08000000-0x100)==0x08000000 and 0x100+(0x080a0000-0x100)==0x080a0000 and 'm.gicd - io_base'in shim and 'm.gicr - io_base'in shim and 'soc_base + reg[0]'in init and 'soc_base + reg[2]'in init)
  check('real-controller-total288','"num-irq", NUM_IRQS + 32'in qemu and '#define NUM_IRQS 256'in qemu);check('single-CPU-redist-frame-fit',0x20000<=0x00f60000)
  psci_path=m/'worktrees/vm-008-20261105/artifacts/avf-kernel-headers/prepare-2/source/xnu/osfmk/arm64/psci_smp.c';psci=psci_path.read_text();r['extra_PSCI_source']={'path':str(psci_path.relative_to(m)),'sha256':sha(psci_path),'size':psci_path.stat().st_size};check('source-only-default-HVC-intersection','vms->secure = false;'in qemu and 'vms->virt = false;'in qemu and 'vms->psci_conduit = QEMU_PSCI_CONDUIT_HVC;'in qemu and 'dt_prop_str(&w, "psci-method", m.psci_hvc ? "hvc" : "smc")'in shim and 'strncmp((const char *)prop, "hvc", 3) == 0'in psci)
  spec=importlib.util.spec_from_file_location('exact_review_subject',producer/'tools/build/avf_guest_timer_irq.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);facts=dict(evidence['facts']);launch=load(producer/'fixtures/public/avf-guest-timer-irq/launch.json')
  check('source-derived-intersection',facts['spi_min']==32 and facts['guest_spi_max']==1019 and facts['guest_spi_slots']==48 and facts['qemu_spi_max']==287 and facts['virtual_timer_intid']==27)
  def model(x):
   fixed={'machine':'virt,gic-version=3','accel':'tcg','cpu':'cortex-a76','smp':1,'memory_mib':256,'dt_format':'shim-converted-Apple-DT','virtual_timer_intid':27,'gicd':[0x8000000,0x10000],'gicr':[0x80a0000,0xf60000]}
   if type(x)is not dict or set(x)!=set(fixed)|{'required_spi_intids'}:return False
   if any(type(x[k])is not type(v)or x[k]!=v for k,v in fixed.items()):return False
   irqs=x['required_spi_intids']
   return type(irqs)is list and len(irqs)<=48 and all(type(n)is int and 32<=n<=287 for n in irqs)and len(irqs)==len(set(irqs))
  cases=[('base',launch),('first-SPI',dict(launch,required_spi_intids=[32])),('last-SPI',dict(launch,required_spi_intids=[287])),('max48',dict(launch,required_spi_intids=list(range(32,80))))]
  for v in [[31],[288],[1019],[1020],[-1],[2**64],[True],[False],[32.0],['32'],[None],[[32]],[{'id':32}],[32,32],list(range(32,81)),None,{},'32',32]:cases.append(('SPI-shape-'+repr(v),dict(launch,required_spi_intids=v)))
  for key,value in [('machine','virt,gic-version=2'),('accel','kvm'),('cpu','max'),('smp',2),('smp',True),('memory_mib',256.0),('virtual_timer_intid',27.0),('virtual_timer_intid',30),('gicd',[0x8000000,0x10001]),('gicr',[0x80a0000,0x10000]),('dt_format','raw-FDT')]:cases.append(('field-'+key+'-'+repr(value),dict(launch,**{key:value})))
  cases.extend([('missing-SPI', {k:v for k,v in launch.items()if k!='required_spi_intids'}),('extra-key',dict(launch,unsafe=True)),('scalar',3),('list',[])])
  for name,case in cases:
   expected=model(case);error=None
   try:mod.validate_launch(case,facts);actual=True
   except (ValueError,TypeError,KeyError)as exc:actual=False;error=type(exc).__name__+': '+str(exc)
   r['launch_cases'].append({'name':name,'value':case,'expected':expected,'accepted':actual,'error':error});check('independent-launch-model-'+name,actual==expected)
  for label,lp,expected,diagnostic in [('actual-boundary287',dict(launch,required_spi_intids=[287]),0,None),('actual-boundary288',dict(launch,required_spi_intids=[288]),2,'SPI outside actual QEMU controller range: 288')]:
   launch_path=out/(label+'.json');launch_path.write_text(json.dumps(lp)+'\n');destination=out/label;command([sys.executable,'-s',producer/'tools/build/avf_guest_timer_irq.py','--main',m,'--out',destination,'--launch',launch_path],label,expected);result=load(destination/'report.json');check('real-CLI-diagnostic-'+label,result['exit_code']==expected and (diagnostic is None or result.get('error')==diagnostic) and result['timer_irq_observed']is False and result['compiler_started']is False and result['qemu_started']is False)
  qemu_copy=out/'real-virt-NUM_IRQS128.c';raw=texts['qemu_virt'];changed=raw.replace('#define NUM_IRQS 256','#define NUM_IRQS 128');check('unique-real-source-mutation',raw.count('#define NUM_IRQS 256')==1 and changed!=raw);qemu_copy.write_text(changed);descriptor=copy.deepcopy(pin);descriptor['files']['qemu_virt'].update(path=str(qemu_copy),size=qemu_copy.stat().st_size,sha256=sha(qemu_copy));dp=out/'re-pinned-controller128.json';dp.write_text(json.dumps(descriptor)+'\n');lp=out/'source-semantic-launch160.json';lp.write_text(json.dumps(dict(launch,required_spi_intids=[160]))+'\n');destination=out/'source-semantic-controller128';command([sys.executable,'-s',producer/'tools/build/avf_guest_timer_irq.py','--main',m,'--out',destination,'--inputs',dp,'--launch',lp],'source-semantic-controller128',2);result=load(destination/'report.json');check('re-pinned-real-controller-semantic-rejection',result.get('error')=='SPI outside actual QEMU controller range: 160' and result['facts']['qemu_spi_max']==159)
  r['limits']=['Source/token and declarative launch inspection, not C preprocessing or a complete QEMU argv validator','No compiler/link/QEMU/common/phone operation; no timer frequency, IRQ delivery/rearm/EOI or XNU boot observation','Default one-CPU HVC source intersection only; no SMP/PSCI runtime result','Guest wait loops remain unbounded at source level; later separately leased runtime needs finite external supervisor'];r['outcome']='pass'
 except Exception as exc:r['error']=repr(exc)
 finally:
  r['memory_end']=mem();r['artifacts']=[str(x.relative_to(m))for x in out.rglob('*')if x.is_file()];r['sha256']={str(x.relative_to(m)):sha(x)for x in out.rglob('*')if x.is_file()};(out/'evidence.json').write_text(json.dumps(r,indent=2)+'\n')
 print(json.dumps({k:r.get(k)for k in ['outcome','error','memory_end']},indent=2));return 0 if r['outcome']=='pass'else 1
if __name__=='__main__':raise SystemExit(main())
