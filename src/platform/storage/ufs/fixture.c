/* Host fixture uses independent genuine-source builder and declarations. */
#define _GNU_SOURCE
#include "host.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
extern void oracle_build(uint64_t, uint8_t, uint8_t, const uint8_t *, uint32_t, void *, void *);
extern void oracle_cqe(void *, uint64_t, uint32_t, uint32_t, uint32_t);
extern void oracle_rsp(void *, uint32_t, uint32_t, uint32_t, uint32_t);
extern uint32_t oracle_tag(uint64_t, uint32_t, uint64_t);
static unsigned checks, donor_cases, guard_cases, mcq_tag_cases;
#define CHECK(x) do { checks++; assert(x); } while (0)
static struct ufs_policy policy(void)
{
    struct ufs_policy p={1000000,100,900000,UINT64_C(0x123450001000),UFS_UCD_BYTES,
        UINT64_C(0x123450002000),UFS_MAX_TRANSFER,4096,0,0,7};
    return p;
}
static void cdb_read(uint8_t *cdb, uint32_t lba, uint32_t blocks)
{
    memset(cdb,0,10);cdb[0]=0x28;
    cdb[2]=(uint8_t)(lba>>24);cdb[3]=(uint8_t)(lba>>16);
    cdb[4]=(uint8_t)(lba>>8);cdb[5]=(uint8_t)lba;
    cdb[7]=(uint8_t)(blocks>>8);cdb[8]=(uint8_t)blocks;
}
static void start(struct ufs_host *h, struct ufs_policy *p, uint8_t *cdb)
{
    CHECK(ufs_host_init(h,p)==UFS_OK);cdb_read(cdb,100,1);
    CHECK(ufs_host_prepare(h,cdb,10,UFS_FROM_DEVICE,p->block_bytes)==UFS_OK);
    CHECK(ufs_host_reserve_device(h,&h->token,100,1000)==UFS_OK);
}
static void good(struct ufs_host *h, uint8_t *cqe, uint8_t *rsp)
{
    oracle_cqe(cqe,h->policy.ucd_dma,h->policy.sqid,h->packet.prdt_entries,0);
    oracle_rsp(rsp,h->policy.lun,h->token.tag,0,0);
}
int main(void)
{
    struct ufs_host h,before;
    struct ufs_policy p=policy(),bad;
    struct ufs_token stale;
    struct ufs_packet donor;
    uint8_t cdb[10],cqe[32],rsp[512],*region,*edge;
    unsigned i,j,k,random=24009945;
    const uint32_t counts[]={1,2,63,64,65,255,256};
    long pagesize=sysconf(_SC_PAGESIZE);
    /* Full byte comparison against actual pinned donor pure builder. */
    for (i=0;i<2;i++) for (j=0;j<sizeof(counts)/sizeof(counts[0]);j++) for (k=0;k<4;k++) {
        uint32_t bytes;
        p=policy();p.block_bytes=i?512:4096;p.lun=k?127:0;p.sqid=k;
        p.ucd_dma+=((uint64_t)k<<32);p.data_dma+=((uint64_t)k<<32);
        bytes=counts[j]*p.block_bytes;
        CHECK(ufs_host_init(&h,&p)==0);cdb_read(cdb,100+k,counts[j]);
        CHECK(ufs_host_prepare(&h,cdb,10,UFS_FROM_DEVICE,bytes)==0);
        memset(&donor,0,sizeof(donor));
        oracle_build(p.ucd_dma-4096,(uint8_t)p.lun,0,cdb,bytes,donor.utrd,donor.ucd);
        CHECK(!memcmp(h.packet.utrd,donor.utrd,32));CHECK(!memcmp(h.packet.ucd,donor.ucd,UFS_UCD_BYTES));
        CHECK(h.packet.bytes==bytes);donor_cases++;
        CHECK(ufs_host_cancel_prepared(&h,&h.token)==0);
    }
    /* Real Samsung MCQ tag function masks SQ ID out of the UCD address.
       Use a128-aligned stride; donor1088-byte UCD is not such an array stride. */
    for (i=0;i<64;i++) for (j=0;j<32;j++) {
        CHECK(oracle_tag(UINT64_C(0x123450000000),1152,UINT64_C(0x123450000000)+(uint64_t)i*1152+j)==i);
        mcq_tag_cases++;
    }
    for (i=0;i<32;i++) {
        p=policy();p.sqid=i;start(&h,&p,cdb);good(&h,cqe,rsp);
        CHECK(ufs_host_complete(&h,&h.token,cqe,32,rsp,52,101)==0);
        CHECK(ufs_host_reclaim(&h,&h.token)==0);
    }
    p=policy();CHECK(ufs_host_init(NULL,&p)==UFS_ARGUMENT);
    for (i=0;i<13;i++) {
        bad=p;
        switch(i) {
        case 0:bad.epoch=0;break;case 1:bad.lun=128;break;case 2:bad.sqid=32;break;
        case 3:bad.block_bytes=1024;break;case 4:bad.extent_blocks=UINT64_MAX;break;
        case 5:bad.first_block=bad.lun_blocks;break;case 6:bad.ucd_dma++;break;
        case 7:bad.data_dma++;break;case 8:bad.ucd_bytes=1087;break;
        case 9:bad.data_bytes=UFS_MAX_TRANSFER-1;break;case 10:bad.data_dma=bad.ucd_dma;break;
        case 11:bad.ucd_dma=UINT64_MAX-127;break;default:bad.data_bytes=UINT64_MAX;break;
        }
        CHECK(ufs_host_init(&h,&bad)!=0);
    }
    CHECK(ufs_host_init(&h,&p)==0);cdb_read(cdb,100,1);before=h;
    for (i=0;i<256;i++) if(i!=0x28) {
        cdb[0]=(uint8_t)i;CHECK(ufs_host_prepare(&h,cdb,10,UFS_FROM_DEVICE,4096)==UFS_COMMAND);
        CHECK(!memcmp(&h,&before,sizeof(h)));
    }
    cdb[0]=0x28;
    CHECK(ufs_host_prepare(&h,cdb,10,UFS_TO_DEVICE,4096)==UFS_WRITE_REJECTED);
    CHECK(ufs_host_prepare(&h,cdb,10,0,4096)==UFS_WRITE_REJECTED);
    for (i=0;i<3;i++) { unsigned at=i==0?1:i==1?6:9;cdb[at]=1;CHECK(ufs_host_prepare(&h,cdb,10,1,4096)==UFS_COMMAND);cdb[at]=0; }
    cdb_read(cdb,99,1);CHECK(ufs_host_prepare(&h,cdb,10,1,4096)==UFS_EXTENT);
    cdb_read(cdb,900099,2);CHECK(ufs_host_prepare(&h,cdb,10,1,8192)==UFS_EXTENT);
    cdb_read(cdb,100,0);CHECK(ufs_host_prepare(&h,cdb,10,1,0)==UFS_EXTENT);
    cdb_read(cdb,100,257);CHECK(ufs_host_prepare(&h,cdb,10,1,257*4096)==UFS_EXTENT);
    cdb_read(cdb,100,1);CHECK(ufs_host_prepare(&h,cdb,10,1,4095)==UFS_EXTENT);
    bad=p;bad.lun_blocks=UINT64_MAX;bad.first_block=0;bad.extent_blocks=UINT64_MAX;
    CHECK(ufs_host_init(&h,&bad)==0);cdb_read(cdb,UINT32_MAX,2);
    CHECK(ufs_host_prepare(&h,cdb,10,1,8192)==UFS_EXTENT);
    cdb_read(cdb,UINT32_MAX,1);CHECK(ufs_host_prepare(&h,cdb,10,1,4096)==0);
    /* Generation/task-tag exhaustion cannot wrap and alias old wire tags. */
    CHECK(ufs_host_init(&h,&p)==0);cdb_read(cdb,100,1);
    for (i=1;i<=255;i++) { CHECK(ufs_host_prepare(&h,cdb,10,1,4096)==0);CHECK(h.token.tag==i);CHECK(ufs_host_cancel_prepared(&h,&h.token)==0); }
    CHECK(ufs_host_prepare(&h,cdb,10,1,4096)==UFS_EXHAUSTED);
    /* Completion alone does not allow DMA reuse. Real backend reclaim is separate. */
    start(&h,&p,cdb);good(&h,cqe,rsp);stale=h.token;stale.generation++;
    CHECK(ufs_host_complete(&h,&stale,cqe,32,rsp,52,101)==UFS_STALE);
    CHECK(h.phase==UFS_DEVICE_OWNED);
    CHECK(ufs_host_cancel_prepared(&h,&h.token)==UFS_OWNERSHIP);
    CHECK(ufs_host_reclaim(&h,&h.token)==UFS_OWNERSHIP);
    CHECK(ufs_host_prepare(&h,cdb,10,1,4096)==UFS_BUSY);
    cqe[0]^=128;CHECK(ufs_host_complete(&h,&h.token,cqe,32,rsp,52,102)==UFS_STALE);cqe[0]^=128;
    cqe[0]^=1;CHECK(ufs_host_complete(&h,&h.token,cqe,32,rsp,52,103)==UFS_STALE);cqe[0]^=1;
    cqe[0]|=32;CHECK(ufs_host_complete(&h,&h.token,cqe,32,rsp,52,104)==UFS_FORMAT);cqe[0]&=(uint8_t)~32;
    rsp[3]++;CHECK(ufs_host_complete(&h,&h.token,cqe,32,rsp,52,105)==UFS_STALE);rsp[3]--;
    cqe[14]++;CHECK(ufs_host_complete(&h,&h.token,cqe,32,rsp,52,106)==UFS_FORMAT);cqe[14]--;
    CHECK(ufs_host_complete(&h,&h.token,cqe,32,rsp,52,107)==0);CHECK(h.phase==UFS_COMPLETE);
    CHECK(ufs_host_prepare(&h,cdb,10,1,4096)==UFS_BUSY);
    CHECK(ufs_host_reclaim(&h,&h.token)==0);CHECK(h.phase==UFS_IDLE);
    /* Matching OCS, check condition, residual, sense and unsupported flags quarantine. */
    for(i=0;i<10;i++) {
        start(&h,&p,cdb);good(&h,cqe,rsp);
        switch(i) { case 0:cqe[16]=15;break;case 1:rsp[7]=2;break;case 2:rsp[15]=1;break;
        case 3:rsp[33]=18;break;case 4:rsp[1]=0x20;break;case 5:rsp[1]=0x40;break;
        case 6:rsp[0]=0x3f;break;case 7:rsp[6]=1;break;case 8:rsp[10]=1;break;default:rsp[8]=1;break; }
        CHECK(ufs_host_complete(&h,&h.token,cqe,32,rsp,52,101)==UFS_STATUS);
        CHECK(h.phase==UFS_QUARANTINED);CHECK(ufs_host_reclaim(&h,&h.token)==UFS_OWNERSHIP);
        CHECK(ufs_host_prepare(&h,cdb,10,1,4096)==UFS_BUSY);
    }
    start(&h,&p,cdb);good(&h,cqe,rsp);
    CHECK(ufs_host_complete(&h,&h.token,cqe,32,rsp,52,99)==UFS_CLOCK);
    CHECK(ufs_host_poll_timeout(&h,1099)==0);CHECK(ufs_host_poll_timeout(&h,1100)==UFS_TIMEOUT);
    CHECK(h.phase==UFS_QUARANTINED);CHECK(ufs_host_reclaim(&h,&h.token)==UFS_OWNERSHIP);
    CHECK(ufs_host_complete(&h,&h.token,cqe,32,rsp,52,1101)==UFS_OWNERSHIP);
    CHECK(ufs_host_init(&h,&p)==0);cdb_read(cdb,100,1);CHECK(ufs_host_prepare(&h,cdb,10,1,4096)==0);
    CHECK(ufs_host_reserve_device(&h,&h.token,UINT64_MAX-5,10)==UFS_CLOCK);CHECK(h.phase==UFS_PREPARED);
    CHECK(ufs_host_reserve_device(&h,&h.token,100,0)==UFS_CLOCK);
    CHECK(ufs_host_reserve_device(&h,&h.token,100,UFS_TIMEOUT_MAX_NS+1)==UFS_CLOCK);
    /* Guard pages catch reads beyond declared CDB/CQE/response lengths. */
    CHECK(pagesize>0);region=mmap(NULL,(size_t)pagesize*2,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    CHECK(region!=MAP_FAILED);CHECK(mprotect(region+pagesize,(size_t)pagesize,PROT_NONE)==0);
    for(i=0;i<10;i++) { CHECK(ufs_host_init(&h,&p)==0);edge=region+pagesize-i;if(i)memcpy(edge,cdb,i);CHECK(ufs_host_prepare(&h,edge,i,1,4096)==UFS_LENGTH);guard_cases++; }
    for(i=0;i<32;i++) { start(&h,&p,cdb);good(&h,cqe,rsp);edge=region+pagesize-i;if(i)memcpy(edge,cqe,i);CHECK(ufs_host_complete(&h,&h.token,edge,i,rsp,52,101)==UFS_LENGTH);guard_cases++; }
    for(i=0;i<52;i++) { start(&h,&p,cdb);good(&h,cqe,rsp);edge=region+pagesize-i;if(i)memcpy(edge,rsp,i);CHECK(ufs_host_complete(&h,&h.token,cqe,32,edge,i,101)==UFS_LENGTH);guard_cases++; }
    start(&h,&p,cdb);good(&h,cqe,rsp);CHECK(ufs_host_complete(&h,&h.token,cqe,33,rsp,52,101)==UFS_LENGTH);
    CHECK(ufs_host_complete(&h,&h.token,cqe,32,rsp,513,101)==UFS_LENGTH);
    CHECK(ufs_host_complete(&h,&h.token,NULL,32,rsp,52,101)==UFS_ARGUMENT);
    for(i=0;i<100000;i++) {
        for(j=0;j<32;j++) { random=random*1664525u+1013904223u;cqe[j]=(uint8_t)(random>>24); }
        for(j=0;j<52;j++) { random=random*1664525u+1013904223u;rsp[j]=(uint8_t)(random>>24); }
        start(&h,&p,cdb);CHECK(ufs_host_complete(&h,&h.token,cqe,32,rsp,52,101)!=0);CHECK(h.phase!=UFS_IDLE);
    }
    CHECK(munmap(region,(size_t)pagesize*2)==0);
    printf("{\"checks\":%u,\"donor_cases\":%u,\"mcq_tag_cases\":%u,\"guard_lengths\":%u,\"random_completions\":100000,\"hardware_io\":false}\n",checks,donor_cases,mcq_tag_cases,guard_cases);
    return 0;
}
