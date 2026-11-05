/* Owned synthetic-CPU runtime only,not an XNU implementation or production
 * component. Implements the genuine four-argument fortified memset ABI. */
#include <stddef.h>
void *__memset_chk(void *destination,int value,size_t bytes,size_t capacity){
    if(bytes>capacity)__builtin_trap();
    volatile unsigned char *out=destination;
    for(size_t i=0;i<bytes;++i)out[i]=(unsigned char)value;
    return destination;
}
