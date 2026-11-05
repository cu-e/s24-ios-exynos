#include "frame.h"

static void copy_bytes(void *dst, const void *src, size_t n) {
    uint8_t *d=dst; const uint8_t *s=src;
    for(size_t i=0;i<n;++i)d[i]=s[i];
}
static int decode(const void *input, size_t bytes, struct cam_frame *frame) {
    if(!input || bytes!=sizeof(*frame))return 0;
    copy_bytes(frame,input,sizeof(*frame));return 1;
}
static enum cam_result validate(const struct cam_frame *f, int completed, struct cam_layout *l) {
    uint32_t bpp, images; uint64_t pitch[2],full[2],size[2]; int yuyv;
    if(f->version!=CAM_DESCRIPTOR_VERSION || f->reserved)return CAM_FORMAT;
    if(f->component_bits!=8 || f->compression)return CAM_FORMAT;
    yuyv=f->fourcc==CAM_YUYV;
    if(!yuyv && f->fourcc!=CAM_NV12 && f->fourcc!=CAM_NV21 &&
       f->fourcc!=CAM_NV12M && f->fourcc!=CAM_NV21M)return CAM_FORMAT;
    bpp=yuyv?16:8;images=(f->fourcc==CAM_NV12M || f->fourcc==CAM_NV21M)?2:1;
    if(!f->width || !f->height || (f->width&1) || (!yuyv && (f->height&1)))return CAM_GEOMETRY;
    /* Preserve the safe domain of donor u32 multiplication before division. */
    if(f->width>UINT32_MAX/bpp)return CAM_OVERFLOW;
    if(f->plane_count!=images+1 || !f->allocation_bytes)return CAM_CAPACITY;
    if(yuyv && f->bytesperline[1])return CAM_GEOMETRY;
    for(unsigned p=0;p<(yuyv?1u:2u);++p) {
        uint64_t minimum=(uint64_t)f->width*bpp/8;
        pitch[p]=f->bytesperline[p]>minimum?f->bytesperline[p]:minimum;
        full[p]=pitch[p]*f->height;
        if(full[p]>UINT32_MAX)return CAM_OVERFLOW;
    }
    size[0]=full[0];size[1]=0;
    if(!yuyv) {
        if(images==1)size[0]+=full[1]/2;
        else size[1]=full[1]/2;
    }
    if(size[0]>UINT32_MAX)return CAM_OVERFLOW;
    if(!f->crop_w || !f->crop_h || f->crop_x>f->width || f->crop_y>f->height ||
       f->crop_w>f->width-f->crop_x || f->crop_h>f->height-f->crop_y)return CAM_CROP;
    /* Conservative owned policy: whole chroma groups, no repacking implied. */
    if((f->crop_x|f->crop_w)&1)return CAM_CROP;
    if(!yuyv && ((f->crop_y|f->crop_h)&1))return CAM_CROP;
    l->stride[0]=(uint32_t)pitch[0];l->stride[1]=yuyv?0:(uint32_t)pitch[1];
    l->required[0]=(uint32_t)size[0];l->required[1]=(uint32_t)size[1];
    l->required[images]=CAM_METADATA_BYTES;l->plane_count=images+1;
    for(unsigned p=0;p<f->plane_count;++p) {
        const struct cam_plane *plane=&f->planes[p];
        if(plane->offset>f->allocation_bytes || plane->capacity>f->allocation_bytes-plane->offset ||
           plane->capacity<l->required[p] || plane->used>plane->capacity)return CAM_CAPACITY;
        if(completed && p<images && plane->used<l->required[p])return CAM_TRUNCATED;
        for(unsigned prior=0;prior<p;++prior) {
            const struct cam_plane *other=&f->planes[prior];
            if(plane->offset<other->offset+other->capacity && other->offset<plane->offset+plane->capacity)return CAM_OVERLAP;
        }
    }
    for(unsigned p=f->plane_count;p<CAM_PLANES;++p)
        if(f->planes[p].offset || f->planes[p].capacity || f->planes[p].used)return CAM_FORMAT;
    return CAM_OK;
}
static enum cam_result inspect(const void *input,size_t bytes,struct cam_layout *out,int complete) {
    struct cam_frame f;struct cam_layout layout={0};enum cam_result result;
    if(!out)return CAM_ARGUMENT;
    if(!decode(input,bytes,&f)){*out=layout;return CAM_TRUNCATED;}
    result=validate(&f,complete,&layout);
    if(result==CAM_OK)*out=layout;else {struct cam_layout zero={0};*out=zero;}
    return result;
}
enum cam_result cam_plan(const void *f,size_t bytes,struct cam_layout *l){return inspect(f,bytes,l,0);}
enum cam_result cam_admit(const void *f,size_t bytes,struct cam_layout *l){return inspect(f,bytes,l,1);}
static void retire(struct cam_queue *q){q->running=0;q->phase=CAM_RETIRED;}
static void release_slot(struct cam_queue *q){
    struct cam_frame frame={0};struct cam_layout layout={0};
    q->frame=frame;q->layout=layout;q->active_ticket=0;q->deadline=0;q->phase=CAM_IDLE;
}
static int matches(const struct cam_queue *q,uint64_t epoch,uint64_t ticket){
    return epoch==q->epoch && ticket && ticket==q->active_ticket;
}
enum cam_result cam_start(struct cam_queue *q,uint64_t epoch){
    if(!q)return CAM_ARGUMENT;
    if(q->running || q->phase!=CAM_IDLE)return CAM_BUSY;
    if(!epoch || epoch<=q->last_epoch)return CAM_STALE;
    q->epoch=epoch;q->last_epoch=epoch;q->next_ticket=1;q->last_now=0;q->running=1;return CAM_OK;
}
enum cam_result cam_submit(struct cam_queue *q,uint64_t epoch,const void *input,size_t bytes,
    uint64_t now,uint64_t timeout,uint64_t *ticket){
    struct cam_frame frame;struct cam_layout layout;enum cam_result result;
    if(!ticket || !q)return CAM_ARGUMENT;
    *ticket=0;
    if(epoch!=q->epoch)return CAM_STALE;
    if(!q->running)return CAM_STOPPED;
    if(q->phase!=CAM_IDLE)return CAM_BUSY;
    if(!timeout || now<q->last_now || timeout>UINT64_MAX-now)return CAM_OVERFLOW;
    if(!q->next_ticket || q->next_ticket==UINT64_MAX)return CAM_OVERFLOW;
    if(!decode(input,bytes,&frame))return CAM_TRUNCATED;
    result=validate(&frame,0,&layout);if(result!=CAM_OK)return result;
    for(unsigned p=0;p<frame.plane_count;++p)if(frame.planes[p].used)return CAM_FORMAT;
    q->frame=frame;q->layout=layout;q->deadline=now+timeout;q->last_now=now;
    q->active_ticket=q->next_ticket++;q->phase=CAM_INFLIGHT;*ticket=q->active_ticket;return CAM_OK;
}
enum cam_result cam_poll(struct cam_queue *q,uint64_t now){
    if(!q)return CAM_ARGUMENT;
    if(now<q->last_now)return CAM_ARGUMENT;
    q->last_now=now;
    if(q->phase==CAM_INFLIGHT && now>=q->deadline){retire(q);return CAM_TIMEOUT;}
    return q->running?CAM_OK:CAM_STOPPED;
}
enum cam_result cam_complete(struct cam_queue *q,uint64_t epoch,uint64_t ticket,
    const void *counts,size_t bytes,int status,uint64_t now){
    uint64_t used[CAM_PLANES];struct cam_frame frame;struct cam_layout layout;enum cam_result result;
    if(!q)return CAM_ARGUMENT;
    if(!matches(q,epoch,ticket))return CAM_STALE;
    if(q->phase==CAM_RETIRED || !q->running)return CAM_STOPPED;
    if(q->phase!=CAM_INFLIGHT)return CAM_STALE;
    result=cam_poll(q,now);if(result!=CAM_OK)return result;
    if(status){retire(q);return CAM_PRODUCER_ERROR;}
    if(!counts || bytes!=sizeof(used)){retire(q);return CAM_TRUNCATED;}
    copy_bytes(used,counts,sizeof(used));frame=q->frame;
    for(unsigned p=0;p<CAM_PLANES;++p)frame.planes[p].used=used[p];
    result=validate(&frame,1,&layout);
    if(result!=CAM_OK){retire(q);return result;}
    q->frame=frame;q->layout=layout;q->phase=CAM_READY;return CAM_OK;
}
enum cam_result cam_take(struct cam_queue *q,struct cam_frame *f,struct cam_layout *l){
    if(!q || !f || !l)return CAM_ARGUMENT;
    if(!q->running)return CAM_STOPPED;
    if(q->phase!=CAM_READY)return CAM_BUSY;
    *f=q->frame;*l=q->layout;q->phase=CAM_HELD;return CAM_OK;
}
enum cam_result cam_release(struct cam_queue *q,uint64_t epoch,uint64_t ticket){
    if(!q)return CAM_ARGUMENT;
    if(!matches(q,epoch,ticket) || q->phase!=CAM_HELD)return CAM_STALE;
    release_slot(q);return CAM_OK;
}
void cam_stop(struct cam_queue *q){
    if(q){q->running=0;if(q->phase==CAM_INFLIGHT || q->phase==CAM_READY)q->phase=CAM_RETIRED;}
}
enum cam_result cam_quiesced(struct cam_queue *q,uint64_t epoch,uint64_t ticket){
    if(!q)return CAM_ARGUMENT;
    if(!matches(q,epoch,ticket) || q->phase!=CAM_RETIRED)return CAM_STALE;
    release_slot(q);return CAM_OK;
}
