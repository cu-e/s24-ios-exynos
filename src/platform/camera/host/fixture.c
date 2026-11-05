#include "frame.h"
#include "donor.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned checks,vectors;
#define CHECK(x) do{++checks;if(!(x)){fprintf(stderr,"line%d: %s\n",__LINE__,#x);exit(1);}}while(0)
static const uint32_t formats[]={CAM_YUYV,CAM_NV12,CAM_NV21,CAM_NV12M,CAM_NV21M};
static uint32_t random_word(uint32_t *s){*s^=*s<<13;*s^=*s>>17;*s^=*s<<5;return *s;}
static struct cam_frame sample(unsigned kind,uint32_t width,uint32_t height,uint32_t b0,uint32_t b1){
    struct cam_frame f={0};uint32_t bpl[2]={b0,b1},sizes[3]={0};
    donor_calculate(kind,width,height,bpl,sizes);
    f.version=1;f.fourcc=formats[kind];f.component_bits=8;f.width=width;f.height=height;
    f.bytesperline[0]=b0;f.bytesperline[1]=b1;f.crop_w=width;f.crop_h=height;
    f.plane_count=kind>=3?3:2;
    for(unsigned p=0;p<f.plane_count;++p){
        f.planes[p].offset=f.allocation_bytes;f.planes[p].capacity=sizes[p];
        f.planes[p].used=p+1==f.plane_count?0:sizes[p];f.allocation_bytes+=sizes[p];
    }
    return f;
}
static void source_vectors(void){
    uint32_t seed=0x234521ae;struct cam_layout layout;
    CHECK(donor_layout[0]==CAM_METADATA_BYTES);
    CHECK(donor_layout[1]==84 && donor_layout[2]==16 && donor_layout[3]==8);
    CHECK(donor_layout[4]==88 && donor_layout[5]==6840 && donor_layout[6]==216);
    CHECK(donor_layout[7]==18 && donor_layout[8]==8);
    for(unsigned kind=0;kind<5;++kind){
        CHECK(formats[kind]==donor_fourccs[kind]);
        for(unsigned i=0;i<1024;++i){
            uint32_t w=2+2*(random_word(&seed)%4096),h=2+2*(random_word(&seed)%4096);
            uint32_t minimum=w*(kind==0?2:1),bpl[2];
            bpl[0]=(i%3==0)?0:minimum+(random_word(&seed)%1024);
            bpl[1]=kind==0?0:((i%3==1)?w/2:w+(random_word(&seed)%1024));
            struct cam_frame f=sample(kind,w,h,bpl[0],bpl[1]);uint32_t sizes[3]={0};
            donor_calculate(kind,w,h,bpl,sizes);
            CHECK(cam_admit(&f,sizeof(f),&layout)==CAM_OK);
            for(unsigned p=0;p<f.plane_count;++p)CHECK(layout.required[p]==sizes[p]);
            CHECK(layout.stride[0]==(bpl[0]>minimum?bpl[0]:minimum));
            ++vectors;
        }
    }
}
static void malformed(void){
    struct cam_frame base=sample(3,640,480,0,0),f;struct cam_layout layout;
    for(size_t n=0;n<sizeof(base);++n){
        void *short_input=malloc(n?n:1);CHECK(short_input!=NULL);memcpy(short_input,&base,n);
        CHECK(cam_admit(short_input,n,&layout)==CAM_TRUNCATED && layout.plane_count==0);free(short_input);
    }
    uint8_t unaligned[sizeof(base)+1];memcpy(unaligned+1,&base,sizeof(base));
    CHECK(cam_admit(unaligned+1,sizeof(base),&layout)==CAM_OK);
    CHECK(cam_admit(&base,sizeof(base)+1,&layout)==CAM_TRUNCATED);
    for(unsigned mutation=0;mutation<22;++mutation){
        f=base;enum cam_result expected=CAM_FORMAT;
        switch(mutation){
        case 0:f.version=2;break;
        case 1:f.fourcc=CAM_FOURCC('M','J','P','G');break;
        case 2:f.component_bits=10;break;
        case 3:f.compression=1;break;
        case 4:f.reserved=1;break;
        case 5:f.width=0;expected=CAM_GEOMETRY;break;
        case 6:f.width++;expected=CAM_GEOMETRY;break;
        case 7:f.height++;expected=CAM_GEOMETRY;break;
        case 8:f.width=UINT32_MAX-1;expected=CAM_OVERFLOW;break;
        case 9:f.bytesperline[1]=UINT32_MAX;expected=CAM_OVERFLOW;break;
        case 10:f.crop_w=0;expected=CAM_CROP;break;
        case 11:f.crop_x=UINT32_MAX;expected=CAM_CROP;break;
        case 12:f.crop_x=2;expected=CAM_CROP;break;
        case 13:f.crop_h--;expected=CAM_CROP;break;
        case 14:f.plane_count=4;expected=CAM_CAPACITY;break;
        case 15:f.planes[0].capacity--;expected=CAM_CAPACITY;break;
        case 16:f.planes[0].used--;expected=CAM_TRUNCATED;break;
        case 17:f.planes[2].capacity--;expected=CAM_CAPACITY;break;
        case 18:f.planes[1].offset--;expected=CAM_OVERLAP;break;
        case 19:f.planes[2].used=f.planes[2].capacity+1;expected=CAM_CAPACITY;break;
        case 20:f.allocation_bytes=UINT64_MAX;f.planes[2].offset=UINT64_MAX-1;expected=CAM_CAPACITY;break;
        default:f.allocation_bytes--;expected=CAM_CAPACITY;break;
        }
        CHECK(cam_admit(&f,sizeof(f),&layout)==expected);
        CHECK(layout.plane_count==0);
    }
    f=sample(1,640,480,0,0);f.planes[2].used=1;
    CHECK(cam_admit(&f,sizeof(f),&layout)==CAM_FORMAT);
    f=sample(0,640,479,0,0);CHECK(cam_admit(&f,sizeof(f),&layout)==CAM_OK);
    f.bytesperline[1]=1;CHECK(cam_admit(&f,sizeof(f),&layout)==CAM_GEOMETRY);
    f=sample(1,640,480,0,0);f.width=65536;f.height=65536;f.crop_w=f.width;f.crop_h=f.height;
    CHECK(cam_admit(&f,sizeof(f),&layout)==CAM_OVERFLOW);
    f=sample(1,640,480,0,0);f.crop_x=2;f.crop_y=2;f.crop_w=638;f.crop_h=478;
    CHECK(cam_admit(&f,sizeof(f),&layout)==CAM_OK);
    f.crop_x=1;CHECK(cam_admit(&f,sizeof(f),&layout)==CAM_CROP);
}
static struct cam_frame reservation(void){
    struct cam_frame f=sample(3,640,480,0,0);
    for(unsigned p=0;p<3;++p)f.planes[p].used=0;
    return f;
}
static void lifecycle(void){
    struct cam_frame f=reservation(),view;struct cam_layout layout;
    uint64_t used[3]={640*480,640*240,0},ticket,ignored;
    struct cam_queue q={0};
    CHECK(cam_start(&q,1)==CAM_OK);
    CHECK(cam_submit(&q,1,&f,sizeof(f),100,10,&ticket)==CAM_OK && ticket==1);
    CHECK(cam_submit(&q,1,&f,sizeof(f),100,10,&ignored)==CAM_BUSY && ignored==0);
    CHECK(cam_complete(&q,2,ticket,used,sizeof(used),0,101)==CAM_STALE);
    CHECK(cam_complete(&q,1,ticket+1,used,sizeof(used),0,101)==CAM_STALE);
    CHECK(cam_complete(&q,1,ticket,used,sizeof(used),0,99)==CAM_ARGUMENT && q.phase==CAM_INFLIGHT);
    CHECK(cam_complete(&q,1,ticket,used,sizeof(used),0,109)==CAM_OK);
    CHECK(cam_complete(&q,1,ticket,used,sizeof(used),0,109)==CAM_STALE);
    CHECK(cam_take(&q,&view,&layout)==CAM_OK && q.phase==CAM_HELD && view.planes[0].used==used[0]);
    cam_stop(&q);CHECK(q.phase==CAM_HELD && !q.running);
    CHECK(cam_start(&q,2)==CAM_BUSY);
    CHECK(cam_quiesced(&q,1,ticket)==CAM_STALE);
    CHECK(cam_release(&q,1,ticket)==CAM_OK && q.phase==CAM_IDLE);
    CHECK(cam_release(&q,1,ticket)==CAM_STALE);
    CHECK(cam_start(&q,1)==CAM_STALE && cam_start(&q,2)==CAM_OK);
    CHECK(cam_submit(&q,2,&f,sizeof(f),200,10,&ticket)==CAM_OK);
    cam_stop(&q);cam_stop(&q);CHECK(q.phase==CAM_RETIRED);
    CHECK(cam_take(&q,&view,&layout)==CAM_STOPPED);
    CHECK(cam_complete(&q,2,ticket,used,sizeof(used),0,201)==CAM_STOPPED);
    CHECK(cam_start(&q,3)==CAM_BUSY);
    CHECK(cam_quiesced(&q,1,ticket)==CAM_STALE);
    CHECK(cam_quiesced(&q,2,ticket)==CAM_OK && cam_start(&q,3)==CAM_OK);
    CHECK(cam_submit(&q,3,&f,sizeof(f),300,10,&ticket)==CAM_OK);
    CHECK(cam_complete(&q,2,ticket,used,sizeof(used),0,301)==CAM_STALE && q.phase==CAM_INFLIGHT);
    CHECK(cam_poll(&q,309)==CAM_OK && cam_poll(&q,310)==CAM_TIMEOUT && q.phase==CAM_RETIRED);
    CHECK(cam_quiesced(&q,3,ticket)==CAM_OK);
    for(unsigned mode=0;mode<5;++mode){
        CHECK(cam_start(&q,4+mode)==CAM_OK);
        CHECK(cam_submit(&q,4+mode,&f,sizeof(f),400,10,&ticket)==CAM_OK);
        enum cam_result expected=CAM_PRODUCER_ERROR;uint64_t counts[3]={used[0],used[1],0};
        size_t bytes=sizeof(counts);int status=mode==0?-1:0;uint64_t now=401;
        if(mode==1){--bytes;expected=CAM_TRUNCATED;}
        if(mode==2){--counts[0];expected=CAM_TRUNCATED;}
        if(mode==3){counts[2]=CAM_METADATA_BYTES+1;expected=CAM_CAPACITY;}
        if(mode==4){now=410;expected=CAM_TIMEOUT;}
        CHECK(cam_complete(&q,4+mode,ticket,counts,bytes,status,now)==expected);
        CHECK(q.phase==CAM_RETIRED && !q.running && cam_take(&q,&view,&layout)==CAM_STOPPED);
        CHECK(cam_quiesced(&q,4+mode,ticket)==CAM_OK);
    }
    CHECK(cam_start(&q,9)==CAM_OK);
    CHECK(cam_submit(&q,9,&f,sizeof(f),UINT64_MAX,1,&ticket)==CAM_OVERFLOW);
    q.next_ticket=UINT64_MAX;
    CHECK(cam_submit(&q,9,&f,sizeof(f),500,1,&ticket)==CAM_OVERFLOW);
    q.next_ticket=1;f.planes[0].used=1;
    CHECK(cam_submit(&q,9,&f,sizeof(f),500,1,&ticket)==CAM_FORMAT);
    f.planes[0].used=0;
    CHECK(cam_submit(&q,9,&f,sizeof(f),500,10,&ticket)==CAM_OK);
    CHECK(cam_complete(&q,9,ticket,used,sizeof(used),0,501)==CAM_OK);
    cam_stop(&q);CHECK(q.phase==CAM_RETIRED && cam_take(&q,&view,&layout)==CAM_STOPPED);
    CHECK(cam_quiesced(&q,9,ticket)==CAM_OK && cam_start(&q,10)==CAM_OK);
    CHECK(cam_submit(&q,10,&f,sizeof(f),600,10,&ticket)==CAM_OK);
    used[0]=UINT64_MAX;
    CHECK(cam_complete(&q,10,ticket,used,sizeof(used),0,601)==CAM_CAPACITY && q.phase==CAM_RETIRED);
}
static void mutations(void){
    uint32_t seed=0x94abcdef;struct cam_frame base=sample(3,640,480,0,0);struct cam_layout layout;
    for(unsigned i=0;i<20000;++i){
        uint8_t bytes[sizeof(base)];memcpy(bytes,&base,sizeof(base));
        bytes[random_word(&seed)%sizeof(base)]^=(uint8_t)((random_word(&seed)%255)+1);
        enum cam_result r=cam_admit(bytes,sizeof(bytes),&layout);
        CHECK((r==CAM_OK && layout.plane_count==3) || (r!=CAM_OK && layout.plane_count==0));
    }
}
int main(void){
    source_vectors();malformed();lifecycle();mutations();
    printf("{\"outcome\":\"pass\",\"checks\":%u,\"real_donor_vectors\":%u,\"mutations\":20000,\"metadata_bytes\":%u,\"device_io\":false,\"donor_layout\":[",checks,vectors,CAM_METADATA_BYTES);
    for(unsigned i=0;i<9;++i)printf("%s%llu",i?",":"",(unsigned long long)donor_layout[i]);
    puts("]}");return 0;
}
