#!/usr/bin/env python3
"""Source-qualified read-only power input evidence; never accesses hardware."""
from datetime import datetime,timezone
import argparse,hashlib,json,os,re,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent

def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def extract(text,pattern):
    match=re.search(pattern,text)
    if not match:raise ValueError('Genuine declaration/function missing: '+pattern)
    brace=text.index('{',match.start());depth=0
    for i in range(brace,len(text)):
        depth+=(text[i]=='{')-(text[i]=='}')
        if depth==0:return text[match.start():i+1]
    raise ValueError('Incomplete genuine declaration')

def definitions(text,names):
    value=[]
    for name in names:
        found=[line for line in text.splitlines() if re.match(r'#define\s+'+name+r'\s',line)]
        if len(found)!=1:raise ValueError('Genuine macro missing/ambiguous: '+name)
        value+=found
    return '\n'.join(value)+'\n'

def oracle(texts,donor):
    tmu=texts['drivers/thermal/samsung/exynos_acpm_tmu.h'];tmu_c=texts['drivers/thermal/samsung/exynos_acpm_tmu.c']
    dvfs=texts['drivers/soc/samsung/cal-if/acpm_dvfs.c'];domain=texts['drivers/soc/samsung/cal-if/s5e9945/acpm_dvfs_s5e9945.h']
    fw=texts['drivers/soc/samsung/acpm/fw_header/framework.h'];fv=texts['include/soc/samsung/fvmap.h']
    qos=texts['include/soc/samsung/exynos_pm_qos.h']
    prototype=re.search(r'extern void exynos_pm_qos_update_request_nosync\([^;]+;',qos)
    if not prototype:raise ValueError('Genuine QoS target prototype unavailable')
    value='/* GENERATED HOST ORACLE. Complete original inputs/notices retained. No real transport or policy callback. */\n'
    value+=tmu.split('#ifndef',1)[0]+tmu_c.split('#include',1)[0]+fw.split('#ifndef',1)[0]+qos.split('#ifndef',1)[0]
    value+='''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#if __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error Genuine native-layout oracle requires a little-endian host
#endif
typedef uint8_t u8;typedef int8_t s8;typedef uint16_t u16;typedef uint32_t u32;typedef int32_t s32;
#define CONFIG_SOC_S5E9945 1
#define CONFIG_EXYNOS_ACPM 1
#define pr_info(...) ((void)0)
#define pr_debug(...) ((void)0)
'''
    value+=definitions(tmu,['TMU_IPC_READ_TEMP'])
    value+=definitions(texts['drivers/thermal/samsung/exynos_tmu.h'],['MCELSIUS'])
    value+=definitions(texts['drivers/soc/samsung/cal-if/cmucal.h'],['ACPM_VCLK_TYPE'])
    value+=definitions(fv,['BLOCK_ADDR_SIZE','CHILD_ID_NUM'])
    value+='#define SZ_8K (8U*1024U) /* host replacement for Linux size constant */\n'
    value+=definitions(texts['drivers/soc/samsung/cal-if/fvmap.c'],['FVMAP_SIZE','STEP_UV'])
    value+=definitions(donor,['E1S_ACPM_CMD_WORDS','E1S_ACPM_CHANNEL_STRIDE'])
    value+=definitions(qos,['EXYNOS_PM_QOS_DEFAULT_VALUE'])
    for text,names in [(tmu,['tmu_ipc_request','tmu_ipc_sync_data','tmu_ipc_response']),
            (fw,['channel_info','ipc_channel']),(fv,['fvmap_header','rate_volt'])]:
        for name in names:value+=extract(text,r'struct\s+'+name+r'\s*\{')+';\n'
    value+=extract(tmu,r'union tmu_ipc_message\s*\{')+';\n'
    value+=extract(domain,r'enum acpm_dvfs_id\s*\{')+';\n'
    value+='struct vclk { unsigned id; };\n#define CMUCAL_ACPM_VCLK(id,a,b,c,d,margin,cpu) {id}\n'
    value+=extract(domain,r'struct vclk acpm_vclk_list\[\]\s*=\s*\{')+';\n'
    value+='''
_Static_assert(sizeof(union tmu_ipc_message)==16 && sizeof(struct tmu_ipc_response)==16,"TMU size");
_Static_assert(offsetof(struct tmu_ipc_response,type)==4 && offsetof(struct tmu_ipc_response,ret)==5,"TMU type/return");
_Static_assert(offsetof(struct tmu_ipc_response,tzid)==6 && offsetof(struct tmu_ipc_response,temp)==7 && offsetof(struct tmu_ipc_response,stat)==8,"TMU zone/temp/status");
_Static_assert(sizeof(struct channel_info)==32 && sizeof(struct ipc_channel)==E1S_ACPM_CHANNEL_STRIDE,"Samsung/E1S channel stride");
_Static_assert(offsetof(struct ipc_channel,ch)==12 && offsetof(struct ipc_channel,ap_poll)==44,"ACPM channel offsets");
_Static_assert(E1S_ACPM_CMD_WORDS*4==16 && MCELSIUS==1000,"Source units");
_Static_assert(sizeof(struct fvmap_header)==52 && offsetof(struct fvmap_header,o_ratevolt)==20,"FVMAP header/offset");
_Static_assert(sizeof(struct rate_volt)==4 && CHILD_ID_NUM==12,"FVMAP entry size");
_Static_assert(FVMAP_SIZE==8192 && STEP_UV==6250,"FVMAP copy size/encoded voltage units, never a safety limit");
_Static_assert(EXYNOS_PM_QOS_DEFAULT_VALUE==-1,"QoS sentinel is not a frequency");
struct exynos_pm_qos_request { unsigned id; }; /* Host capture context only. */
'''+prototype[0]+'''
static bool acpm_tmu_test_mode,acpm_tmu_log;
static union tmu_ipc_message supplied;
static void exynos_acpm_tmu_ipc_send_data(union tmu_ipc_message *message) {
    assert(message->req.type==TMU_IPC_READ_TEMP && message->req.tzid==supplied.resp.tzid);
    *message=supplied; /* Pure synthetic copy. No real IPC call exists here. */
}
'''
    value+=extract(tmu_c,r'int exynos_acpm_tmu_set_read_temp\([^{}]+')+'\n'
    unit_line=re.findall(r'^\s*\*temp = acpm_temp \* MCELSIUS;',texts['drivers/thermal/samsung/exynos_tmu_v2.c'],re.M)
    if len(unit_line)!=1:raise ValueError('Actual Linux temperature conversion missing/ambiguous')
    value+='''
void oracle_tmu(void *out,unsigned zone,unsigned temperature,unsigned status,int result) {
    union tmu_ipc_message m={0};m.resp.type=TMU_IPC_READ_TEMP;m.resp.tzid=(u8)zone;
    m.resp.temp=(u8)temperature;m.resp.stat=(u8)status;m.resp.ret=(s8)result;memcpy(out,&m,sizeof(m));
}
void oracle_tmu_read(const void *input,unsigned zone,int *temp,int *status) {
    int acpm_temp=0,data[2];memcpy(&supplied,input,sizeof(supplied));
    assert(exynos_acpm_tmu_set_read_temp((int)zone,&acpm_temp,status,data)==0);
'''+unit_line[0]+'''\n}
static struct exynos_pm_qos_request mif_request_from_acpm={0},int_request_from_acpm={1};
static unsigned calls,captured_id;static s32 captured_rate;
void exynos_pm_qos_update_request_nosync(struct exynos_pm_qos_request *qos,s32 rate) {
    ++calls;captured_id=qos->id;captured_rate=rate;
}
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunused-parameter"
'''
    value+=extract(dvfs,r'static void acpm_noti_mif_callback\([^{}]+')+'\n#pragma GCC diagnostic pop\n'
    if 'req %d KHz' not in dvfs:raise ValueError('Source QoS units unavailable')
    value+='''
void oracle_clock(void *out,unsigned domain,uint32_t rate) { uint32_t words[4]={0,rate,domain,0};memcpy(out,words,sizeof(words)); }
unsigned oracle_clock_read(const void *input,unsigned *domain,int32_t *rate) {
    unsigned words[4];memcpy(words,input,sizeof(words));calls=0;acpm_noti_mif_callback(words,sizeof(words));
    *domain=captured_id;*rate=captured_rate;return calls;
}
unsigned oracle_domain_count(void) { return sizeof(acpm_vclk_list)/sizeof(acpm_vclk_list[0]); }
unsigned oracle_domain_id(unsigned index) { return acpm_vclk_list[index].id; }
void oracle_fvmap(void *out,unsigned index,unsigned reported,unsigned levels,unsigned offset) {
    struct fvmap_header header={0};memset(out,0,FVMAP_SIZE);header.domain_id=(u8)reported;
    header.num_of_lv=(u8)levels;header.o_ratevolt=(u16)offset;
    memcpy((uint8_t *)out+index*sizeof(header),&header,sizeof(header));
}
'''
    return value

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',required=True);p.add_argument('--lab-root',type=Path,default=ROOT)
    p.add_argument('--source-cache',type=Path,default=ROOT/'artifacts/power-host');p.add_argument('--clang',type=Path,default=Path('/home/egor/.local/bin/clang'));a=p.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',a.run):p.error('Fresh canonical run name required')
    lab=a.lab_root.resolve();cache=a.source_cache.resolve();out=ROOT/'artifacts/power-host'/a.run
    if not ROOT.is_relative_to(lab) or not cache.is_relative_to(lab) or out.resolve()!=out:p.error('Canonical owned laboratory paths required')
    out.mkdir(parents=True,exist_ok=False)
    report=dict(kind='host-test',origin='local-host',outcome='fail',recorded_at=datetime.now(timezone.utc).isoformat(),summary='Actual source-qualified thermal/clock-request/FVMAP copied-input host admission, genuine oracles, sanitizers and ARM64 compile only',commands=[],checks=[],source_inputs={},device_executed=False,hardware_safety_qualified=False,calibration_qualified=False,firmware_qualified=False,native_power_qualified=False,Apple_services_qualified=False)
    def rel(path):return str(path.resolve().relative_to(lab))
    def run(argv,label,env=None,negative=False,timed=False):
        if timed:argv=['/usr/bin/time','-f','{"max_rss_kib":%M}','-o',out/(label+'.rss.json'),*argv]
        stdout=out/(label+'.stdout.txt');stderr=out/(label+'.stderr.txt')
        with stdout.open('wb') as x,stderr.open('wb') as y:r=subprocess.run([str(v) for v in argv],cwd=ROOT,stdout=x,stderr=y,env=env,timeout=60)
        report['commands'].append(dict(argv=[str(v) for v in argv],cwd=str(ROOT),exit_code=r.returncode,stdout=rel(stdout),stderr=rel(stderr),environment={k:env[k] for k in ['GIT_NO_LAZY_FETCH','GIT_OPTIONAL_LOCKS','ASAN_OPTIONS','UBSAN_OPTIONS'] if env and k in env}))
        if (r.returncode!=0)!=negative:raise ValueError(label+' unexpected exit; diagnostics retained')
        if timed:
            rss=json.loads((out/(label+'.rss.json')).read_text())['max_rss_kib'];report.setdefault('peak_rss_kib',{})[label]=rss
            if rss>262144:raise ValueError('256MiB resident limit exceeded: '+label)
        return stdout.read_text(errors='replace')
    def check(name,good):
        report['checks'].append(dict(name=name,pass_check=bool(good)))
        if not good:raise ValueError(name)
    try:
        report['commit']=run(['git','rev-parse','HEAD'],'base-commit').strip();report['commit_role']='Actual base checkout; exact tested source bytes retained and hashed'
        profile=json.loads((HERE/'source-profile.json').read_text());pin=profile['samsung']['commit'];repo=lab/'references/s24-linux';texts={}
        for session in sorted({item['cache_session'] for item in profile['samsung']['sources']}):
            manifest=cache/session/'sources.json'
            metadata=json.loads(manifest.read_text());report.setdefault('source_acquisition',{})[session]=metadata['outcome']
            for name in ['fetch.py','sources.json','fetch.stdout.txt','fetch.stderr.txt']:
                original=cache/session/name;target=out/'source-acquisition'/session/name
                target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(original,target)
        env={**os.environ,'GIT_NO_LAZY_FETCH':'1','GIT_OPTIONAL_LOCKS':'0'}
        check('Samsung-pin',run(['git','-C',repo,'rev-parse','HEAD'],'samsung-pin',env).strip()==pin)
        for index,item in enumerate(profile['samsung']['sources']):
            name=item['path'];tree=run(['git','-C',repo,'ls-tree',pin,name],'tree-'+str(index),env)
            check('exact-pinned-blob-'+str(index),tree.split()[2]==item['git_blob'])
            original=cache/item['cache_session']/name
            check('verified-cache-'+str(index),sha(original)==item['sha256'])
            data=original.read_bytes();check('actual-git-blob-'+str(index),hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==item['git_blob'])
            target=out/'primary-inputs'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data);report['source_inputs'][rel(original)]=sha(original);texts[name]=data.decode()
        d=profile['donor'];repo=lab/'references/s24-port';check('E1S-pin',run(['git','-C',repo,'rev-parse','HEAD'],'e1s-pin',env).strip()==d['commit'])
        original=repo/d['path'];check('exact-donor-patch',sha(original)==d['sha256']);shutil.copyfile(original,out/'primary-inputs/e1s-acpm.patch');report['source_inputs'][rel(original)]=sha(original)
        donor=original.read_text().split('diff --git a/bsd/dev/e1s_acpm.c b/bsd/dev/e1s_acpm.c\n',1)[1].split('\ndiff --git ',1)[0]
        donor='\n'.join(line[1:] for line in donor.splitlines() if line.startswith('+') and not line.startswith('+++'))+'\n';(out/'actual-e1s-acpm.c').write_text(donor)
        zones=[]
        for match in re.finditer(r'tmuctrl_(\d+):\s*[^{}]+\{([^{}]+)\}',texts['arch/arm64/boot/dts/exynos/s5e9945-thermal.dtsi']):
            body=match[2];zones.append(dict(id=int(re.search(r'\bid\s*=\s*<(\d+)>',body)[1]),name=re.search(r'tmu_name\s*=\s*"([^"]+)"',body)[1]))
        check('actual-DTS-zone-profile-equality',zones==profile['selection']['tmu_zones'] and [z['id'] for z in zones]==list(range(8)))
        check('evt0-domain-declaration-equal-only',texts['drivers/soc/samsung/cal-if/s5e9945/acpm_dvfs_s5e9945.h']==texts['drivers/soc/samsung/cal-if/s5e9945_evt0/acpm_dvfs_s5e9945.h'])
        check('measured-clock-getter-disabled',bool(re.search(r'#if 0\s*unsigned long exynos_acpm_get_rate',texts['drivers/soc/samsung/cal-if/acpm_dvfs.c'])))
        generated=out/'genuine-source-oracle.c';generated.write_text(oracle(texts,donor))
        for name in ['observe.c','observe.h','fixture.c','check.py','source-profile.json']:
            q=HERE/name;target=out/'tested-inputs'/name;target.parent.mkdir(exist_ok=True);shutil.copyfile(q,target);report['source_inputs'][rel(q)]=sha(q)
        compiler=a.clang.resolve();run([compiler,'--version'],'compiler-version');report['compiler']=dict(path=str(compiler),sha256=sha(compiler))
        flags=['-std=c11','-Wall','-Wextra','-Werror','-Wpedantic','-O1','-g','-fno-omit-frame-pointer','-fsanitize=address,undefined','-fno-sanitize-recover=all'];binary=out/'fixture'
        run([compiler,*flags,HERE/'observe.c',HERE/'fixture.c',generated,'-o',binary],'fixture-build',timed=True)
        sanenv={**os.environ,'ASAN_OPTIONS':'detect_leaks=1:halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'}
        result=json.loads(run([binary],'fixture-runtime',sanenv,timed=True));report['result']=result
        check('real-source-oracle-lifecycle-guard-runtime',result['tmu_cases']==2048 and result['clock_cases']==14 and result['extent_cases']==33 and result['guard_lengths']==32 and result['random_records']==100000 and not result['hardware_io'])
        negative=out/'negative.c';negative.write_text('''#include <limits.h>
#include <stdlib.h>
int main(int argc,char **argv) { if(argc!=2)return 2;if(argv[1][0]=='a') { volatile unsigned char *p=malloc(8);if(!p)return 2;p[(unsigned)argc+14]=1;free((void *)p); }else { volatile int value=INT_MAX;return value+argc; }return 0; }
''');control=out/'negative';run([compiler,*flags,negative,'-o',control],'negative-build',timed=True)
        run([control,'asan'],'negative-asan',sanenv,negative=True);run([control,'ubsan'],'negative-ubsan',sanenv,negative=True)
        check('actual-ASan-fault-detection','AddressSanitizer: heap-buffer-overflow' in (out/'negative-asan.stderr.txt').read_text());check('actual-UBSan-fault-detection','signed integer overflow' in (out/'negative-ubsan.stderr.txt').read_text())
        resource=Path(run([compiler,'-print-resource-dir'],'resource-directory').strip())
        layout=out/'genuine-layout.c';layout.write_text(generated.read_text().split('static bool acpm_tmu_test_mode',1)[0].replace('#include <assert.h>\n','').replace('#include <string.h>\n',''))
        objects=[]
        for name,source in [('owned-input',HERE/'observe.c'),('genuine-layout',layout)]:
            obj=out/(name+'.o');objects.append(obj)
            run([compiler,'-target','arm64-apple-ios16.5','-ffreestanding','-fno-builtin','-nostdinc','-isystem',resource/'include','-std=c11','-Wall','-Wextra','-Werror','-Wpedantic','-c',source,'-o',obj],'arm64-'+name,timed=True)
        text=run([compiler.parent/'llvm-readobj','--file-headers','--sections','--symbols',*objects],'arm64-inspect');check('two-actual-arm64-MachO-compile-only',text.count('Format: Mach-O arm64')==2 and all(obj.read_bytes()[:4]==bytes.fromhex('cffaedfe') for obj in objects))
        report['acceptance_assessment']=[dict(criterion=1,pass_check=True,evidence='Exact pinned Samsung/E1S sources, units/declarations/table selections and firmware/calibration unknowns retained; no safe actuation limit inferred'),dict(criterion=2,pass_check=True,evidence='Actual owned C with genuine declarations/read helper/unit line/QoS callback/table oracle, malformed/stale/unavailable/unit/overflow/error/Stop cases; ASan/UBSan negative controls and ARM64 compile only'),dict(criterion=3,pass_check=True,evidence='Exact source/tool/command/exit/output evidence and handoff in owned paths; no device or power command')]
        report['outcome']='pass'
    except Exception as error:report['error']=repr(error)
    files=sorted(q for q in out.rglob('*') if q.is_file() and q.name!='evidence.json');report['artifacts']=[rel(q) for q in files];report['sha256']={rel(q):sha(q) for q in files}
    (out/'evidence.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(outcome=report['outcome'],error=report.get('error'),checks=len(report['checks']),evidence=rel(out/'evidence.json'))));return report['outcome']!='pass'
if __name__=='__main__':sys.exit(main())
