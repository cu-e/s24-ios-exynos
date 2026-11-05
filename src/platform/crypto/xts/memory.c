/* Owned freestanding byte routines for the synthetic CPU guest only. */
#include <stddef.h>
#include <stdint.h>
void *memcpy(void *dst,const void *src,size_t n) { unsigned char *d=dst;const unsigned char *s=src;while(n--)*d++=*s++;return dst; }
void *memset(void *dst,int c,size_t n) { unsigned char *d=dst;while(n--)*d++=(unsigned char)c;return dst; }
void *memmove(void *dst,const void *src,size_t n) { unsigned char *d=dst;const unsigned char *s=src;if((uintptr_t)d<(uintptr_t)s)while(n--)*d++=*s++;else while(n){--n;d[n]=s[n];}return dst; }
int memcmp(const void *a,const void *b,size_t n) { const unsigned char *x=a,*y=b;while(n--){if(*x!=*y)return *x-*y;++x;++y;}return 0; }

void bzero(void *p,size_t n) { (void)memset(p,0,n); }
void *__memcpy_chk(void *dst,const void *src,size_t n,size_t capacity)
{ if(n>capacity)__builtin_trap();return memcpy(dst,src,n); }
