#define _GNU_SOURCE
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <signal.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <unistd.h>
extern void *__memset_chk(void *,int,size_t,size_t);
static void *(*volatile fill)(void *,int,size_t,size_t)=__memset_chk;
static unsigned checks,trapped,reaped;
#define CHECK(x) do{++checks;if(!(x))return __LINE__;}while(0)
static int suite(void){
    unsigned char arena[19];
    for(unsigned test=0;test<5;++test){
        for(unsigned i=0;i<sizeof(arena);++i)arena[i]=0xa5;
        int value=(int[]){0,0x123,-1,-257,256}[test];
        CHECK(fill(arena+3,value,8,8)==arena+3);
        for(unsigned i=0;i<sizeof(arena);++i)CHECK(arena[i]==(i>=3 && i<11?(unsigned char)value:0xa5));
    }
    CHECK(fill(NULL,0x123,0,0)==NULL);
    CHECK(fill(arena,0,0,SIZE_MAX)==arena);
    for(unsigned test=0;test<2;++test){
        unsigned char *shared=mmap(NULL,4096,PROT_READ|PROT_WRITE,MAP_SHARED|MAP_ANONYMOUS,-1,0);
        CHECK(shared!=MAP_FAILED);for(unsigned i=0;i<4096;++i)shared[i]=0xa5;
        pid_t child=fork();CHECK(child>=0);
        if(child==0){fill(shared+4,0x7f,test?SIZE_MAX:9,8);_exit(0);}
        int status=0;CHECK(waitpid(child,&status,0)==child);++reaped;
        CHECK(WIFSIGNALED(status) && (WTERMSIG(status)==SIGILL || WTERMSIG(status)==SIGTRAP));
        ++trapped;
        for(unsigned i=0;i<4096;++i)CHECK(shared[i]==0xa5);
        CHECK(munmap(shared,4096)==0);
    }
    return 0;
}
int main(void){int result=suite();printf("RSA CHECKED MEMSET %s checks=%u failure_line=%d trapped_children=%u reaped=%u\n",result?"FAIL":"PASS",checks,result,trapped,reaped);return result?1:0;}
