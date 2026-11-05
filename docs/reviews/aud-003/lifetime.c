/* Focused independent legal reconstruction check; no DSP or DMA. */
#include "pcm_host.h"
#include "abox_ipc.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static void teardown(struct pcm_host *h,uint64_t epoch,const struct pcm_lease *lease)
{
    struct pcm_stop_token stop;ABOX_IPC_MSG message;memset(&message,0xa5,sizeof(message));
    message.ipcid=IPC_PCMPLAYBACK;message.msg.pcmtask.channel_id=0;message.msg.pcmtask.msgtype=PCM_PLTDAI_CLOSED;
    assert(pcm_host_stop(h,epoch,&stop)==PCM_OK);
    assert(pcm_host_retire(h,lease,0)==PCM_OK);
    assert(pcm_host_event(h,(struct pcm_stamp){epoch,1,stop.serial},&message,sizeof(message),NULL)==PCM_OK);
    /* No real backend or borrowed mapping view exists in this host fixture. */
    assert(pcm_host_provider_fenced(h,stop)==PCM_OK);
    assert(pcm_host_release(h,epoch)==PCM_OK && h->state==PCM_IDLE && !h->leased);
}
int main(void)
{
    const struct pcm_plan plan={.direction=PCM_HOST_PLAYBACK,.channel=0,.iova=0x91000000,
        .period_bytes=4096,.periods=4,.rate=48000,.bits=16,.channels=2,.packed=0,
        .frame_bytes=4,.ring_bytes=16384,.mapping_bytes=1048576};
    struct pcm_host host;struct pcm_lease old,current;uint64_t external_epoch=41;
    pcm_host_init(&host);assert(pcm_host_bind(&host,&plan,external_epoch)==PCM_OK);
    assert(pcm_host_start(&host,external_epoch)==PCM_OK && pcm_host_claim(&host,external_epoch,0,&old)==PCM_OK);
    teardown(&host,external_epoch,&old);
    pcm_host_init(&host);++external_epoch;
    assert(pcm_host_bind(&host,&plan,external_epoch)==PCM_OK && pcm_host_start(&host,external_epoch)==PCM_OK);
    assert(pcm_host_claim(&host,external_epoch,0,&current)==PCM_OK);
    assert(old.serial==1 && current.serial==1 && old.slot==0 && current.slot==0 && old.epoch==41 && current.epoch==42);
    unsigned char before[sizeof(host)];memcpy(before,&host,sizeof(host));
    assert(pcm_host_retire(&host,&old,0)==PCM_STALE && !memcmp(before,&host,sizeof(host)));
    struct pcm_lease blocked;assert(pcm_host_claim(&host,external_epoch,0,&blocked)==PCM_BUSY);
    teardown(&host,external_epoch,&current);
    puts("{\"legal_reconstruction\":true,\"epochs\":[41,42],\"same_slot_serial\":true,\"old_token_stale\":true,\"new_ownership_unchanged\":true,\"fully_released\":true,\"DSP_executed\":false}");
    return 0;
}
