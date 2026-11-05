/* Owned bounded synthetic fixture fortify service; real byte movement. */
#include <stddef.h>
extern void *memmove(void *,const void *,size_t);
extern void *memset(void *,int,size_t);
extern __attribute__((noreturn)) void kdes_fixture_fail(unsigned);
void *__memmove_chk(void *d,const void *s,size_t n,size_t capacity)
{if(n>capacity)kdes_fixture_fail(__LINE__);return memmove(d,s,n);}

void *__memset_chk(void *d,int c,size_t n,size_t capacity)
{if(n>capacity)kdes_fixture_fail(__LINE__);return memset(d,c,n);}
