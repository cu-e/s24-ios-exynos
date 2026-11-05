/* Independent owned review fixture, no DSP/PCM/DMA operations. */
#include "pcm_host.h"
#include "oracle_api.h"
#include "abox_ipc.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static struct pcm_plan plan(unsigned dir,unsigned fmt,unsigned channels,unsigned period,unsigned periods)
{
    ABOX_IPC_MSG s,h;struct pcm_plan p;
    oracle_message(dir,0,fmt,48000,channels,period,periods,0,&s);
    oracle_message(dir,1,fmt,48000,channels,period,periods,0,&h);
    struct pcm_mapping map={dir?0x92000000u:0x91000000u,0x100000};
    assert(pcm_admit_plan(&s,sizeof(s),&h,sizeof(h),map,&p)==PCM_OK);return p;
}
static void event_message(unsigned dir,unsigned kind,unsigned pointer,ABOX_IPC_MSG *out)
{ oracle_message(dir,kind,0,48000,2,4096,4,pointer,out); }
int main(int argc,char **argv)
{
    if(argc==2 && argv[1][0]=='f') { (void)oracle_pointer(0,64,0x90ffffffu);return 99; }
    _Static_assert(sizeof(ABOX_IPC_MSG)==768,"genuine AP snapshot");
    _Static_assert(sizeof(struct IPC_PCMTASK_MSG)==88,"genuine PCM task");
    _Static_assert(sizeof(struct PCMTASK_SET_BUFFER)==24,"genuine period/count");
    assert(oracle_value(4)==16 && oracle_value(5)==32);
    unsigned cases=0,pointers=0;
    for(unsigned dir=0;dir<2;dir++)for(unsigned fmt=0;fmt<4;fmt++)for(unsigned channels=1;channels<=8;channels++) {
        unsigned frame=oracle_physical_width(fmt)/8*channels;
        unsigned period=frame*16;struct pcm_plan p=plan(dir,fmt,channels,period,4);
        assert(p.period_bytes==period && p.periods==4 && p.ring_bytes==(uint64_t)period*4 && p.frame_bytes==frame);
        for(unsigned position=0;position<16;position++) {
            uint64_t got=UINT64_MAX;uint32_t absolute=p.iova+position*frame;
            assert(pcm_offset_frames(&p,absolute,&got)==PCM_OK && got==position);
            assert(got==oracle_pointer(dir,frame*8,absolute));pointers++;
        }
        uint64_t sentinel=UINT64_MAX;
        assert(pcm_offset_frames(&p,p.iova+(uint32_t)p.ring_bytes,&sentinel)==PCM_INVALID && sentinel==UINT64_MAX);
        assert(pcm_offset_frames(&p,p.iova-1,&sentinel)==PCM_INVALID);
        assert(pcm_offset_frames(&p,p.iova+1,&sentinel)==PCM_INVALID);
        assert(oracle_pointer(dir,frame*8,p.iova+1)==0); /* Genuine source floors; owned profile rejects misalignment. */
        cases++;
    }
    struct pcm_plan unpacked=plan(0,1,2,192,4),packed=plan(0,2,2,192,4);
    uint64_t frames;assert(unpacked.bits==24 && unpacked.frame_bytes==8 && packed.frame_bytes==6);
    assert(pcm_offset_frames(&unpacked,unpacked.iova+24,&frames)==PCM_OK && frames==3);
    assert(pcm_offset_frames(&packed,packed.iova+24,&frames)==PCM_OK && frames==4);
    ABOX_IPC_MSG s,h;oracle_message(0,0,0,48000,2,262144,4,0,&s);oracle_message(0,1,0,48000,2,262144,4,0,&h);
    struct pcm_plan p,prior;struct pcm_mapping map={0x91000000u,1048576};
    assert(pcm_admit_plan(&s,sizeof(s),&h,sizeof(h),map,&p)==PCM_OK && p.ring_bytes==1048576 && p.period_bytes==262144);
    memset(&p,0xa5,sizeof(p));memcpy(&prior,&p,sizeof(p));s.msg.pcmtask.param.setbuff.size=1048576;
    assert(pcm_admit_plan(&s,sizeof(s),&h,sizeof(h),map,&p)==PCM_INVALID && !memcmp(&p,&prior,sizeof(p)));
    s.msg.pcmtask.param.setbuff.size=262144;
    for(size_t n=0;n<sizeof(s);n++)assert(pcm_admit_plan(&s,n,&h,sizeof(h),map,&p)==PCM_INVALID);
    assert(pcm_admit_plan(&s,sizeof(s),&h,sizeof(h),map,&p)==PCM_OK);
    struct pcm_host host;pcm_host_init(&host);assert(pcm_host_bind(&host,&p,10)==PCM_OK);
    p.frame_bytes=1;assert(host.plan.frame_bytes==4);assert(pcm_host_start(&host,10)==PCM_OK);
    struct pcm_lease lease;assert(pcm_host_claim(&host,10,0,&lease)==PCM_OK);
    ABOX_IPC_MSG msg;event_message(0,2,host.plan.iova+4,&msg);uint64_t count=999;
    assert(pcm_host_event(&host,(struct pcm_stamp){10,1,0},&msg,sizeof(msg),&count)==PCM_OK && count==1 && host.leased);
    assert(pcm_host_event(&host,(struct pcm_stamp){10,1,0},&msg,sizeof(msg),&count)==PCM_DUPLICATE);
    struct pcm_stop_token stop,again;assert(pcm_host_stop(&host,10,&stop)==PCM_OK);
    assert(pcm_host_stop(&host,10,&again)==PCM_OK && again.serial==stop.serial);
    event_message(0,3,0,&msg);assert(pcm_host_event(&host,(struct pcm_stamp){10,2,stop.serial},&msg,sizeof(msg),NULL)==PCM_OK);
    assert(pcm_host_provider_fenced(&host,stop)==PCM_BUSY && pcm_host_release(&host,10)==PCM_BUSY);
    struct pcm_lease forged=lease;forged.bytes++;
    assert(pcm_host_retire(&host,&forged,0)==PCM_INVALID && host.leased);
    assert(pcm_host_retire(&host,&lease,-5)==PCM_OK && host.state==PCM_FAULT && !host.closed);
    assert(pcm_host_provider_fenced(&host,stop)==PCM_STATE);
    assert(pcm_host_stop(&host,10,&again)==PCM_OK && again.serial>stop.serial);
    assert(pcm_host_event(&host,(struct pcm_stamp){10,3,stop.serial},&msg,sizeof(msg),NULL)==PCM_STALE);
    assert(pcm_host_event(&host,(struct pcm_stamp){10,3,again.serial},&msg,sizeof(msg),NULL)==PCM_OK);
    assert(pcm_host_provider_fenced(&host,again)==PCM_OK && pcm_host_release(&host,10)==PCM_OK);
    p=unpacked;assert(pcm_host_bind(&host,&p,10)==PCM_STALE && pcm_host_bind(&host,&p,11)==PCM_OK);
    assert(pcm_host_retire(&host,&lease,0)==PCM_STALE);
    /* Concrete initializer contract counterexample: no documented fresh-only
       premise currently prevents reset from discarding a live reservation. */
    struct pcm_host reset;pcm_host_init(&reset);assert(pcm_host_bind(&reset,&unpacked,1)==PCM_OK && pcm_host_start(&reset,1)==PCM_OK);
    struct pcm_lease old,newer;assert(pcm_host_claim(&reset,1,0,&old)==PCM_OK && reset.leased);
    pcm_host_init(&reset);assert(!reset.leased && reset.state==PCM_IDLE);
    assert(pcm_host_bind(&reset,&unpacked,1)==PCM_OK && pcm_host_start(&reset,1)==PCM_OK);
    assert(pcm_host_claim(&reset,1,0,&newer)==PCM_OK);
    assert(old.epoch==newer.epoch && old.serial==newer.serial && old.slot==newer.slot && old.offset==newer.offset && old.bytes==newer.bytes);
    assert(pcm_host_retire(&reset,&old,0)==PCM_OK && !reset.leased);
    printf("{\"source_plan_cases\":%u,\"source_pointer_cases\":%u,\"snapshot_prefixes\":%zu,\"live_reinit_old_lease_alias\":true,\"DSP_executed\":false}\n",cases,pointers,sizeof(s));
    return 0;
}
