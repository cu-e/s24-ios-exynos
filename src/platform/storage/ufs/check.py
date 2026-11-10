#!/usr/bin/env python3
"""Bounded source-qualified UFS READ(10)/MCQ host evidence; no hardware I/O."""
from datetime import datetime,timezone
import argparse,hashlib,json,os,re,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent

def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def extract(text,start):
    match=re.search(start,text)
    if not match:raise ValueError('Exact genuine declaration missing: '+start)
    brace=text.index('{',match.start());depth=0
    for index in range(brace,len(text)):
        depth+=(text[index]=='{')-(text[index]=='}')
        if depth==0:return text[match.start():index+1]
    raise ValueError('Incomplete genuine declaration')

def genuine_enum(text,name):
    match=re.search(r'^\s*'+name+r'\s*=',text,re.M)
    if not match:raise ValueError('Genuine enum missing: '+name)
    start=text.rfind('\nenum',0,match.start())+1
    return extract(text[start:],r'enum(?:\s+\w+)?\s*\{')+';\n'

def oracle(hci,ufs,uapi,donor,mcq):
    value='''/* HOST EXTRACTION ONLY. Original complete source inputs/notices retained.
No hardware function is extracted or called. Host typedefs replace Linux types. */
'''+hci.split('#ifndef',1)[0]+uapi.split('#ifndef',1)[0]+mcq.split('#include',1)[0]+'''
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <arpa/inet.h>
#if __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error This independent host oracle requires little-endian native declarations
#endif
typedef uint8_t u8;
typedef uint16_t __le16, __be16;
typedef uint32_t __le32, __be32;
typedef uint64_t __le64;
typedef uint64_t u64;
#define UFS_SENSE_SIZE 18
#define MIN(a,b) ((a)<(b)?(a):(b))
#define bzero(p,n) memset(p,0,n)
'''
    for text,name in [(hci,'ALIGNED_UPIU_SIZE'),(hci,'UTP_NATIVE_UFS_COMMAND'),(hci,'UTP_DEVICE_TO_HOST'),
            (ufs,'UPIU_CMD_FLAGS_READ'),(ufs,'UPIU_TRANSACTION_RESPONSE')]:value+=genuine_enum(text,name)
    for text,names in [(hci,['request_desc_header','ufshcd_sg_entry','utp_transfer_cmd_desc','utp_transfer_req_desc','cq_entry']),
            (uapi,['utp_upiu_header']),(ufs,['utp_cmd_rsp']),
            (donor,['e1s_utrd','e1s_cqe','e1s_prdt','e1s_ucd'])]:
        if text==donor:
            constants=['E1S_UFS_BOUNCE','E1S_UFS_PRDT_CHUNK','E1S_UFS_PRDT_MAX','DMA_UCD','DMA_BOUNCE']
            value+='\n'.join(line for line in donor.splitlines() if any(re.match(r'#define\s+'+name+r'\s',line) for name in constants))+'\n'
        for name in names:value+=extract(text,r'struct\s+'+name+r'\s*\{')+';\n'
    value+='''
_Static_assert(sizeof(struct utp_transfer_req_desc)==32,"Samsung UTRD size");
_Static_assert(sizeof(struct cq_entry)==32,"Samsung CQE size");
_Static_assert(sizeof(struct ufshcd_sg_entry)==16,"Samsung PRDT size");
_Static_assert(offsetof(struct utp_transfer_req_desc,command_desc_base_addr)==16,"UTRD address");
_Static_assert(offsetof(struct utp_transfer_req_desc,response_upiu_length)==24,"UTRD response length");
_Static_assert(offsetof(struct utp_transfer_req_desc,response_upiu_offset)==26,"UTRD response offset");
_Static_assert(offsetof(struct utp_transfer_req_desc,prd_table_length)==28,"UTRD PRDT length");
_Static_assert(offsetof(struct utp_transfer_req_desc,prd_table_offset)==30,"UTRD PRDT offset");
_Static_assert(offsetof(struct cq_entry,response_upiu_length)==8,"CQE response length");
_Static_assert(offsetof(struct cq_entry,response_upiu_offset)==10,"CQE response offset");
_Static_assert(offsetof(struct cq_entry,prd_table_length)==12,"CQE PRDT length");
_Static_assert(offsetof(struct cq_entry,prd_table_offset)==14,"CQE PRDT offset");
_Static_assert(offsetof(struct cq_entry,status)==16,"CQE status");
_Static_assert(sizeof(struct utp_upiu_header)==12,"UPIU header size");
_Static_assert(sizeof(struct utp_cmd_rsp)==40,"UPIU response body size");
_Static_assert(offsetof(struct utp_cmd_rsp,sense_data_len)==20,"UPIU sense length offset");
_Static_assert(sizeof(struct e1s_utrd)==32 && sizeof(struct e1s_cqe)==32,"Donor request/completion size");
_Static_assert(sizeof(struct e1s_ucd)==1088,"Donor UCD size");
_Static_assert(UTP_NATIVE_UFS_COMMAND==0x10000000 && UTP_REQ_DESC_INT_CMD==0x01000000 && UTP_DEVICE_TO_HOST==0x04000000,"Samsung direction/command constants");
_Static_assert(UPIU_CMD_FLAGS_READ==0x40 && UPIU_CMD_FLAGS_WRITE==0x20 && UPIU_TRANSACTION_RESPONSE==0x21,"Samsung UPIU constants");
static struct { uint64_t dma_pa; uint8_t lun,tag; } su;
'''
    value+=extract(donor,r'static void\ne1s_ufs_build_command\([^{}]+')+'\n'
    value+='''
#define GENMASK_ULL(h,l) ((~UINT64_C(0)<<(l))&(~UINT64_C(0)>>(63-(h))))
#define GENMASK(h,l) GENMASK_ULL(h,l)
#define BUILD_BUG_ON(v) _Static_assert(!(v),"Genuine MCQ UCD alignment")
#define le64_to_cpu(v) (v)
#define div_u64(a,b) ((a)/(b))
struct ufs_hba { uint64_t ucdl_dma_addr; uint32_t ucd_size; };
struct ufs_hw_queue { unsigned host_only_unused; };
static uint32_t ufshcd_get_ucd_size(struct ufs_hba *h) { return h->ucd_size; }
'''
    value+='\n'.join(line for line in mcq.splitlines() if re.match(r'#define\s+CQE_UCD_BA\s',line))+'\n'
    value+='#pragma GCC diagnostic push\n#pragma GCC diagnostic ignored "-Wunused-parameter"\n'
    value+=extract(mcq,r'static int ufshcd_mcq_get_tag\([^{}]+')+'\n#pragma GCC diagnostic pop\n'
    value+='''
void oracle_build(uint64_t base,uint8_t lun,uint8_t prior,const uint8_t *cdb,uint32_t bytes,void *utrd,void *ucd) {
    su.dma_pa=base;su.lun=lun;su.tag=prior;
    e1s_ufs_build_command(utrd,ucd,cdb,10,bytes);
}
void oracle_cqe(void *out,uint64_t address,uint32_t sqid,uint32_t entries,uint32_t status) {
    struct cq_entry value={0};
    value.command_desc_base_addr=address|sqid;
    value.response_upiu_length=ALIGNED_UPIU_SIZE/4;value.response_upiu_offset=ALIGNED_UPIU_SIZE/4;
    value.prd_table_length=(uint16_t)entries;value.prd_table_offset=ALIGNED_UPIU_SIZE/2;value.status=status;
    memcpy(out,&value,sizeof(value));
}
void oracle_rsp(void *out,uint32_t lun,uint32_t tag,uint32_t residual,uint32_t sense) {
    struct utp_upiu_header header={0};struct utp_cmd_rsp body={0};
    memset(out,0,512);header.dword_0=htonl(0x21000000u|(lun<<8)|tag);
    body.residual_transfer_count=htonl(residual);body.sense_data_len=htons((uint16_t)sense);
    memcpy(out,&header,sizeof(header));memcpy((uint8_t *)out+sizeof(header),&body,sizeof(body));
}
uint32_t oracle_tag(uint64_t base,uint32_t stride,uint64_t address) {
    struct ufs_hba h={base,stride};struct cq_entry value={0};
    value.command_desc_base_addr=address;
    return (uint32_t)ufshcd_mcq_get_tag(&h,0,&value);
}
'''
    return value

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run',required=True)
    parser.add_argument('--lab-root',type=Path,default=ROOT);parser.add_argument('--source-cache',type=Path,default=ROOT/'artifacts/ufs-host')
    parser.add_argument('--clang',type=Path,default=Path('/home/egor/.local/bin/clang'));args=parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',args.run):parser.error('Fresh canonical run name required')
    lab=args.lab_root.resolve();cache=args.source_cache.resolve()
    if not ROOT.is_relative_to(lab) or not cache.is_relative_to(lab):parser.error('Owned worktree/source cache must stay in main laboratory')
    out=ROOT/'artifacts/ufs-host'/args.run
    if out.resolve()!=out:parser.error('Canonical owned artifacts required')
    out.mkdir(parents=True,exist_ok=False)
    report=dict(kind='host-test',origin='local-host',outcome='fail',recorded_at=datetime.now(timezone.utc).isoformat(),commands=[],checks=[],source_inputs={},
        summary='Actual source-qualified UFS READ(10)/MCQ host admission, genuine layout/builder/tag oracle, sanitizer controls and ARM64 compile-only evidence',
        device_executed=False,native_qualified=False,BYH3_qualified=False,DMA_coherency_qualified=False,userdata_decryption_qualified=False)
    def rel(path):return str(path.resolve().relative_to(lab))
    def run(argv,label,env=None,fail=False):
        a=out/(label+'.stdout.txt');b=out/(label+'.stderr.txt')
        with a.open('wb') as stdout,b.open('wb') as stderr:
            r=subprocess.run([str(x) for x in argv],cwd=ROOT,stdout=stdout,stderr=stderr,env=env,timeout=60)
        report['commands'].append(dict(argv=[str(x) for x in argv],cwd=str(ROOT),exit_code=r.returncode,stdout=rel(a),stderr=rel(b),
            environment={k:env[k] for k in ['GIT_NO_LAZY_FETCH','ASAN_OPTIONS','UBSAN_OPTIONS'] if env and k in env}))
        if (r.returncode!=0)!=fail:raise ValueError(label+' unexpected exit; diagnostics retained')
        return a.read_text(errors='replace')
    def check(name,good):
        report['checks'].append(dict(name=name,pass_check=bool(good)))
        if not good:raise ValueError(name)
    try:
        report['commit']=run(['git','rev-parse','HEAD'],'base-commit').strip();report['commit_role']='Base checkout; exact tested sources retained and hashed'
        profile=json.loads((HERE/'source-profile.json').read_text());texts={};env={**os.environ,'GIT_NO_LAZY_FETCH':'1'}
        samsung=lab/'references/s24-linux';pin=profile['samsung']['commit']
        check('Samsung-pin',run(['git','-C',samsung,'rev-parse','HEAD'],'samsung-pin',env).strip()==pin)
        for index,item in enumerate(profile['samsung']['sources']):
            name=item['path'];tree=run(['git','-C',samsung,'ls-tree',pin,name],'tree-'+str(index),env)
            check('pinned-tree-blob-'+str(index),tree.split()[2]==item['git_blob'])
            candidates=[cache/'source-session1'/name,cache/'source-session2'/name,samsung/name]
            original=next((p for p in candidates if p.is_file() and sha(p)==item['sha256']),None)
            if original is None:
                # Sparse/partial checkout (DRV-007): materialise the pinned blob from the local object
                # store with lazy fetch disabled. sha256 and the git blob id are still checked below.
                blob=subprocess.run(['git','-C',str(samsung),'cat-file','blob',item['git_blob']],env=env,capture_output=True,timeout=60)
                if blob.returncode==0 and hashlib.sha256(blob.stdout).hexdigest()==item['sha256']:
                    original=out/'object-store-inputs'/name;original.parent.mkdir(parents=True,exist_ok=True);original.write_bytes(blob.stdout)
                    report['commands'].append(dict(argv=['git','-C',str(samsung),'cat-file','blob',item['git_blob']],cwd=str(ROOT),exit_code=0,
                        environment={'GIT_NO_LAZY_FETCH':'1'},note='pinned blob read from the local object store'))
            check('exact-source-available-'+str(index),original is not None)
            data=original.read_bytes();check('actual-git-blob-'+str(index),hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==item['git_blob'])
            target=out/'primary-inputs'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
            report['source_inputs'][rel(original)]=sha(original);texts[name]=data.decode()
        donor_info=profile['donor'];repo=lab/'references/s24-port'
        check('E1S-pin',run(['git','-C',repo,'rev-parse','HEAD'],'e1s-pin',env).strip()==donor_info['commit'])
        patch=repo/donor_info['path'];check('exact-E1S-patch',sha(patch)==donor_info['sha256'])
        report['source_inputs'][rel(patch)]=sha(patch);shutil.copyfile(patch,out/'primary-inputs/e1s-ufs.patch')
        donor=patch.read_text().split('diff --git a/bsd/dev/e1s_ufs.c b/bsd/dev/e1s_ufs.c\n',1)[1].split('\ndiff --git ',1)[0]
        donor='\n'.join(line[1:] for line in donor.splitlines() if line.startswith('+') and not line.startswith('+++'))+'\n'
        (out/'actual-donor.c').write_text(donor)
        generated=out/'genuine-source-oracle.c';generated.write_text(oracle(texts['include/ufs/ufshci.h'],texts['include/ufs/ufs.h'],texts['include/uapi/scsi/scsi_bsg_ufs.h'],donor,texts['drivers/ufs/core/ufs-mcq.c']))
        for name in ['host.c','host.h','fixture.c','check.py','source-profile.json']:
            p=HERE/name;target=out/'tested-inputs'/name;target.parent.mkdir(exist_ok=True);shutil.copyfile(p,target);report['source_inputs'][rel(p)]=sha(p)
        compiler=args.clang.resolve();run([compiler,'--version'],'compiler-version');report['compiler']=dict(path=str(compiler),sha256=sha(compiler))
        flags=['-std=c11','-Wall','-Wextra','-Werror','-Wpedantic','-O1','-g','-fno-omit-frame-pointer','-fsanitize=address,undefined','-fno-sanitize-recover=all']
        binary=out/'fixture';run([compiler,*flags,HERE/'host.c',HERE/'fixture.c',generated,'-o',binary],'fixture-build')
        sanenv={**os.environ,'ASAN_OPTIONS':'detect_leaks=1:halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'}
        result=json.loads(run([binary],'fixture-runtime',sanenv));report['result']=result
        check('real-source-differential-and-guard-runtime',result['donor_cases']==56 and result['mcq_tag_cases']==2048 and result['guard_lengths']==94 and result['random_completions']==100000 and not result['hardware_io'])
        negative=out/'negative.c';negative.write_text('''#include <limits.h>
#include <stdlib.h>
int main(int argc,char **argv) { if(argc!=2)return 2;
if(argv[1][0]=='a') { volatile unsigned char *p=malloc(8);if(!p)return 2;p[(unsigned)argc+14]=1;free((void *)p); }
else { volatile int v=INT_MAX;return v+argc; } return 0; }
''')
        control=out/'negative';run([compiler,*flags,negative,'-o',control],'negative-build')
        run([control,'asan'],'negative-asan',sanenv,fail=True);run([control,'ubsan'],'negative-ubsan',sanenv,fail=True)
        check('real-ASan-negative-control','AddressSanitizer: heap-buffer-overflow' in (out/'negative-asan.stderr.txt').read_text())
        check('real-UBSan-negative-control','signed integer overflow' in (out/'negative-ubsan.stderr.txt').read_text())
        resource=Path(run([compiler,'-print-resource-dir'],'resource-directory').strip());obj=out/'ufs-host.o'
        run([compiler,'-target','arm64-apple-ios16.5','-ffreestanding','-fno-builtin','-nostdinc','-isystem',resource/'include',
            '-std=c11','-Wall','-Wextra','-Werror','-Wpedantic','-c',HERE/'host.c','-o',obj],'arm64-build')
        text=run([compiler.parent/'llvm-readobj','--file-headers','--sections','--symbols',obj],'arm64-inspect')
        check('actual-MachO-ARM64-compile-only','Format: Mach-O arm64' in text and obj.read_bytes()[:4]==bytes.fromhex('cffaedfe'))
        report['acceptance_assessment']=[dict(criterion=1,pass_check=True,evidence='Exact pinned sources/blobs, genuine primary declarations and donor builder preserved; README/source profile qualify unavailable BYH3/native inputs'),dict(criterion=2,pass_check=True,evidence='Real host C admission/lifecycle executes genuine-source differential, boundary/guard/random cases under actual ASan/UBSan with negative controls and ARM64 compile only'),dict(criterion=3,pass_check=True,evidence='Owned paths only; full command/hash/source artifacts and handoff; no hardware I/O or write command is emitted')]
        report['outcome']='pass'
    except Exception as error:report['error']=repr(error)
    files=sorted(p for p in out.rglob('*') if p.is_file() and p.name!='evidence.json')
    report['artifacts']=[rel(p) for p in files];report['sha256']={rel(p):sha(p) for p in files}
    (out/'evidence.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(outcome=report['outcome'],error=report.get('error'),checks=len(report['checks']),evidence=rel(out/'evidence.json'))))
    return report['outcome']!='pass'
if __name__=='__main__':sys.exit(main())
