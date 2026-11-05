/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Intentional host faults: prove instrumentation is active. Never audio/DSP. */
#include <limits.h>
#include <stdlib.h>
int main(int argc, char **argv)
{
    if(argc>1 && argv[1][0]=='a') {
        volatile unsigned index=17;
        volatile unsigned char *p=malloc(16);
        if(!p) return 2;
        p[index]=1;
        free((void *)p);
        return 0;
    }
    volatile int top=INT_MAX,one=1;
    return top+one;
}
