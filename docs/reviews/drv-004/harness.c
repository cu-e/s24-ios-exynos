/* Project-authored independent source-review harness, host only. */
#include "host.h"
#include "source-layout.h"
#include <assert.h>
#include <arpa/inet.h>
#include <stdio.h>
#include <string.h>
static struct ufs_policy policy(void)
{
    struct ufs_policy p={UINT64_C(0x100000000),123,10000,UINT64_C(0x100080),1088,
        UINT64_C(0x300000),1048576,4096,7,31,9};return p;
}
static void read10(uint8_t *cdb,unsigned count)
{
    memset(cdb,0,10);cdb[0]=0x28;cdb[5]=123;cdb[7]=(uint8_t)(count>>8);cdb[8]=(uint8_t)count;
}
static void prepare(struct ufs_host *h,struct ufs_policy *p,unsigned blocks)
{
    uint8_t cdb[10];assert(ufs_host_init(h,p)==UFS_OK);read10(cdb,blocks);
    assert(ufs_host_prepare(h,cdb,10,UFS_FROM_DEVICE,(uint64_t)blocks*p->block_bytes)==UFS_OK);
}
static void reserve(struct ufs_host *h)
{ assert(ufs_host_reserve_device(h,&h->token,1000,500)==UFS_OK); }
static void completion(const struct ufs_host *h,uint8_t *cq,uint8_t *rsp)
{
    struct cq_entry c={0};struct utp_upiu_header header={0};struct utp_cmd_rsp body={0};
    c.command_desc_base_addr=h->policy.ucd_dma|h->policy.sqid;
    c.response_upiu_length=128;c.response_upiu_offset=128;
    c.prd_table_length=(uint16_t)h->packet.prdt_entries;c.prd_table_offset=256;
    memcpy(cq,&c,sizeof(c));memset(rsp,0,512);
    header.dword_0=htonl(UINT32_C(0x21000000)|(h->policy.lun<<8)|h->token.tag);
    memcpy(rsp,&header,sizeof(header));memcpy(rsp+sizeof(header),&body,sizeof(body));
}
static void held(struct ufs_host *h)
{
    uint8_t cdb[10];read10(cdb,1);
    assert(ufs_host_cancel_prepared(h,&h->token)==UFS_OWNERSHIP);
    assert(ufs_host_reclaim(h,&h->token)==UFS_OWNERSHIP);
    assert(ufs_host_prepare(h,cdb,10,UFS_FROM_DEVICE,4096)==UFS_BUSY);
}
int main(void)
{
    struct ufs_policy p=policy();struct ufs_host h,before,other;
    uint8_t cdb[10],cqe[32],rsp[512];unsigned descriptor_cases=0,errors=0,stales=0;
    _Static_assert(sizeof(struct utp_transfer_req_desc)==32,"genuine UTRD");
    _Static_assert(sizeof(struct cq_entry)==32,"genuine CQE");
    _Static_assert(sizeof(struct ufshcd_sg_entry)==16,"genuine PRDT");
    _Static_assert(sizeof(struct utp_upiu_header)==12 && sizeof(struct utp_cmd_rsp)==40,"genuine response");
    _Static_assert(sizeof(struct e1s_ucd)==1088 && sizeof(struct e1s_ucd)%128==64,"donor stride hazard");
    const unsigned blocks[]={1,63,64,65,127,128,129,255,256};
    for(unsigned i=0;i<sizeof(blocks)/sizeof(blocks[0]);i++) {
        prepare(&h,&p,blocks[i]);struct utp_transfer_req_desc u;memcpy(&u,h.packet.utrd,sizeof(u));
        assert(u.header.dword_0==(UTP_NATIVE_UFS_COMMAND|UTP_DEVICE_TO_HOST|UTP_REQ_DESC_INT_CMD));
        assert(u.header.dword_2==15 && u.command_desc_base_addr==p.ucd_dma);
        assert(u.response_upiu_length==128 && u.response_upiu_offset==128);
        assert(u.prd_table_offset==256 && u.prd_table_length==h.packet.prdt_entries);
        unsigned consumed=0;
        for(unsigned j=0;j<u.prd_table_length;j++) {
            struct ufshcd_sg_entry e;memcpy(&e,h.packet.ucd+1024+16*j,sizeof(e));
            unsigned bytes=e.size+1;assert(bytes<=262144 && !(bytes%4));
            assert(e.addr==p.data_dma+consumed && !e.reserved);consumed+=bytes;
        }
        assert(consumed==blocks[i]*4096 && h.packet.prdt_entries==(consumed+262143)/262144);
        reserve(&h);completion(&h,cqe,rsp);assert(ufs_host_complete(&h,&h.token,cqe,32,rsp,52,1001)==UFS_OK);
        assert(h.phase==UFS_COMPLETE);assert(ufs_host_reclaim(&h,&h.token)==UFS_OK);descriptor_cases++;
    }
    /* Caller-qualified adjacent spans are legal; overlapping one byte is rejected. */
    struct ufs_policy adjacent=p;adjacent.data_dma=p.ucd_dma+1152;
    assert(ufs_host_init(&h,&adjacent)==UFS_OK);adjacent.ucd_bytes=1153;
    assert(ufs_host_init(&h,&adjacent)==UFS_DMA_RANGE);
    prepare(&h,&p,1);assert(ufs_host_cancel_prepared(&h,&h.token)==UFS_OK);before=h;
    read10(cdb,1);
    for(unsigned op=0;op<256;op++)if(op!=0x28) {
        cdb[0]=(uint8_t)op;assert(ufs_host_prepare(&h,cdb,10,UFS_FROM_DEVICE,4096)==UFS_COMMAND);
        assert(!memcmp(&h,&before,sizeof(h)));
    }
    cdb[0]=0x28;assert(ufs_host_prepare(&h,cdb,10,UFS_TO_DEVICE,4096)==UFS_WRITE_REJECTED);
    assert(!memcmp(&h,&before,sizeof(h)));
    /* Stale address/SQ/wire tags/software tokens and malformed descriptors retain lease. */
    for(unsigned mode=0;mode<8;mode++) {
        prepare(&h,&p,1);reserve(&h);completion(&h,cqe,rsp);
        struct ufs_token token=h.token;
        if(mode==0)cqe[0]^=128;
        if(mode==1)cqe[0]^=1;
        if(mode==2)rsp[2]++;
        if(mode==3)rsp[3]++;
        if(mode==4)token.epoch++;
        if(mode==5)token.generation++;
        if(mode==6)cqe[0]|=32;
        if(mode==7)cqe[12]++;
        unsigned r=ufs_host_complete(&h,&token,cqe,32,rsp,52,1001);
        assert(r==(mode<6?UFS_STALE:UFS_FORMAT));assert(h.phase==UFS_DEVICE_OWNED);held(&h);stales++;
    }
    /* Matching status, residual, flags, sense and extra-header/data fields quarantine. */
    const unsigned offsets[]={0,1,4,5,6,7,8,9,10,11,12,13,14,15,32,33};
    for(unsigned i=0;i<sizeof(offsets)/sizeof(offsets[0])+1;i++) {
        prepare(&h,&p,1);reserve(&h);completion(&h,cqe,rsp);
        if(i==sizeof(offsets)/sizeof(offsets[0]))cqe[16]=1;else rsp[offsets[i]]^=1;
        assert(ufs_host_complete(&h,&h.token,cqe,32,rsp,52,1001)==UFS_STATUS);
        assert(h.phase==UFS_QUARANTINED);held(&h);errors++;
    }
    /* Publication failure is still a device lease; no logical cancellation frees DMA. */
    prepare(&h,&p,1);reserve(&h);held(&h);completion(&h,cqe,rsp);
    assert(ufs_host_poll_timeout(&h,1499)==UFS_OK);
    assert(ufs_host_complete(&h,&h.token,cqe,32,rsp,52,1500)==UFS_TIMEOUT);
    assert(h.phase==UFS_QUARANTINED);held(&h);
    assert(ufs_host_complete(&h,&h.token,cqe,32,rsp,52,1501)==UFS_OWNERSHIP);
    /* Success also requires an explicit backend reclaim before another request. */
    prepare(&h,&p,1);reserve(&h);completion(&h,cqe,rsp);
    assert(ufs_host_complete(&h,&h.token,cqe,32,rsp,52,1001)==UFS_OK);
    read10(cdb,1);assert(ufs_host_prepare(&h,cdb,10,UFS_FROM_DEVICE,4096)==UFS_BUSY);
    struct ufs_token old=h.token;assert(ufs_host_reclaim(&h,&old)==UFS_OK);
    assert(ufs_host_prepare(&h,cdb,10,UFS_FROM_DEVICE,4096)==UFS_OK);
    assert(ufs_host_reserve_device(&h,&h.token,1002,500)==UFS_OK);
    assert(ufs_host_complete(&h,&old,cqe,32,rsp,52,1003)==UFS_STALE);
    assert(ufs_host_complete(&h,&h.token,cqe,32,rsp,52,1003)==UFS_STALE);held(&h);
    /* Deliberately violate the documented drain/exclusive-DMA precondition:
       software epochs cannot distinguish old wire bytes at reused address/tag. */
    prepare(&h,&p,1);reserve(&h);completion(&h,cqe,rsp);
    struct ufs_policy reused=p;reused.epoch++;
    prepare(&other,&reused,1);reserve(&other);
    assert(ufs_host_complete(&other,&h.token,cqe,32,rsp,52,1001)==UFS_STALE);
    assert(ufs_host_complete(&other,&other.token,cqe,32,rsp,52,1001)==UFS_OK);
    /* Actual Samsung function demonstrates why1088 cannot be an aligned pool stride. */
    uint64_t base=UINT64_C(0x100000);
    assert(actual_tag(base,1088,base+1088+31)==0); /* expected slot1 is misidentified */
    assert(actual_tag(base,1152,base+1152+31)==1);
    printf("{\"descriptor_cases\":%u,\"stale_or_format_cases\":%u,\"matching_error_cases\":%u,\"non_read_opcodes\":255,\"documented_epoch_reuse_counterexample\":true,\"documented_stride_counterexample\":true,\"hardware_io\":false}\n",descriptor_cases,stales,errors);
    return 0;
}
