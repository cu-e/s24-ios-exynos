/* Project-authored independent review fixture. No phone or hardware I/O. */
#define _GNU_SOURCE
#include "transport.h"
#include "exynos_ipc.h"
#include <assert.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
struct io_device { struct exynos_seq_num seq_num; };
struct link_device { unsigned unused; };
#include "actual-writer.c"
static void w16(uint8_t *p,unsigned v) { p[0]=(uint8_t)v;p[1]=(uint8_t)(v>>8); }
static void w64(uint8_t *p,uint64_t v) { for(unsigned i=0;i<8;i++)p[i]=(uint8_t)(v>>(i*8)); }
static void fixture(uint8_t *p,unsigned batch,unsigned type)
{
    memset(p,0,65550);p[0]=5;w16(p+3,4+14*batch);w16(p+5,4+14*batch);
    p[15]=0x37;p[16]=(uint8_t)type;w16(p+17,batch);
    for(unsigned i=0;i<batch;i++) {
        for(unsigned j=0;j<6;j++)p[19+14*i+j]=(uint8_t)(i+j);
        w64(p+25+14*i,(uint64_t)i);
    }
}
int main(void)
{
    struct sen_service ready={true,true}, no_clock={true,false}, off={false,false};
    static uint8_t bytes[65550];
    struct { unsigned prefix;struct sen_sample data[3];unsigned suffix; } output,prior;
    size_t count=42;
    fixture(bytes,3,1);w64(bytes+7,UINT64_MAX);
    memset(&output,0xa5,sizeof(output));memcpy(&prior,&output,sizeof(prior));
    for(size_t n=0;n<61;n++) {
        assert(sen_shub_report(&ready,bytes,n,10,output.data,3,&count)!=SEN_OK);
        assert(count==42 && !memcmp(&output,&prior,sizeof(output)));
    }
    assert(sen_shub_report(&ready,bytes,61,10,output.data,2,&count)==SEN_CAPACITY);
    assert(count==42 && !memcmp(&output,&prior,sizeof(output)));
    assert(sen_shub_report(&no_clock,bytes,61,10,output.data,3,&count)==SEN_UNAVAILABLE);
    assert(sen_shub_report(&off,bytes,61,10,output.data,3,&count)==SEN_UNAVAILABLE);
    assert(count==42 && !memcmp(&output,&prior,sizeof(output)));
    w64(bytes+25,0);w64(bytes+39,10);w64(bytes+53,UINT64_MAX);
    assert(sen_shub_report(&ready,bytes,sizeof(bytes),10,output.data,3,&count)==SEN_OK);
    assert(count==3 && output.prefix==prior.prefix && output.suffix==prior.suffix);
    for(unsigned i=0;i<3;i++) {
        assert(output.data[i].type==1 && output.data[i].raw[0]==i && output.data[i].raw[5]==i+5);
        assert(output.data[i].receipt_boot_ns==10);
    }
    assert(output.data[0].hub_ns==0 && output.data[0].effective_boot_ns==0 && !output.data[0].future_clamped);
    assert(output.data[1].effective_boot_ns==10 && !output.data[1].future_clamped);
    assert(output.data[2].hub_ns==UINT64_MAX && output.data[2].effective_boot_ns==10 && output.data[2].future_clamped);
    w64(bytes+25,9);w64(bytes+39,8);w64(bytes+53,7);bytes[16]=4;
    assert(sen_shub_report(&ready,bytes,61,UINT64_MAX,output.data,3,&count)==SEN_OK);
    assert(output.data[0].effective_boot_ns==9 && output.data[1].effective_boot_ns==8 && output.data[2].effective_boot_ns==7);
    memcpy(&prior,&output,sizeof(prior));count=42;
    /* Validate no publication on unsupported body, fragment, length and count cases. */
    unsigned failures=0;
    for(unsigned mode=0;mode<7;mode++) {
        fixture(bytes,3,1);
        if(mode==0)bytes[15]=0xff;
        if(mode==1)bytes[16]=8;
        if(mode==2)w16(bytes+17,0);
        if(mode==3)w16(bytes+17,65535);
        if(mode==4)w16(bytes+3,47);
        if(mode==5)w16(bytes+3,45);
        if(mode==6){w16(bytes+3,47);w16(bytes+5,47);}
        assert(sen_shub_report(&ready,bytes,65550,123,output.data,3,&count)!=SEN_OK);
        assert(count==42 && !memcmp(&output,&prior,sizeof(output)));failures++;
    }
    static struct sen_sample many[4680];
    fixture(bytes,4680,4);
    assert(sen_shub_report(&ready,bytes,65539,UINT64_MAX,many,4680,&count)==SEN_OK);
    assert(count==4680 && many[4679].hub_ns==4679 && many[4679].raw[5]==(uint8_t)(4679+5));
    /* A protected page is a valid zero-extent pointer: reject before dereference. */
    long page=sysconf(_SC_PAGESIZE);assert(page>0);
    uint8_t *guard=mmap(NULL,(size_t)page,PROT_NONE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);assert(guard!=MAP_FAILED);
    count=42;assert(sen_shub_report(&ready,guard,0,0,output.data,3,&count)==SEN_TRUNCATED);
    assert(sen_shub_report(&off,guard,0,0,output.data,3,&count)==SEN_UNAVAILABLE);
    struct sen_gnss_frame frame,previous;memset(&frame,0xa5,sizeof(frame));memcpy(&previous,&frame,sizeof(frame));
    assert(sen_gnss_frame(&ready,guard,0,&frame)==SEN_TRUNCATED);
    assert(sen_gnss_frame(&off,guard,0,&frame)==SEN_UNAVAILABLE);
    assert(!memcmp(&frame,&previous,sizeof(frame)));assert(munmap(guard,(size_t)page)==0);
    /* Actual pinned writer is the oracle, not its contradictory C struct overlay. */
    _Alignas(8) uint8_t ring[65536]={0};
    struct io_device device={0};struct link_device link={0};unsigned writer_cases=0;
    assert(offsetof(struct exynos_link_header,seq)==0 && EXYNOS_FRAME_SEQ_OFFSET==2);
    assert(offsetof(struct exynos_link_header,len)==4 && EXYNOS_LEN_OFFSET==6);
    for(unsigned length=12;length<=64;length++) {
        unsigned payload=length-12;memset(ring,0xa5,sizeof(ring));
        exynos_build_header(&device,&link,ring,EXYNOS_SINGLE_MASK<<8,0,payload);
        assert(exynos_start_valid(ring) && exynos_single_frame(ring));
        assert(exynos_get_frame_len(ring)==length && exynos_get_ch(ring)==0);
        memcpy(&previous,&frame,sizeof(frame));
        unsigned padded=exynos_get_total_len(ring);
        assert(sen_gnss_frame(&ready,ring,padded-1,&frame)==SEN_TRUNCATED);
        assert(!memcmp(&frame,&previous,sizeof(frame)));
        assert(sen_gnss_frame(&no_clock,ring,sizeof(ring),&frame)==SEN_OK); /* GNSS outer header has no clock. */
        assert(frame.payload==ring+12 && frame.payload_size==payload && frame.consumed==padded);
        assert(frame.sequence==device.seq_num.frame_cnt && frame.channel_sequence==device.seq_num.ch_cnt[0]);
        writer_cases++;
    }
    exynos_build_header(&device,&link,ring,EXYNOS_SINGLE_MASK<<8,0,65523);
    assert(sen_gnss_frame(&ready,ring,sizeof(ring),&frame)==SEN_OK && frame.consumed==65536 && frame.payload_size==65523);
    printf("{\"SHUB_prefixes\":61,\"SHUB_invalid_atomic_cases\":%u,\"SHUB_max_batch\":4680,\"actual_GNSS_writer_cases\":%u,\"GNSS_max_length\":65535,\"hardware_io\":false}\n",failures,writer_cases+1);
    return 0;
}
