#!/usr/bin/env python3
"""Independent exact camera source/provenance and bounded host verification."""
from datetime import datetime,timezone
import hashlib,json,os,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];LAB=ROOT.parents[1];IMPL=LAB/'worktrees/cam-003-20261105';RUNTIME=IMPL/'artifacts/camera-host/host-session4'
RUN=os.environ.get('S24_REVCAM_RUN','20261105-session1');assert re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',RUN)
OUT=ROOT/'artifacts/rev-camera'/RUN;OUT.mkdir(parents=True,exist_ok=False);(OUT/'verifier-executed.py').write_bytes(Path(__file__).read_bytes())
C='b468c6949e70cc75a0264a5dad1fd1d58f7cb4b2';PIN='417484173abc2c4fa93e738ea82ad9f2e84911b1';PREFIX='drivers/media/platform/exynos/camera/';ENV={**os.environ,'GIT_NO_LAZY_FETCH':'1','GIT_OPTIONAL_LOCKS':'0'};commands=[]
def sha(p):
 with Path(p).open('rb') as s:return hashlib.file_digest(s,'sha256').hexdigest()
def run(argv,label,env=ENV):
 with (OUT/(label+'.stdout')).open('wb') as a,(OUT/(label+'.stderr')).open('wb') as b:r=subprocess.run(list(map(str,argv)),cwd=ROOT,stdout=a,stderr=b,env=env,timeout=45)
 commands.append(dict(argv=list(map(str,argv)),cwd=str(ROOT),exit_code=r.returncode,stdout=str((OUT/(label+'.stdout')).relative_to(LAB)),stderr=str((OUT/(label+'.stderr')).relative_to(LAB)),environment_overrides={k:env[k] for k in ['GIT_NO_LAZY_FETCH','GIT_OPTIONAL_LOCKS','ASAN_OPTIONS','UBSAN_OPTIONS'] if k in env}));(OUT/'commands.json').write_text(json.dumps(commands,indent=2)+'\n');assert r.returncode==0,(label,r.returncode)
 return (OUT/(label+'.stdout')).read_bytes()
def block(text,pattern):
 m=re.search(pattern,text);assert m,pattern;start=m.start();brace=text.index('{',start);depth=0
 for token in re.finditer(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|[{}]',text[brace:],re.S):
  if token.group()=='{':depth+=1
  elif token.group()=='}':
   depth-=1
   if depth==0:return text[start:brace+token.end()]
 raise ValueError(pattern)
report=dict(kind='source-review',origin='local-host',outcome='fail',summary='Independent camera source arithmetic/metadata/provenance and ownership review',recorded_at=datetime.now(timezone.utc).isoformat(),commit=C,commands=commands,device_io=False,ISP_executed=False,DMA_mapping=False,native_qualified=False)
try:
 inputs={};names=['README.md','check.py','fixture.c','frame.c','frame.h','layout.cpp','oracle.py','profile.json','source.py']
 for i,f in enumerate(names):
  name='src/platform/camera/host/'+f;p=OUT/'candidate'/f;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(run(['git','show',C+':'+name],'candidate-'+str(i)));inputs[name]=sha(p);assert sha(RUNTIME/'implementation'/f)==sha(p)
 for i,f in enumerate(['README.md','evidence-summary.json']):run(['git','show',C+':docs/procedures/camera-host/'+f],'handoff-'+str(i))
 evidence=json.loads((RUNTIME/'evidence.json').read_text())
 for path,h in evidence['sha256'].items():assert sha(LAB/path)==h,path
 summary=json.loads((OUT/'handoff-1.stdout').read_text())
 for path,h in summary['evidence'].items():assert sha(LAB/path)==h
 records=json.loads((RUNTIME/'source/provenance.json').read_text());source={}
 tree=run(['git','-C',LAB/'references/s24-linux','ls-tree','-r',PIN,'--',*[x['source'] for x in records]],'pinned-tree').decode();blobs={x.split('\t',1)[1]:x.split('\t',1)[0].split()[2] for x in tree.splitlines()}
 for row in records:
  name=row['source'];p=RUNTIME/'source'/name;data=p.read_bytes();assert row['revision']==PIN and sha(p)==row['sha256'];assert hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==blobs[name]
  target=OUT/'sources'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data);source[name]=sha(target)
 # Reuse exact extracted UAPI support declarations, checking their bodies against original source.
 original_uapi=(RUNTIME/'source/include/uapi/linux/videodev2.h').read_text();shim=(RUNTIME/'oracle/linux/videodev2.h').read_text()
 for name in ['enum v4l2_quantization','enum v4l2_colorspace','struct __kernel_v4l2_timeval','struct v4l2_timecode','struct v4l2_buffer']:assert block(original_uapi,r'\b'+name+r'\s*\{') in shim
 (OUT/'linux').mkdir();(OUT/'linux/videodev2.h').write_text(shim)
 metadata=RUNTIME/'source'/PREFIX/'include/v12_0_0/is-metadata-vendor.h';(OUT/'metadata.h').write_bytes(metadata.read_bytes())
 config=(RUNTIME/'source'/PREFIX/'ischain/is-v12_0_0/is-config.h').read_text();definition=re.search(r'^#define\s+CAPTURE_NODE_MAX\s+[^\n]+',config,re.M).group();(OUT/'is-config.h').write_text(definition+'\n')
 types=(RUNTIME/'source'/PREFIX/'include/is-type.h').read_text();formats=(RUNTIME/'source'/PREFIX/'v4l2/format.c').read_text();extract=json.loads((RUNTIME/'oracle/extract.json').read_text())
 common=(RUNTIME/'source'/PREFIX/'include/is-common-enum.h').read_text();macro=re.search(r'^#define\s+IS_MAX_PLANES\s+[^\n]+',common,re.M).group()
 oracle='#include <stddef.h>\n#include "metadata.h"\n'+macro+'\n'
 for name in ['is_frame_cfg','is_fmt','is_crop']:oracle+=block(types,r'\bstruct '+name+r'\s*\{')+';\n'
 oracle+='#define NUM_OF_META_PLANE 1\n#define BITS_PER_BYTE 8\n#define max(a,b) ((a)>(b)?(a):(b))\n#define dbg(...) ((void)0)\n'
 helper_hashes={}
 for helper in ['setup_plane_widths','widths0_sps','widths01_420_sps','widths01_2p_420_sps']:
  actual=block(formats,r'static void '+helper+r'\s*\(');assert hashlib.sha256(actual.encode()).hexdigest()==extract['exact_function_sha256'][helper];helper_hashes[helper]=hashlib.sha256(actual.encode()).hexdigest();oracle+=actual+'\n'
 oracle+='void original_sizes(unsigned kind,uint32_t width,uint32_t height,const uint32_t bpl[2],uint32_t sizes[3]) {\nstruct is_fmt fmt={0};struct is_frame_cfg fc={0};fmt.name="independent source case";fmt.num_planes=kind>=3?3:2;fmt.bitsperpixel[0]=kind?8:16;fmt.bitsperpixel[1]=kind?8:0;fc.format=&fmt;fc.width=width;fc.height=height;fc.bytesperline[0]=bpl[0];fc.bytesperline[1]=bpl[1];if(kind==0)widths0_sps(&fc,sizes);else if(kind<3)widths01_420_sps(&fc,sizes);else widths01_2p_420_sps(&fc,sizes);}\nconst uint64_t measured_metadata[]={sizeof(struct camera2_shot_ext),sizeof(struct camera2_stream),offsetof(struct camera2_shot_ext,shot)};\n'
 (OUT/'original-calculations.c').write_text(oracle);(OUT/'harness.c').write_bytes((ROOT/'docs/reviews/cam-003/harness.c').read_bytes())
 # Read-only native import/provider availability audit; no link or target execution.
 target=Path('/home/egor/Android/Sdk/ndk/28.2.13676358/toolchains/llvm/prebuilt/linux-x86_64/bin');nm=target/'llvm-nm'
 imports=run([nm,'--undefined-only',RUNTIME/'arm64-ios-frame.o'],'macho-imports').decode();symbols={x.split()[-1] for x in imports.splitlines() if x.strip()};assert symbols=={'___stack_chk_fail','___stack_chk_guard','_memcpy','_memset'}
 for path,h in evidence['readonly_provider_graph'].items():assert sha(LAB/path)==h
 checked={}
 for entry in evidence['available_provider_objects']:
  assert entry['symbol'] in symbols and entry['native_link_or_execution_qualified'] is False
  for row in entry['providers']:
   assert sha(LAB/row['source'])==row['source_sha256'] and sha(LAB/row['output'])==row['output_sha256']
   if row['id'] not in checked:checked[row['id']]=run([nm,'--defined-only',LAB/row['output']],'provider-'+row['id'].replace('/','-')).decode()
   assert entry['symbol'] in {x.split()[-1] for x in checked[row['id']].splitlines() if x.strip()}
 cc=Path('/home/egor/.local/bin/clang').resolve();run([cc,'--version'],'compiler')
 run(['/usr/bin/time','-v',cc,'-std=c11','-Wall','-Wextra','-Werror','-O1','-g','-fno-omit-frame-pointer','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I',OUT,'-I',OUT/'candidate',OUT/'harness.c',OUT/'original-calculations.c',OUT/'candidate/frame.c','-o',OUT/'harness'],'compile')
 peak=int(re.search(r'Maximum resident set size \(kbytes\):\s*(\d+)',(OUT/'compile.stderr').read_text())[1]);assert peak<=256*1024
 env={**ENV,'ASAN_OPTIONS':'halt_on_error=1:detect_leaks=1','UBSAN_OPTIONS':'halt_on_error=1'};result=json.loads(run(['/usr/bin/time','-v',OUT/'harness'],'runtime',env))
 report.update(outcome='pass',summary='Independent genuine size/metadata comparisons and overflow/crop/plane/snapshot/Stop ownership assertions passed ASan+UBSan; no actionable host-boundary defect found',source_inputs=inputs,primary_inputs=source,source_pin=PIN,helper_sha256=helper_hashes,result=result,maximum_compiler_RSS_kib=peak,compiler=dict(path=str(cc),sha256=sha(cc)),provider_availability=dict(symbols=sorted(symbols),objects=list(checked),native_link_qualified=False),implementation_capsule=dict(path=str((RUNTIME/'evidence.json').relative_to(LAB)),sha256=sha(RUNTIME/'evidence.json')),checks=[dict(name=x,pass_check=True) for x in ['exact-candidate-runtime-source-bytes','actual-capsule-artifact-and-source-blob-hashes','genuine-calculation-bodies-and-full-metadata-declarations','independent-safe-domain-size-and-overflow-cases','snapshot-stale-Stop-error-timeout-lease-cases','four-actual-MachO-imports-have-current-symbol-witnesses-only','bounded-actual-ASan-UBSan-run']])
except Exception as error:report['error']=repr(error)
report['artifacts']=[str(p.relative_to(LAB)) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='evidence.json'];report['sha256']={str(p.relative_to(LAB)):sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='evidence.json'}
(OUT/'evidence.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(outcome=report['outcome'],error=report.get('error'),commands=len(commands),evidence=str((OUT/'evidence.json').relative_to(LAB)))))
raise SystemExit(report['outcome']!='pass')
