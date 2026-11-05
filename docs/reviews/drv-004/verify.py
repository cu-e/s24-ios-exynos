#!/usr/bin/env python3
"""Independent bounded UFS review; all shared inputs are read-only."""
from datetime import datetime,timezone
import hashlib,json,os,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];LAB=ROOT.parents[1]
RUN=os.environ.get('S24_REVUFS_RUN','20261105-session1');assert re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',RUN)
OUT=ROOT/'artifacts/rev-ufs'/RUN;OUT.mkdir(parents=True,exist_ok=False)
(OUT/'verifier-executed.py').write_bytes(Path(__file__).read_bytes())
C='1e0b86c8e5a322c60718006b053739d96a641078';IMPL=LAB/'worktrees/drv-004-20261105';commands=[]
ENV={**os.environ,'GIT_NO_LAZY_FETCH':'1','GIT_OPTIONAL_LOCKS':'0'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(argv,label,env=ENV):
 with (OUT/(label+'.stdout')).open('wb') as a,(OUT/(label+'.stderr')).open('wb') as b:r=subprocess.run(list(map(str,argv)),cwd=ROOT,stdout=a,stderr=b,env=env,timeout=90)
 commands.append(dict(argv=list(map(str,argv)),cwd=str(ROOT),exit_code=r.returncode,stdout=str((OUT/(label+'.stdout')).relative_to(LAB)),stderr=str((OUT/(label+'.stderr')).relative_to(LAB)),environment={k:env[k] for k in ['GIT_NO_LAZY_FETCH','GIT_OPTIONAL_LOCKS','ASAN_OPTIONS','UBSAN_OPTIONS'] if k in env}))
 (OUT/'commands.json').write_text(json.dumps(commands,indent=2)+'\n');assert r.returncode==0,(label,r.returncode)
 return (OUT/(label+'.stdout')).read_bytes()
def declaration(text,name):
 match=re.search(r'^struct '+name+r'\s*\{',text,re.M);assert match,name
 start=match.start();brace=text.index('{',start);depth=0
 for i in range(brace,len(text)):
  depth+=(text[i]=='{')-(text[i]=='}')
  if not depth:return text[start:i+1]+';\n'
 raise ValueError(name)
report=dict(kind='source-review',origin='local-host',outcome='fail',recorded_at=datetime.now(timezone.utc).isoformat(),commit=C,summary='Independent UFS source review and bounded adversarial lifecycle verification',commands=commands,device_executed=False,native_qualified=False)
try:
 inputs={}
 for i,f in enumerate(['host.c','host.h','check.py','fixture.c','source-profile.json','README.md']):
  name='src/platform/storage/ufs/'+f;data=run(['git','show',C+':'+name],'candidate-'+str(i));p=OUT/'candidate'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);inputs[name]=sha(p)
 for i,f in enumerate(['README.md','handoff.md','source-notes.md']):run(['git','show',C+':docs/procedures/ufs-host/'+f],'procedure-'+str(i))
 capsules=[]
 for session in ['final-session2','commit-session1']:
  p=IMPL/'artifacts/ufs-host'/session/'evidence.json';e=json.loads(p.read_text())
  for path,h in e['sha256'].items():assert sha(LAB/path)==h,path
  for path,h in e['source_inputs'].items():assert sha(LAB/path)==h,path
  capsules.append(dict(path=str(p.relative_to(LAB)),sha256=sha(p),outcome=e['outcome'],checks=len(e['checks'])))
 bound=json.loads((IMPL/'artifacts/ufs-host/commit-session1/evidence.json').read_text());assert bound['commit']==C
 runtime=bound['runtime_evidence'];assert sha(LAB/runtime['path'])==runtime['sha256']
 for f in ['host.c','host.h','check.py','fixture.c','source-profile.json']:
  assert sha(IMPL/'artifacts/ufs-host/final-session2/tested-inputs'/f)==inputs['src/platform/storage/ufs/'+f]
 profile=json.loads((OUT/'candidate/src/platform/storage/ufs/source-profile.json').read_text());texts={};primary={}
 for i,item in enumerate(profile['samsung']['sources']):
  name=item['path'];tree=run(['git','-C',LAB/'references/s24-linux','ls-tree',profile['samsung']['commit'],name],'tree-'+str(i));assert tree.split()[2].decode()==item['git_blob']
  source=IMPL/'artifacts/ufs-host/final-session2/primary-inputs'/name;data=source.read_bytes()
  assert sha(source)==item['sha256'];assert hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==item['git_blob']
  p=OUT/'primary-inputs'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);texts[name]=data.decode();primary[name]=sha(p)
 info=profile['donor'];data=run(['git','-C',LAB/'references/s24-port','show',info['commit']+':'+info['path']],'donor-patch');assert hashlib.sha256(data).hexdigest()==info['sha256']
 patch=data.decode();chunk=patch.split('diff --git a/bsd/dev/e1s_ufs.c b/bsd/dev/e1s_ufs.c\n',1)[1].split('\ndiff --git ',1)[0]
 donor='\n'.join(x[1:] for x in chunk.splitlines() if x.startswith('+') and not x.startswith('+++'))+'\n';(OUT/'actual-donor.c').write_text(donor)
 hci=texts['include/ufs/ufshci.h'];ufs=texts['include/ufs/ufs.h'];uapi=texts['include/uapi/scsi/scsi_bsg_ufs.h'];mcq=texts['drivers/ufs/core/ufs-mcq.c']
 # Keep full notices in primary copies; generated declarations are local only.
 layout='''/* Local exact declarations from pinned attributed primary inputs. */
#include <stdint.h>
#include <stddef.h>
#if __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error Little-endian isolated host declaration oracle required
#endif
typedef uint8_t u8;typedef uint16_t __le16,__be16;typedef uint32_t __le32,__be32;typedef uint64_t __le64,u64;
#define UFS_SENSE_SIZE 18
#define E1S_UFS_PRDT_MAX 4
'''
 # Extract complete original enumerations containing command/direction constants.
 for marker in ['ALIGNED_UPIU_SIZE','UTP_NATIVE_UFS_COMMAND','UTP_DEVICE_TO_HOST']:
  pos=hci.index(marker);start=hci.rfind('enum {',0,pos);end=hci.index('};',pos)+2;layout+=hci[start:end]+'\n'
 for text,names in [(hci,['request_desc_header','utp_transfer_req_desc','cq_entry','ufshcd_sg_entry','utp_transfer_cmd_desc']),(uapi,['utp_upiu_header']),(ufs,['utp_cmd_rsp']),(donor,['e1s_prdt','e1s_ucd'])]:
  for name in names:layout+=declaration(text,name)
 layout+='uint32_t actual_tag(uint64_t,uint32_t,uint64_t);\n';(OUT/'source-layout.h').write_text(layout)
 match=re.search(r'static int ufshcd_mcq_get_tag\([^{}]+\{.*?\n\}',mcq,re.S);assert match
 tag='''#include "source-layout.h"
#define GENMASK_ULL(h,l) ((~UINT64_C(0)<<(l))&(~UINT64_C(0)>>(63-(h))))
#define GENMASK(h,l) GENMASK_ULL(h,l)
#define BUILD_BUG_ON(x) _Static_assert(!(x),"genuine alignment")
#define le64_to_cpu(x) (x)
#define div_u64(a,b) ((a)/(b))
struct ufs_hba { uint64_t ucdl_dma_addr;uint32_t stride; };
struct ufs_hw_queue { unsigned unused; };
static unsigned ufshcd_get_ucd_size(struct ufs_hba *h) { return h->stride; }
'''
 tag+=next(x for x in mcq.splitlines() if x.startswith('#define CQE_UCD_BA'))+'\n'+match.group()+'\nuint32_t actual_tag(uint64_t base,uint32_t stride,uint64_t addr) { struct ufs_hba h={base,stride};struct cq_entry q={0};q.command_desc_base_addr=addr;return (uint32_t)ufshcd_mcq_get_tag(&h,0,&q); }\n'
 (OUT/'actual-tag.c').write_text(tag);(OUT/'harness.c').write_bytes((ROOT/'docs/reviews/drv-004/harness.c').read_bytes())
 cc=Path('/home/egor/.local/bin/clang').resolve();run([cc,'--version'],'compiler')
 flags=['-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer']
 run(['/usr/bin/time','-v',cc,*flags,'-I',OUT,'-I',OUT/'candidate/src/platform/storage/ufs',OUT/'harness.c',OUT/'actual-tag.c',OUT/'candidate/src/platform/storage/ufs/host.c','-o',OUT/'harness'],'compile')
 env={**ENV,'ASAN_OPTIONS':'halt_on_error=1:detect_leaks=1','UBSAN_OPTIONS':'halt_on_error=1'}
 run(['/usr/bin/time','-v',OUT/'harness'],'runtime',env)
 report.update(outcome='pass',summary='Independent genuine declaration and lifecycle admission checks passed; documented unpadded-stride and cross-epoch wire-ambiguity counterexamples reproduced, no actionable defect found within stated backend contract',source_inputs=inputs,primary_inputs=primary,source_pins=dict(samsung=profile['samsung']['commit'],donor=info['commit']),implementation_capsules=capsules,compiler=dict(path=str(cc),sha256=sha(cc)),checks=[dict(name=x,pass_check=True) for x in ['exact-candidate-and-runtime-source-binding','actual-capsule-artifact-hashes','primary-tree-blob-and-SHA256-identities','genuine-declaration-descriptor-and-completion-interpretation','independent-stale-error-timeout-lease-cases','read-only-opcode-and-direction-rejection','documented-1088-stride-and-cross-epoch-counterexamples','actual-ASan-UBSan-runtime']])
except Exception as error:report['error']=repr(error)
report['artifacts']=[str(p.relative_to(LAB)) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='evidence.json'];report['sha256']={str(p.relative_to(LAB)):sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='evidence.json'}
(OUT/'evidence.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(outcome=report['outcome'],error=report.get('error'),commands=len(commands),evidence=str((OUT/'evidence.json').relative_to(LAB)))))
raise SystemExit(report['outcome']!='pass')
