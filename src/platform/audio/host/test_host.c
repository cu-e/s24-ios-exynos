/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "pcm_host.h"
#include "oracle_api.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static uint64_t assertions, plans, pointer_vectors, mutations;
#define CHECK(x) do { ++assertions; if (!(x)) { fprintf(stderr,"line%d: %s\n",__LINE__,#x); exit(1); } } while (0)
static uint32_t random_state = 0x7a183b41u;
static uint32_t next(void) { random_state ^= random_state<<13; random_state ^= random_state>>17; random_state ^= random_state<<5; return random_state; }
static void put(void *v, unsigned at, uint32_t x) { unsigned char *p=v; for(unsigned i=0;i<4;i++) p[at+i]=(unsigned char)(x>>(i*8)); }

static struct pcm_plan plan(unsigned d, unsigned f, unsigned ch, unsigned period, unsigned count)
{
    unsigned char a[PCM_AP_MESSAGE_BYTES], b[PCM_AP_MESSAGE_BYTES];
    struct pcm_plan p;
    oracle_message(d,0,f,48000,ch,period,count,0,a);
    oracle_message(d,1,f,48000,ch,period,count,0,b);
    CHECK(pcm_admit_plan(a,sizeof(a),b,sizeof(b),(struct pcm_mapping){d?0x92000000:0x91000000,0x100000},&p)==PCM_OK);
    return p;
}

static void reject_plan(const void *a,size_t an,const void *b,size_t bn,struct pcm_mapping m)
{
    struct pcm_plan out;
    unsigned char saved[sizeof(out)]; memset(&out,0xc6,sizeof(out)); memcpy(saved,&out,sizeof(out));
    CHECK(pcm_admit_plan(a,an,b,bn,m,&out)!=PCM_OK);
    CHECK(!memcmp(saved,&out,sizeof(out)));
}

static void vectors(void)
{
    CHECK(oracle_value(0)==PCM_AP_MESSAGE_BYTES);
    CHECK(oracle_value(1)==88 && oracle_value(2)==24 && oracle_value(3)==20);
    CHECK(oracle_value(4)==16 && oracle_value(5)==32 && oracle_value(17)==4);
    CHECK(oracle_value(6)==2 && oracle_value(7)==3 && oracle_value(8)==20 && oracle_value(9)==14);
    CHECK(oracle_value(10)==18 && oracle_value(11)==23);
    CHECK(oracle_value(12)==0x100000 && oracle_value(13)==16 && oracle_value(14)==0x80000);
    CHECK(oracle_value(15)==0x91000000 && oracle_value(16)==0x92000000);
    const unsigned counts[]={2,3,4,8,16,32}, frames[]={1,3,32,127,1024};
    for(unsigned d=0;d<2;d++) for(unsigned f=0;f<4;f++) for(unsigned ch=1;ch<=8;ch++)
    for(unsigned ci=0;ci<6;ci++) for(unsigned fi=0;fi<5;fi++) {
        unsigned bits=oracle_physical_width(f)*ch;
        unsigned period=(unsigned)oracle_frame_bytes(bits,frames[fi]);
        while(period<16) period+=(bits/8);
        if((uint64_t)period*counts[ci]>0x100000) continue;
        struct pcm_plan p=plan(d,f,ch,period,counts[ci]); ++plans;
        CHECK(p.frame_bytes==bits/8 && p.bits==oracle_width(f));
        CHECK(p.ring_bytes==(uint64_t)period*counts[ci] && p.period_bytes==period);
        for(unsigned j=0;j<64;j++) {
            unsigned offset=(next()%(p.ring_bytes/p.frame_bytes))*p.frame_bytes;
            uint64_t got=UINT64_MAX;
            CHECK(pcm_offset_frames(&p,p.iova+offset,&got)==PCM_OK);
            CHECK(got==oracle_pointer(d,bits,p.iova+offset)); ++pointer_vectors;
        }
        uint64_t untouched=UINT64_MAX;
        CHECK(pcm_offset_frames(&p,p.iova-1,&untouched)==PCM_INVALID && untouched==UINT64_MAX);
        CHECK(pcm_offset_frames(&p,p.iova+(uint32_t)p.ring_bytes,&untouched)==PCM_INVALID && untouched==UINT64_MAX);
        CHECK(pcm_offset_frames(&p,p.iova+1,&untouched)==PCM_INVALID && untouched==UINT64_MAX);
    }
}

static void invalid_inputs(void)
{
    unsigned char a[PCM_AP_MESSAGE_BYTES],b[PCM_AP_MESSAGE_BYTES],bad[PCM_AP_MESSAGE_BYTES],unaligned[PCM_AP_MESSAGE_BYTES+1];
    oracle_message(0,0,1,48000,2,4096,4,0,a); oracle_message(0,1,1,48000,2,4096,4,0,b);
    struct pcm_mapping m={0x91000000,0x100000};
    for(size_t n=0;n<PCM_AP_MESSAGE_BYTES;n++) { reject_plan(a,n,b,sizeof(b),m); reject_plan(a,sizeof(a),b,n,m); }
    reject_plan(a,sizeof(a)+1,b,sizeof(b),m); reject_plan(NULL,sizeof(a),b,sizeof(b),m);
    reject_plan(a,sizeof(a),NULL,sizeof(b),m);
    const struct { unsigned hw,at; uint32_t value; } invalid[]={
        {0,0,0},{0,0,1},{0,0,4},{0,4,1},{0,4,UINT32_MAX},{0,8,18},{0,8,14},
        {0,12,1},{0,12,UINT32_MAX},{0,16,0},{0,16,UINT32_MAX},{0,16,0x92000000},
        {0,20,0},{0,20,1},{0,20,15},{0,20,17},{0,20,0x80001},{0,20,UINT32_MAX},
        {0,24,0},{0,24,1},{0,24,33},{0,24,UINT32_MAX},
        {1,0,0},{1,0,3},{1,4,1},{1,8,20},{1,12,1},{1,16,0},{1,16,0x80000000u},
        {1,20,0},{1,20,8},{1,20,64},{1,24,0},{1,24,9},{1,24,UINT32_MAX},
        {1,28,2},{1,28,UINT32_MAX}};
    for(unsigned i=0;i<sizeof(invalid)/sizeof(invalid[0]);i++) {
        memcpy(bad,invalid[i].hw?b:a,sizeof(bad));put(bad,invalid[i].at,invalid[i].value);
        if(invalid[i].hw) reject_plan(a,sizeof(a),bad,sizeof(bad),m);
        else reject_plan(bad,sizeof(bad),b,sizeof(b),m);
    }
    const uint64_t extents[]={0,1,16383,0x100001,UINT64_MAX};
    for(unsigned i=0;i<5;i++) reject_plan(a,sizeof(a),b,sizeof(b),(struct pcm_mapping){m.iova,extents[i]});
    reject_plan(a,sizeof(a),b,sizeof(b),(struct pcm_mapping){UINT64_MAX,m.bytes});
    reject_plan(a,sizeof(a),b,sizeof(b),(struct pcm_mapping){m.iova+1,m.bytes});
    memcpy(unaligned+1,a,sizeof(a)); struct pcm_plan p;
    CHECK(pcm_admit_plan(unaligned+1,sizeof(a),b,sizeof(b),m,&p)==PCM_OK);
    /* Unused phys/ip_type/padding remain 0xa5 from the actual source builder. */
    CHECK(pcm_admit_plan(a,sizeof(a),b,sizeof(b),m,&p)==PCM_OK);
    for(unsigned i=0;i<20000;i++) {
        memcpy(bad,(i&1)?a:b,sizeof(bad)); unsigned at=next()%sizeof(bad); bad[at]^=(unsigned char)(1u<<(next()%8));
        struct pcm_plan out; memset(&out,0x9c,sizeof(out)); unsigned char saved[sizeof(out)];memcpy(saved,&out,sizeof(out));
        int result=(i&1)?pcm_admit_plan(bad,sizeof(bad),b,sizeof(b),m,&out):pcm_admit_plan(a,sizeof(a),bad,sizeof(bad),m,&out);
        if(result==PCM_OK) { uint64_t x;CHECK(pcm_offset_frames(&out,out.iova,&x)==PCM_OK && x==0); }
        else CHECK(!memcmp(saved,&out,sizeof(out)));
        ++mutations;
    }
}

static void lifecycle(void)
{
    struct pcm_host h; pcm_host_init(&h);struct pcm_plan p=plan(0,0,2,4096,4);
    struct pcm_lease leases[4],bad;struct pcm_stop_token stop,oldstop;
    unsigned char message[PCM_AP_MESSAGE_BYTES]; uint64_t frames=UINT64_MAX;
    CHECK(pcm_host_bind(&h,&p,1)==PCM_OK);
    CHECK(pcm_host_claim(&h,1,0,&leases[0])==PCM_STATE);
    CHECK(pcm_host_start(&h,2)==PCM_STALE);CHECK(pcm_host_start(&h,1)==PCM_OK);
    for(unsigned i=0;i<4;i++) { CHECK(pcm_host_claim(&h,1,i,&leases[i])==PCM_OK);CHECK(leases[i].offset==i*4096 && leases[i].bytes==4096); }
    CHECK(pcm_host_claim(&h,1,3,&bad)==PCM_BUSY);CHECK(pcm_host_claim(&h,1,32,&bad)==PCM_INVALID);
    bad=leases[0];++bad.serial;CHECK(pcm_host_retire(&h,&bad,0)==PCM_STALE);
    bad=leases[0];++bad.bytes;CHECK(pcm_host_retire(&h,&bad,0)==PCM_INVALID);
    CHECK(pcm_host_retire(&h,&leases[0],1)==PCM_INVALID);
    oracle_message(0,2,0,48000,2,4096,4,p.iova,message);put(message,4,UINT32_MAX);
    CHECK(pcm_host_event(&h,(struct pcm_stamp){1,1,0},message,sizeof(message),&frames)==PCM_OK && frames==0);
    CHECK(pcm_host_event(&h,(struct pcm_stamp){1,1,0},message,sizeof(message),&frames)==PCM_DUPLICATE);
    CHECK(pcm_host_event(&h,(struct pcm_stamp){1,2,0},message,sizeof(message),&frames)==PCM_OK); /* same position can be a later ring wrap */
    CHECK(pcm_host_stop(&h,1,&stop)==PCM_OK);oldstop=stop;
    CHECK(pcm_host_stop(&h,1,&oldstop)==PCM_OK && oldstop.serial==stop.serial);
    CHECK(pcm_host_claim(&h,1,0,&bad)==PCM_STATE);
    CHECK(pcm_host_event(&h,(struct pcm_stamp){1,3,0},message,sizeof(message),&frames)==PCM_STATE);
    CHECK(pcm_host_release(&h,1)==PCM_BUSY);CHECK(pcm_host_provider_fenced(&h,stop)==PCM_BUSY);
    oracle_message(0,3,0,48000,2,4096,4,0,message);
    CHECK(pcm_host_event(&h,(struct pcm_stamp){1,3,stop.serial},message,sizeof(message),NULL)==PCM_OK);
    CHECK(pcm_host_provider_fenced(&h,stop)==PCM_BUSY); /* CLOSED does not release leased buffers */
    CHECK(pcm_host_retire(&h,&leases[0],0)==PCM_OK);CHECK(pcm_host_retire(&h,&leases[0],0)==PCM_DUPLICATE);
    CHECK(pcm_host_retire(&h,&leases[1],-5)==PCM_OK && h.state==PCM_FAULT && !h.closed);
    CHECK(pcm_host_stop(&h,1,&stop)==PCM_OK && stop.serial!=oldstop.serial);
    CHECK(pcm_host_event(&h,(struct pcm_stamp){1,4,oldstop.serial},message,sizeof(message),NULL)==PCM_STALE);
    CHECK(pcm_host_retire(&h,&leases[2],0)==PCM_OK);CHECK(pcm_host_retire(&h,&leases[3],0)==PCM_OK);
    CHECK(pcm_host_event(&h,(struct pcm_stamp){1,4,stop.serial},message,sizeof(message),NULL)==PCM_OK);
    CHECK(pcm_host_provider_fenced(&h,oldstop)==PCM_STALE);CHECK(pcm_host_provider_fenced(&h,stop)==PCM_OK);
    CHECK(pcm_host_release(&h,1)==PCM_OK && h.state==PCM_IDLE);
    CHECK(pcm_host_bind(&h,&p,1)==PCM_STALE);CHECK(pcm_host_bind(&h,&p,2)==PCM_OK);CHECK(pcm_host_start(&h,2)==PCM_OK);
    CHECK(pcm_host_retire(&h,&leases[3],0)==PCM_STALE);
    CHECK(pcm_host_event(&h,(struct pcm_stamp){1,5,stop.serial},message,sizeof(message),NULL)==PCM_STALE);
    CHECK(pcm_host_fault(&h,2,-11)==PCM_OK);CHECK(pcm_host_release(&h,2)==PCM_BUSY);
    CHECK(pcm_host_stop(&h,2,&stop)==PCM_OK);
    CHECK(pcm_host_event(&h,(struct pcm_stamp){2,1,stop.serial},message,sizeof(message),NULL)==PCM_OK);
    CHECK(pcm_host_provider_fenced(&h,stop)==PCM_OK);CHECK(pcm_host_release(&h,2)==PCM_OK);
    CHECK(pcm_host_bind(&h,&p,UINT64_MAX)==PCM_OK && pcm_host_start(&h,UINT64_MAX)==PCM_OK);
    h.issued=UINT64_MAX;CHECK(pcm_host_claim(&h,UINT64_MAX,0,&bad)==PCM_LIMIT);
    h.stop_serial=UINT64_MAX;CHECK(pcm_host_stop(&h,UINT64_MAX,&stop)==PCM_LIMIT && h.state==PCM_RUNNING);
    h.dispatch=UINT64_MAX;oracle_message(0,2,0,48000,2,4096,4,p.iova,message);
    CHECK(pcm_host_event(&h,(struct pcm_stamp){UINT64_MAX,UINT64_MAX,0},message,sizeof(message),&frames)==PCM_DUPLICATE);
}

static void event_adversaries(void)
{
    struct pcm_plan p=plan(1,2,3,4608,8);unsigned char canonical[PCM_AP_MESSAGE_BYTES],message[PCM_AP_MESSAGE_BYTES];
    oracle_message(1,2,2,48000,3,4608,8,p.iova+9,canonical);
    struct pcm_host valid;pcm_host_init(&valid);uint64_t first=UINT64_MAX;
    CHECK(pcm_host_bind(&valid,&p,1)==PCM_OK && pcm_host_start(&valid,1)==PCM_OK);
    CHECK(pcm_host_event(&valid,(struct pcm_stamp){1,1,0},canonical,sizeof(canonical),&first)==PCM_OK && first==1);
    for(unsigned i=0;i<20000;i++) {
        struct pcm_host h;pcm_host_init(&h);CHECK(pcm_host_bind(&h,&p,1)==PCM_OK);CHECK(pcm_host_start(&h,1)==PCM_OK);
        memcpy(message,canonical,sizeof(message));
        unsigned mode=i%8;size_t n=sizeof(message);struct pcm_stamp stamp={1,1,0};
        uint32_t candidate=next();int expected_ok=0;
        if(mode==0) { put(message,16,candidate);expected_ok=candidate>=p.iova && (uint64_t)candidate-p.iova<p.ring_bytes && (candidate-p.iova)%p.frame_bytes==0; }
        if(mode==1) { put(message,0,candidate);expected_ok=candidate==3; }
        if(mode==2) { put(message,8,candidate);expected_ok=candidate==18; }
        if(mode==3) { put(message,12,candidate);expected_ok=candidate==0; }
        if(mode==4) n=next()%PCM_AP_MESSAGE_BYTES;
        if(mode==5) stamp.epoch=2;
        if(mode==6) stamp.sequence=0;
        if(mode==7) stamp.stop_serial=1;
        unsigned char before[sizeof(h)];memcpy(before,&h,sizeof(h));uint64_t f=UINT64_MAX;
        int rc=pcm_host_event(&h,stamp,message,n,&f);
        CHECK((rc==PCM_OK)==expected_ok);
        if(rc!=PCM_OK) { CHECK(!memcmp(before,&h,sizeof(h)));CHECK(f==UINT64_MAX); }
        else CHECK(f<p.ring_bytes/p.frame_bytes && h.notifications==1);
        ++mutations;
    }
}

int main(void)
{
    vectors();invalid_inputs();lifecycle();event_adversaries();
    printf("{\"outcome\":\"pass\",\"assertions\":%llu,\"valid_plans\":%llu,\"source_pointer_vectors\":%llu,\"mutation_cases\":%llu,\"device_executed\":false}\n",
      (unsigned long long)assertions,(unsigned long long)plans,(unsigned long long)pointer_vectors,(unsigned long long)mutations);
    return 0;
}
