#!/usr/bin/env python3
"""Reproduce bounded independent SEN-001 review in a fresh local capsule."""
from datetime import datetime, timezone
import hashlib,json,os,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];LAB=ROOT.parents[1]
RUN=os.environ.get('S24_REVSEN_RUN','20261105-session1')
assert re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',RUN)
OUT=ROOT/'artifacts/rev-sensors'/RUN;OUT.mkdir(parents=True,exist_ok=False)
(OUT/'verifier-executed.py').write_bytes(Path(__file__).read_bytes())
PIN='417484173abc2c4fa93e738ea82ad9f2e84911b1';C='f6b20723b1b3c3e1acb39c68af90924956d0d147';D='82c8e9482611ce42f89f2bc923bb9dfa9327609b'
commands=[]
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def run(argv,label,env=None):
 with (OUT/(label+'.stdout')).open('wb') as a,(OUT/(label+'.stderr')).open('wb') as b:
  r=subprocess.run(list(map(str,argv)),cwd=ROOT,stdout=a,stderr=b,env=env,timeout=120)
 commands.append(dict(argv=list(map(str,argv)),cwd=str(ROOT),exit_code=r.returncode,stdout=str((OUT/(label+'.stdout')).relative_to(LAB)),stderr=str((OUT/(label+'.stderr')).relative_to(LAB))))
 (OUT/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
 assert r.returncode==0,(label,r.returncode)
 return (OUT/(label+'.stdout')).read_bytes()
report=dict(kind='source-review',origin='local-host',outcome='fail',recorded_at=datetime.now(timezone.utc).isoformat(),commit=C,documentation_commit=D,commands=commands,source_pin=PIN,device_executed=False,native_device_qualified=False)
try:
 inputs={}
 files=['transport.c','transport.h','README.md','check.py','identities.json','tests/transport_test.c']
 for i,f in enumerate(files):
  name='src/platform/sensors/'+f;p=OUT/'candidate'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(run(['git','show',C+':'+name],'candidate-'+str(i)));inputs[name]=sha(p)
  assert run(['git','show',D+':'+name],'followup-'+str(i))==p.read_bytes()
 run(['git','show',D+':docs/procedures/sen-001/handoff.md'],'handoff-followup')
 capsules=[]
 for session in ['20261105-host-001','20261105-host-002']:
  p=LAB/'worktrees/sen-001-20261105/artifacts/sen-001'/session/'evidence.json';e=json.loads(p.read_text())
  for path,h in e['output_hashes'].items(): assert sha(LAB/path)==h,path
  for command in e['commands']: assert sha(LAB/command['output'])==command['sha256']
  capsules.append(dict(path=str(p.relative_to(LAB)),sha256=sha(p),outcome=e['outcome'],command_exits=[x['exit_code'] for x in e['commands']]))
 final=json.loads((LAB/'worktrees/sen-001-20261105/artifacts/sen-001/20261105-host-002/evidence.json').read_text())
 assert final['commit']==C and final['owned_inputs']==inputs
 source={}
 for i,(name,entry) in enumerate(final['source']['files'].items()):
  data=run(['git','-C',LAB/'references/s24-linux','show',PIN+':'+name],'primary-'+str(i))
  assert hashlib.sha256(data).hexdigest()==entry['sha256']==sha(LAB/entry['artifact'])
  p=OUT/'sources'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);source[name]=sha(p)
 inv=Path(final['inventory']['path']);assert sha(inv)==final['inventory']['sha256']
 ids=json.loads((OUT/'candidate/src/platform/sensors/identities.json').read_text());selected=[]
 for sensor in ids['sensors']:
  line=next(x for x in inv.read_text().splitlines() if x.startswith(sensor['handle']+') '))
  assert line.split(') ',1)[1].split('|')[0].strip()==sensor['name']
  assert re.search(r'type: [^|]*\('+str(sensor['hal_type'])+r'\)',line)
  selected.append(line)
 (OUT/'identity-selected-lines.txt').write_text('\n'.join(selected)+'\n')
 support=OUT/'support';(support/'linux').mkdir(parents=True)
 (support/'linux/types.h').write_text('#pragma once\n#include <stdint.h>\n#include <stdbool.h>\ntypedef uint8_t u8;typedef uint16_t u16;\n#define __packed __attribute__((packed))\n')
 (support/'gnss.h').write_text('/* Empty isolated host dependency; no kernel ABI claim. */\n')
 writer=(OUT/'sources/drivers/soc/samsung/gnssif/gnss_io_device.c').read_text()
 extract=re.search(r'static void exynos_build_header\(.*?\n\}',writer,re.S).group()
 (OUT/'actual-writer.c').write_text('/* Exact pinned source extract, local only. */\n'+extract+'\n')
 (OUT/'harness.c').write_bytes((ROOT/'docs/reviews/sen-001/harness.c').read_bytes())
 cc=Path('/home/egor/.local/bin/clang').resolve();run([cc,'--version'],'compiler-version')
 run([cc,'-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-g','-O1','-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer','-I',support,'-I',OUT/'sources/drivers/soc/samsung/gnssif/include','-I',OUT/'candidate/src/platform/sensors','-I',OUT,OUT/'harness.c',OUT/'candidate/src/platform/sensors/transport.c','-o',OUT/'harness'],'compile-independent')
 env=os.environ.copy();env.update(ASAN_OPTIONS='halt_on_error=1:detect_leaks=1',UBSAN_OPTIONS='halt_on_error=1')
 run(['/usr/bin/time','-v',OUT/'harness'],'run-independent',env)
 report.update(outcome='pass',summary='No actionable defect found within owned packet/clock boundaries; actual GNSS writer and independent atomic-output/extent/timestamp checks passed',owned_inputs=inputs,source_inputs=source,implementation_capsules=capsules,compiler=dict(path=str(cc),sha256=sha(cc)),inventory=dict(path=str(inv.relative_to(LAB)),sha256=sha(inv),checked_entries=len(selected)),checks=[dict(name=n,pass_check=True) for n in ['exact-implementation-and-followup-bytes','actual-failed-and-final-capsule-hashes','18-pinned-primary-source-blobs','seven-exact-original-HAL-identities','independent-SHUB-atomic-clock-capacity-and-guard-cases','genuine-GNSS-writer-versus-contradictory-struct','ASan-UBSan-execution']])
except Exception as error:
 report['error']=str(error)
report['artifacts']=[str(p.relative_to(LAB)) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='evidence.json']
report['sha256']={str(p.relative_to(LAB)):sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='evidence.json'}
(OUT/'evidence.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(dict(outcome=report['outcome'],error=report.get('error'),evidence=str((OUT/'evidence.json').relative_to(LAB)),commands=len(commands))))
raise SystemExit(report['outcome']!='pass')
