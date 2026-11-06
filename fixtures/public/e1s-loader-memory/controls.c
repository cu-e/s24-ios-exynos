/* SPDX-License-Identifier: GPL-2.0-only
 * Project regression fixtures, 2026-11-06. Includes actual extracted loader C.
 * Physical addresses below are synthetic ownership cases, not safe RAM claims.
 */
#define _GNU_SOURCE 1
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include "fdt.h"
#include "selection.inc"

#define MBASE UINT64_C(0x100000000)
#define MSIZE UINT64_C(0x40000000)
static _Alignas(8) unsigned char blob[65536], tree[32768], names[8192];
static size_t nt, nn, actual_size;
static void w32(unsigned char *p, uint32_t v) { p[0]=v>>24;p[1]=v>>16;p[2]=v>>8;p[3]=v; }
static void w64(unsigned char *p, uint64_t v) { w32(p,v>>32);w32(p+4,v); }
static void word(uint32_t v) { w32(tree+nt,v);nt+=4; }
static void begin(const char *name) { word(1);size_t n=strlen(name)+1;memcpy(tree+nt,name,n);nt=(nt+n+3)&~(size_t)3; }
static void end(void) { word(2); }
static void prop(const char *name,const void *p,size_t n) {
 size_t off=nn;memcpy(names+nn,name,strlen(name)+1);nn+=strlen(name)+1;
 word(3);word((uint32_t)n);word((uint32_t)off);if(n)memcpy(tree+nt,p,n);nt=(nt+n+3)&~(size_t)3;
}
static void cell(const char *name,uint32_t n) { unsigned char p[4];w32(p,n);prop(name,p,4); }
static void reg(uint64_t base,uint64_t size,int len) { unsigned char p[16];w64(p,base);w64(p+8,size);prop("reg",p,(size_t)len); }
static uintptr_t build(int kind) {
 memset(blob,0,sizeof blob);memset(tree,0,sizeof tree);memset(names,0,sizeof names);nt=nn=0;
 begin("");cell("#address-cells",2);cell("#size-cells",2);
 int memories=kind==5?17:1;
 for(int i=0;i<memories;i++) {begin("memory@100000000");reg(MBASE+(uint64_t)i*MSIZE,MSIZE,16);end();}
 if(kind==6) {begin("memory@fffffffffffff000");reg(UINT64_MAX-4095,8192,16);end();}
 begin("reserved-memory");cell("#address-cells",kind==7?3:2);cell("#size-cells",2);
 unsigned char translate[16]={0};prop("ranges",translate,kind==8?16:0);
 if(kind==0) {begin("left@100000000");reg(MBASE,0x10000000,16);end();begin("right@130000000");reg(MBASE+0x30000000,0x10000000,16);end();}
 if(kind==1) {begin("partial");reg(MBASE,MSIZE,15);end();}
 if(kind==2) {begin("wrapped");reg(UINT64_MAX-4095,8192,16);end();}
 if(kind==3 || kind==4 || kind==18) {
  int n=kind==4?92:93;
  for(int i=0;i<n;i++) {begin("reservation");reg(MBASE+(uint64_t)i*0x100000,kind==3&&i==92?MSIZE-92*0x100000:0x100000,16);end();}
 }
 if(kind==9) {begin("dynamic");cell("size",4096);end();}
 if(kind==10) {begin("all");reg(MBASE,MSIZE,16);end();}
 if(kind==11) {begin("nested");reg(MBASE,4096,16);begin("child");reg(MBASE+4096,4096,16);end();end();}
 end();
 if(kind==12) {for(int i=0;i<12;i++)begin("deep");for(int i=0;i<12;i++)end();}
 if(kind==13)cell("late-property",1);
 end();word(9);
 size_t ro=40,so=56;
 if(kind==14 || kind==15 || kind==18)so=72;
 if(kind==14) {w64(blob+ro,MBASE);w64(blob+ro+8,MSIZE);}
 if(kind==15) {w64(blob+ro,UINT64_MAX-4095);w64(blob+ro+8,8192);}
 if(kind==18) {w64(blob+ro,MBASE+MSIZE-4096);w64(blob+ro+8,4096);}
 size_t to=so+nt,total=to+nn;
 memcpy(blob+so,tree,nt);memcpy(blob+to,names,nn);actual_size=total;
 w32(blob,0xd00dfeed);w32(blob+4,(uint32_t)total);w32(blob+8,(uint32_t)so);w32(blob+12,(uint32_t)to);w32(blob+16,40);w32(blob+20,17);w32(blob+24,16);w32(blob+32,(uint32_t)nn);w32(blob+36,(uint32_t)nt);
 if(kind==16)w32(blob+36,(uint32_t)nt-4); /* Missing final END within declared block. */
 if(kind==17)w32(blob+ro,1); /* Reservation list has no terminator before structure. */
 if(kind==19)w32(blob+12,(uint32_t)so); /* Overlapping blocks. */
 if(kind==20)w32(blob+32,UINT32_MAX);
 if(kind==21)w32(blob+so+12,UINT32_MAX); /* First property's length. */
 if(kind==22)w32(blob+so+16,UINT32_MAX); /* First property's string offset. */
 if(kind==23)memset(blob+to,'x',nn); /* Unterminated property strings. */
 if(kind==24)w32(blob+so,0xdeadbeef);
 if(kind==25)w32(blob+4,39);
 if(kind==26)w32(blob+8,UINT32_MAX-3);
 if(kind==27)w32(blob+20,18);
 if(kind==28)w32(blob+16,44);
 return (uintptr_t)blob;
}
static int run_selection(uintptr_t dtb,uint64_t *base,uint64_t *size) {
 return choose_window(dtb,0x81000000,0x2000000,0xfa200000,0x9a4000,base,size);
}
static int guarded_case(int kind,uint64_t *base,uint64_t *size) {
 build(kind);
 size_t page=(size_t)sysconf(_SC_PAGESIZE), used=(actual_size+7)&~(size_t)7;
 size_t span=(used+page-1)&~(page-1);
 unsigned char *map=mmap(NULL,span+page,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
 if(map==MAP_FAILED||mprotect(map+span,page,PROT_NONE))exit(20);
 unsigned char *p=map+span-used;memcpy(p,blob,actual_size);
 int result=run_selection((uintptr_t)p,base,size);
 if(munmap(map,span+page))exit(21);
 return result;
}
int main(int argc,char **argv) {
 int legacy=argc==2&&!strcmp(argv[1],"--legacy"),checks=0;
 if(legacy) {
  /* Well-bounded DTBs reproducing silent acceptance, not unsafe truncated reads. */
  int kinds[]={1,2,3,5,6,14};
  for(size_t i=0;i<sizeof(kinds)/sizeof(kinds[0]);i++) {
   uint64_t base=0,size=0;int result=guarded_case(kinds[i],&base,&size);
   if(result!=1) {fprintf(stderr,"legacy control not reproduced: %d\n",kinds[i]);return 3;}
   checks++;
  }
  printf("legacy incorrect-map acceptance reproduced: %d\n",checks);return 0;
 }
 for(int kind=0;kind<=29;kind++) {
  uint64_t base=0x1122334455667788,size=0x8877665544332211;
  int result=guarded_case(kind,&base,&size);
  int valid=kind==0||kind==4;
  if(result!=valid || (!result&&(base!=0x1122334455667788||size!=0x8877665544332211))) {
   fprintf(stderr,"selection fixture%d result%d base%llx size%llx\n",kind,result,(unsigned long long)base,(unsigned long long)size);return 4;
  }
  if(kind==0&&(base!=MBASE+0x10000000||size!=0x20000000))return 5;
  checks++;
 }
 uint64_t base=1,size=2;
 if(run_selection(0,&base,&size)||run_selection(build(0)+1,&base,&size))return 6;
 checks+=2;
 struct fdt_range generic[2];
 uintptr_t empty=build(29);
 if(fdt_reserved_ranges(empty,generic,2)!=0)return 9;
 checks++; /* Generic empty FDT map valid; board selection above must refuse. */
 uintptr_t dtb=build(0);
 if(choose_window(dtb,UINT64_MAX-1,16,0xfa200000,0x9a4000,&base,&size))return 7;
 if(choose_window(dtb,0x81000000,0x2000000,UINT64_MAX-1,16,&base,&size))return 8;
 checks+=2;
 puts("actual patched C selection/parser controls PASS");printf("controls=%d\n",checks);return 0;
}
