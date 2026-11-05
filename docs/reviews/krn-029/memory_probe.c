#include <assert.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
void *review_memcpy(void *,const void *,size_t);
void *review_memmove(void *,const void *,size_t);
void *review_memset(void *,int,size_t);
int review_memcmp(const void *,const void *,size_t);
void review_bzero(void *,size_t);
void *review_memcpy_chk(void *,const void *,size_t,size_t);
int main(int argc,char **argv)
{
    (void)argv;unsigned checks=0;unsigned char actual[128],expect[128],before[128];
    if(argc>1){review_memcpy_chk(actual,expect,17,16);return 1;}
    for(size_t src=0;src<32;src++)for(size_t dst=0;dst<32;dst++)for(size_t n=0;n<=64;n++) {
        for(unsigned i=0;i<128;i++)actual[i]=expect[i]=before[i]=(unsigned char)(i*7);
        for(size_t i=0;i<n;i++)expect[dst+i]=before[src+i];
        assert(review_memmove(actual+dst,actual+src,n)==actual+dst);
        assert(!memcmp(actual,expect,sizeof(actual)));checks++;
    }
    for(unsigned x=0;x<256;x++)for(unsigned y=0;y<256;y++) {
        unsigned char a=(unsigned char)x,b=(unsigned char)y;
        int r=review_memcmp(&a,&b,1);
        assert((r<0)==(x<y) && (r>0)==(x>y));checks++;
    }
    memset(actual,0,sizeof(actual));memset(expect,0,sizeof(expect));
    assert(review_memset(actual,-1,64)==actual);memset(expect,-1,64);assert(!memcmp(actual,expect,128));
    assert(review_memcpy(actual+64,actual,64)==actual+64);memcpy(expect+64,expect,64);assert(!memcmp(actual,expect,128));
    assert(review_memcpy_chk(actual+64,actual,64,64)==actual+64);
    review_bzero(actual,128);assert(!memcmp(actual,(unsigned char[128]){0},128));
    printf("PASS %u independent synthetic-memory overlap/compare cases plus byte/fortify bounds\n",checks);
    return 0;
}
