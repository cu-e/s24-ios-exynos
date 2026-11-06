/* SPDX-License-Identifier: GPL-2.0-only
 * Actual donor FDT/UI + extracted loader initialization, synthetic host buffers.
 * No physical framebuffer, MMIO or target execution occurs in these controls.
 */
#define _GNU_SOURCE 1
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include "fdt.h"
#include "ui.h"
static int flushes;
static uintptr_t flush_start,flush_end;
static void clean(uintptr_t a,uintptr_t b) { flushes++;flush_start=a;flush_end=b; }
#include "loader_ui.inc"
static _Alignas(8) unsigned char blob[32768],tree[16384],names[4096];
static size_t nt,nn,total;
static void w32(unsigned char *p,uint32_t n){p[0]=n>>24;p[1]=n>>16;p[2]=n>>8;p[3]=n;}
static void w64(unsigned char *p,uint64_t n){w32(p,n>>32);w32(p+4,n);}
static void word(uint32_t n){w32(tree+nt,n);nt+=4;}
static void begin(const char *n){word(1);size_t z=strlen(n)+1;memcpy(tree+nt,n,z);nt=(nt+z+3)&~(size_t)3;}
static void end(void){word(2);}
static void prop(const char *n,const void *v,size_t z){size_t off=nn;memcpy(names+nn,n,strlen(n)+1);nn+=strlen(n)+1;word(3);word((uint32_t)z);word((uint32_t)off);memcpy(tree+nt,v,z);nt=(nt+z+3)&~(size_t)3;}
static void cell(const char *n,uint32_t v){unsigned char b[4];w32(b,v);prop(n,b,4);}
static void string(const char *n,const char *v){prop(n,v,strlen(v)+1);}
static void node(int k){
 unsigned char reg[32]={0};uint64_t base=0x90000000,size=0x400000;
 uint32_t width=320,height=320,stride=1296;
 if(k==9)size=(uint64_t)stride*height-1;
 if(k==10)size=(uint64_t)stride*height;
 if(k==11)width=UINT32_MAX;
 if(k==12)width=16385;
 if(k==13)height=UINT32_MAX;
 if(k==14)base=0xfffff000;
 if(k==15)base=UINT64_MAX-1023;
 if(k==35){width=16;height=16;stride=80;size=1280;}
 begin("framebuffer@90000000");w64(reg,base);w64(reg+8,size);
 prop("reg",reg,k==19?15:k==20?32:16);
 string("compatible",k==16?"vendor,simple-framebuffer-wrong":"simple-framebuffer");
 if(k!=5)cell("width",width);cell("height",height);
 cell("stride",k==6?0:k==7?1281:k==8?1276:stride);
 if(k!=4){const char *f=k==1?"r5g6b5":k==17?"a8b8g8r8":k==26?"a8r8g8b8":"x8r8g8b8";if(k==24)prop("format",f,strlen(f));else string("format",f);}
 if(k!=3){const char *s=k==2?"disabled":k==27?"ok":"okay";if(k==25)prop("status",s,strlen(s));else string("status",s);}
 if(k==18)string("format","x8r8g8b8");
 if(k==29)cell("memory-region",1);
 end();
}
static uintptr_t build(int k){
 memset(blob,0,sizeof blob);memset(tree,0,sizeof tree);memset(names,0,sizeof names);nt=nn=0;
 begin("");cell("#address-cells",k==34?3:2);cell("#size-cells",2);
 begin(k==21?"bus":"chosen");
 if(k==22)string("status","disabled");
 if(k==30)cell("ranges",1);
 if(k!=36)node(k);if(k==28)node(0);
 if(k==23)string("status","disabled");
 end();end();word(9);
 size_t so=56,to=so+nt;total=to+nn;memcpy(blob+so,tree,nt);memcpy(blob+to,names,nn);
 w32(blob,0xd00dfeed);w32(blob+4,(uint32_t)total);w32(blob+8,(uint32_t)so);w32(blob+12,(uint32_t)to);w32(blob+16,40);w32(blob+20,17);w32(blob+24,16);w32(blob+32,(uint32_t)nn);w32(blob+36,(uint32_t)nt);
 if(k==31)w32(blob+36,(uint32_t)nt-4);
 if(k==32)w32(blob+12,UINT32_MAX-7);
 if(k==33)w32(blob+so,0x12345678);
 return (uintptr_t)blob;
}
static int find_guarded(int k,uint64_t *base,uint64_t *size,uint32_t *w,uint32_t *h,uint32_t *s){
 build(k);size_t page=(size_t)sysconf(_SC_PAGESIZE),used=(total+7)&~(size_t)7,span=(used+page-1)&~(page-1);
 unsigned char *m=mmap(NULL,span+page,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
 if(m==MAP_FAILED||mprotect(m+span,page,PROT_NONE))exit(20);
 unsigned char *p=m+span-used;memcpy(p,blob,total);
 int rc=fdt_find_framebuffer((uintptr_t)p,base,size,w,h,s);if(munmap(m,span+page))exit(21);return rc;
}
static void init(int have){
#ifdef E1S_FB_CONTRACT
 ui_init(have);
#else
 (void)have;ui_init();
#endif
}
static int untouched(const unsigned char *p,size_t n){for(size_t i=0;i<n;i++)if(p[i]!=0x7b)return 0;return 1;}
#ifdef E1S_FB_CONTRACT
static uint64_t pixels_hash(const unsigned char *pixels,size_t width,size_t height,size_t stride){
 uint64_t hash=1469598103934665603ULL;
 for(size_t y=0;y<height;y++)for(size_t x=0;x<width*4;x++)hash=(hash^pixels[y*stride+x])*1099511628211ULL;
 return hash;
}
static int tall_ui(void){
 const size_t width=1080,height=2340,stride=4352,extent=stride*height,page=(size_t)sysconf(_SC_PAGESIZE),span=(extent+page-1)&~(page-1);
 unsigned char *m=mmap(NULL,span+2*page,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
 if(m==MAP_FAILED||mprotect(m,page,PROT_NONE)||mprotect(m+page+span,page,PROT_NONE))return 20;
 unsigned char *pixels=m+page+span-extent;memset(m+page,0x7b,span);
 fb_base=(uintptr_t)pixels;fb_size=extent;fb_w=width;fb_h=height;fb_stride=stride;flushes=0;
 uint64_t before=pixels_hash(pixels,width,height,stride);init(1);uint64_t after=pixels_hash(pixels,width,height,stride);
 if(!ui_ready||before==after)return 30;before=after;
 struct ui_boot_info info={0};info.cmdline="bounded host framebuffer control";ui_set_info(&ui,&info);after=pixels_hash(pixels,width,height,stride);if(before==after)return 31;before=after;
 ui_set_stage(&ui,UI_STAGE_FB,UI_OK);after=pixels_hash(pixels,width,height,stride);if(before==after)return 32;before=after;
 ui_set_progress(&ui,73,"padded-stride progress glyphs");after=pixels_hash(pixels,width,height,stride);if(before==after)return 33;before=after;
 ui_set_status(&ui,"visible bounded status glyphs",UI_TEXT_OK);after=pixels_hash(pixels,width,height,stride);if(before==after)return 34;before=after;
 ui_fail(&ui,"visible bounded failure glyphs");after=pixels_hash(pixels,width,height,stride);if(before==after)return 35;
 for(size_t y=0;y<height;y++)if(!untouched(pixels+y*stride+width*4,stride-width*4))return 36;
 if(!untouched(m+page,(size_t)(pixels-(m+page))))return 37;
 fb_flush();if(flushes!=1||flush_start!=(uintptr_t)pixels||flush_end!=(uintptr_t)pixels+extent)return 38;
 if(munmap(m,span+2*page))return 21;
 return 0;
}
#endif
int main(int argc,char **argv){
 int legacy=argc==2&&!strcmp(argv[1],"--legacy"),checks=0;
 if(legacy){
#ifndef E1S_FB_CONTRACT
  int cases[]={1,2,3,4,5,6,16};
  for(size_t i=0;i<sizeof cases/sizeof cases[0];i++){uint64_t b=0,z=0;uint32_t w=320,h=320,s=1280;if(find_guarded(cases[i],&b,&z,&w,&h,&s)!=1)return 3;checks++;}
  if(fb_base!=FB_BASE||find_guarded(36,&fb_base,&fb_size,&fb_w,&fb_h,&fb_stride)||fb_base!=FB_BASE)return 15;checks++;
  /* Allocate more than the advertised16 bytes: observe real writes outside
   * the logical extent without ever writing outside host backing or MMIO. */
  unsigned char *backing=malloc(512);if(!backing)return 20;memset(backing,0x7b,512);fb_base=(uintptr_t)backing;fb_size=16;fb_w=fb_h=8;fb_stride=32;
  init(0);fb_flush();if(!ui_ready||untouched(backing+16,240))return 4;free(backing);
  puts("legacy actual invalid framebuffer acceptance and extent-blind/missing-metadata drawing reproduced");printf("controls=%d\n",checks+1);return 0;
#else
  return 2;
#endif
 }
#ifdef E1S_FB_CONTRACT
 for(int k=0;k<=36;k++){
  uint64_t b=0x1234,z=0x5678;uint32_t w=1,h=2,s=3;int rc=find_guarded(k,&b,&z,&w,&h,&s);int valid=k==0||k==10||k==26||k==27||k==35;
  if(rc!=valid||(!valid&&(b!=0x1234||z!=0x5678||w!=1||h!=2||s!=3))){fprintf(stderr,"fb fixture%d result%d\n",k,rc);return 5;}checks++;
 }
 uint64_t b=1,z=2;uint32_t w=3,h=4,s=5;if(fdt_find_framebuffer(0,&b,&z,&w,&h,&s)||fdt_find_framebuffer(build(0)+1,&b,&z,&w,&h,&s))return 6;checks+=2;
 size_t page=(size_t)sysconf(_SC_PAGESIZE),extent=1280;unsigned char *m=mmap(NULL,2*page,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
 if(m==MAP_FAILED||mprotect(m+page,page,PROT_NONE))return 20;unsigned char *pixels=m+page-extent;memset(m,0x7b,page);
 fb_base=(uintptr_t)pixels;fb_size=extent;fb_w=fb_h=16;fb_stride=80;flushes=0;init(0);fb_flush();
 if(ui_ready||flushes||fb_base||fb_size||fb_w||fb_h||fb_stride||!untouched(m,page))return 7;checks++;
 fb_base=(uintptr_t)pixels;fb_size=16;fb_w=fb_h=16;fb_stride=80;init(1);fb_flush();if(ui_ready||flushes||!untouched(m,page))return 8;checks++;
 fb_base=(uintptr_t)pixels;fb_size=extent;fb_w=fb_h=16;fb_stride=81;init(1);if(ui_ready||!untouched(m,page))return 9;checks++;
 fb_base=(uintptr_t)pixels;fb_size=extent;fb_w=fb_h=16;fb_stride=80;init(1);fb_flush();
 if(!ui_ready||flushes!=1||flush_start!=(uintptr_t)pixels||flush_end!=(uintptr_t)pixels+extent||untouched(pixels,64))return 10;
 struct ui_boot_info info={0};ui_set_info(&ui,&info);ui_set_stage(&ui,UI_STAGE_FB,UI_OK);ui_set_progress(&ui,100,"done");ui_set_status(&ui,"ok",UI_TEXT_OK);ui_fail(&ui,"synthetic bounded host control");
 for(size_t y=0;y<16;y++)if(!untouched(pixels+y*80+64,16))return 11;
 if(!untouched(m,(size_t)(pixels-m)))return 12;checks+=2;
 memset(pixels,0x7b,extent);struct ui_fb invalid=ui;invalid.size_bytes=16;ui_begin(&invalid);ui_set_info(&invalid,&info);ui_set_stage(&invalid,1,1);ui_set_progress(&invalid,100,"none");ui_set_status(&invalid,"none",0);ui_fail(&invalid,"none");if(!untouched(pixels,extent))return 13;checks++;
 invalid=ui;invalid.width=UINT32_MAX;ui_set_progress(&invalid,100,"none");invalid=ui;invalid.base=(volatile uint32_t *)(UINTPTR_MAX-3);invalid.size_bytes=8;if(ui_fb_valid(&invalid)||!untouched(pixels,extent))return 14;checks++;
 if(munmap(m,2*page))return 21;
 int tall=tall_ui();if(tall)return tall;checks+=9;
 printf("actual patched FDT/fullUI/loader-init controls PASS=%d\n",checks);return 0;
#else
 return 2;
#endif
}
