/* Real detector controls; intentionally invalid, never linked into adapter/guest. */
#include <stdlib.h>
#include <limits.h>
int main(int argc,char **argv)
{
    (void)argv;
    if(argc==2) { volatile unsigned char *p=malloc(1);if(!p)return 2;p[1]=7;free((void *)p); }
    else { volatile int x=INT_MAX;return x+1; }
    return 0;
}
