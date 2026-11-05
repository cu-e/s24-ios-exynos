/* Project-authored independent camera source-review fixture; no pixel or DMA I/O. */
#include "frame.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
extern void original_sizes(unsigned,uint32_t,uint32_t,const uint32_t[2],uint32_t[3]);
extern const uint64_t measured_metadata[3];
static const uint32_t kinds[]={CAM_YUYV,CAM_NV12,CAM_NV21,CAM_NV12M,CAM_NV21M};
static struct cam_frame make(unsigned kind,uint32_t w,uint32_t h,uint32_t p0,uint32_t p1)
{
    struct cam_frame f={0};uint32_t bpl[2]={p0,p1},size[3]={0};
    original_sizes(kind,w,h,bpl,size);
    f.version=1;f.fourcc=kinds[kind];f.component_bits=8;f.width=w;f.height=h;
    f.bytesperline[0]=p0;f.bytesperline[1]=p1;f.crop_w=w;f.crop_h=h;
    f.plane_count=kind>=3?3:2;
    uint64_t end=0;
    for(unsigned i=0;i<f.plane_count;i++) { f.planes[i].offset=end;f.planes[i].capacity=size[i];end+=size[i]; }
    f.allocation_bytes=end;return f;
}
static uint64_t submit(struct cam_queue *q,struct cam_frame *f,uint64_t epoch,uint64_t now)
{
    uint64_t ticket=0;assert(cam_start(q,epoch)==CAM_OK);
    assert(cam_submit(q,epoch,f,sizeof(*f),now,10,&ticket)==CAM_OK && ticket);return ticket;
}
static void held_retirement(struct cam_queue *q,uint64_t e,uint64_t t)
{
    struct cam_frame f;struct cam_layout l;
    assert(q->phase==CAM_RETIRED && q->frame.allocation_bytes);
    assert(cam_start(q,e+1)==CAM_BUSY);
    assert(cam_release(q,e,t)==CAM_STALE);
    assert(cam_take(q,&f,&l)==CAM_STOPPED);
    assert(cam_quiesced(q,e,t+1)==CAM_STALE);
    assert(cam_quiesced(q,e,t)==CAM_OK && q->phase==CAM_IDLE && !q->active_ticket);
}
int main(void)
{
    struct cam_layout l;unsigned comparisons=0;
    assert(measured_metadata[0]==30968 && measured_metadata[1]==84 && measured_metadata[2]==6840);
    const unsigned widths[]={2,4,14,640,1920},heights[]={2,6,1080};
    for(unsigned k=0;k<5;k++)for(unsigned wi=0;wi<5;wi++)for(unsigned hi=0;hi<3;hi++)for(unsigned pad=0;pad<4;pad++) {
        uint32_t w=widths[wi],h=heights[hi],minimum=w*(k?1:2);
        uint32_t p0=pad==0?0:pad==1?minimum-1:minimum+pad*11;
        uint32_t p1=k?(pad==0?0:pad==1?w-1:w+pad*17):0;
        struct cam_frame f=make(k,w,h,p0,p1);uint32_t bpl[2]={p0,p1},size[3]={0};
        original_sizes(k,w,h,bpl,size);
        assert(cam_plan(&f,sizeof(f),&l)==CAM_OK);
        assert(l.plane_count==f.plane_count && !memcmp(l.required,size,sizeof(size)));
        for(unsigned i=0;i<f.plane_count-1;i++)f.planes[i].used=l.required[i];
        assert(cam_admit(&f,sizeof(f),&l)==CAM_OK);comparisons++;
    }
    struct cam_frame f=make(0,14,3,0,0);assert(cam_plan(&f,sizeof(f),&l)==CAM_OK); /* 4:2:2 permits odd height. */
    f.planes[1].capacity=30967;f.allocation_bytes--;assert(cam_plan(&f,sizeof(f),&l)==CAM_CAPACITY);
    f=make(0,14,3,0,0);assert(f.planes[1].capacity==30968 && cam_plan(&f,sizeof(f),&l)==CAM_OK);
    f.planes[1].capacity=32768;f.allocation_bytes+=1800;assert(cam_plan(&f,sizeof(f),&l)==CAM_OK);
    f=make(3,2,2,2000000000,1000000000);assert(cam_plan(&f,sizeof(f),&l)==CAM_OK);
    assert(l.required[0]==4000000000u && l.required[1]==1000000000u);
    f.fourcc=CAM_NV12;f.plane_count=2;assert(cam_plan(&f,sizeof(f),&l)==CAM_OVERFLOW); /* Final contiguous sum cannot wrap. */
    f=make(3,2,2,0,0);f.width=536870912;f.crop_w=f.width;
    assert(cam_plan(&f,sizeof(f),&l)==CAM_OVERFLOW); /* width*8 overflows donor u32 before /8. */
    f=make(0,2,1,0,0);f.width=268435456;f.crop_w=f.width;
    assert(cam_plan(&f,sizeof(f),&l)==CAM_OVERFLOW); /* width*16 intermediate. */
    f=make(3,2,2,0,0);f.bytesperline[1]=UINT32_MAX;
    assert(cam_plan(&f,sizeof(f),&l)==CAM_OVERFLOW); /* Reject product before chroma /2. */
    f=make(0,2,1,0,0);f.height=UINT32_MAX;f.crop_h=f.height;
    assert(cam_plan(&f,sizeof(f),&l)==CAM_OVERFLOW);
    f=make(1,14,6,0,0);f.crop_x=UINT32_MAX;assert(cam_plan(&f,sizeof(f),&l)==CAM_CROP);
    f=make(1,14,6,0,0);f.crop_y=1;f.crop_h=4;assert(cam_plan(&f,sizeof(f),&l)==CAM_CROP);
    f=make(1,14,6,0,0);f.crop_x=2;f.crop_w=12;assert(cam_plan(&f,sizeof(f),&l)==CAM_OK);
    /* Reserved padding overlaps metadata even when required payloads do not. */
    f=make(0,14,3,0,0);f.planes[0].capacity+=8;f.allocation_bytes+=8;
    assert(cam_plan(&f,sizeof(f),&l)==CAM_OVERLAP);
    f=make(0,14,3,0,0);f.allocation_bytes=UINT64_MAX;f.planes[0].offset=UINT64_MAX-f.planes[0].capacity;
    f.planes[1].offset=0;assert(cam_plan(&f,sizeof(f),&l)==CAM_OK);
    f.planes[0].offset=UINT64_MAX-1;assert(cam_plan(&f,sizeof(f),&l)==CAM_CAPACITY);
    f=make(4,14,6,0,0);uint8_t unaligned[sizeof(f)+1];memcpy(unaligned+1,&f,sizeof(f));
    assert(cam_plan(unaligned+1,sizeof(f),&l)==CAM_OK);
    for(size_t n=0;n<sizeof(f);n++)assert(cam_plan(unaligned+1,n,&l)==CAM_TRUNCATED);
    /* Descriptor/count copies are snapshots; they do not copy image contents. */
    struct cam_queue q={0};f=make(4,14,6,0,0);struct cam_frame original=f,taken;
    uint64_t t=submit(&q,&f,10,100),used[3]={f.planes[0].capacity,f.planes[1].capacity,0};
    f.width=UINT32_MAX;f.planes[0].capacity=0;
    assert(q.frame.width==14 && q.frame.planes[0].capacity==original.planes[0].capacity);
    assert(cam_complete(&q,10,t,used,sizeof(used),0,101)==CAM_OK);used[0]=0;
    assert(cam_take(&q,&taken,&l)==CAM_OK && taken.width==14 && taken.planes[0].used==original.planes[0].capacity);
    taken.planes[0].used=0;assert(q.frame.planes[0].used==original.planes[0].capacity);
    cam_stop(&q);assert(q.phase==CAM_HELD && cam_start(&q,11)==CAM_BUSY);
    assert(cam_quiesced(&q,10,t)==CAM_STALE);assert(cam_release(&q,10,t)==CAM_OK);
    assert(cam_start(&q,10)==CAM_STALE && cam_start(&q,11)==CAM_OK);
    uint64_t next;assert(cam_submit(&q,11,&original,sizeof(original),200,10,&next)==CAM_OK && next==t);
    uint64_t oldcounts[3]={original.planes[0].capacity,original.planes[1].capacity,0};
    assert(cam_complete(&q,10,t,oldcounts,sizeof(oldcounts),0,201)==CAM_STALE && q.phase==CAM_INFLIGHT);
    cam_stop(&q);held_retirement(&q,11,next);
    q=(struct cam_queue){0};f=original;t=submit(&q,&f,20,300);
    assert(cam_complete(&q,20,t,NULL,0,1,301)==CAM_PRODUCER_ERROR);held_retirement(&q,20,t);
    q=(struct cam_queue){0};t=submit(&q,&f,30,400);oldcounts[0]=0;
    assert(cam_complete(&q,30,t,oldcounts,sizeof(oldcounts),0,401)==CAM_TRUNCATED);held_retirement(&q,30,t);
    q=(struct cam_queue){0};t=submit(&q,&f,40,500);
    assert(cam_poll(&q,509)==CAM_OK && cam_poll(&q,510)==CAM_TIMEOUT);held_retirement(&q,40,t);
    q=(struct cam_queue){0};t=submit(&q,&f,50,600);oldcounts[0]=f.planes[0].capacity;
    assert(cam_complete(&q,50,t,oldcounts,sizeof(oldcounts),0,601)==CAM_OK);cam_stop(&q);held_retirement(&q,50,t);
    printf("{\"genuine_size_cases\":%u,\"metadata_bytes\":%llu,\"descriptor_prefixes\":%zu,\"snapshot_controls\":3,\"lifecycle_groups\":5,\"camera_io\":false}\n",comparisons,(unsigned long long)measured_metadata[0],sizeof(f));
    return 0;
}
