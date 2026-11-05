"""Extract actual pinned declarations/calculations into a local GPL test oracle.

Generated vendor code stays in ignored artifacts. No vendor implementation is
linked into frame.c. The shim supplies fixed-width Linux types, not a kernel.
"""
import hashlib
import json
from pathlib import Path
import re
from source import PREFIX

FORMATS=['YUYV','NV12','NV21','NV12M','NV21M']

def block(text, pattern):
    match=re.search(pattern,text)
    if not match:raise ValueError('Missing exact source declaration: '+pattern)
    start=text.index('{',match.start());depth=1;end=start+1
    token=re.compile(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|[{}]',re.S)
    for item in token.finditer(text,end):
        if item[0]=='{':depth+=1
        elif item[0]=='}':depth-=1
        if not depth:
            return text[match.start():item.end()]
    raise ValueError('Unbalanced source declaration')

def generate(cache,out):
    out.mkdir(parents=True,exist_ok=False)
    def text(name):return (cache/name).read_text()
    def macro(body,name):
        match=re.search(r'^#define\s+'+name+r'\s+([^\n]+)',body,re.M)
        if not match:raise ValueError('Missing exact macro '+name)
        return '#define '+name+' '+match[1]+'\n'
    uapi=text('include/uapi/linux/videodev2.h')
    config=text(PREFIX+'ischain/is-v12_0_0/is-config.h')
    common=text(PREFIX+'include/is-common-enum.h')
    types=text(PREFIX+'include/is-type.h')
    formats=text(PREFIX+'v4l2/format.c')
    linux=out/'linux';linux.mkdir()
    shim='#include <stdint.h>\n#include <stdbool.h>\n#define _LINUX_TYPES_H\n#define __KERNEL__ 1\ntypedef uint8_t __u8;typedef uint32_t __u32;typedef int32_t __s32;typedef uint32_t u32;typedef uint8_t u8;typedef unsigned long ulong;\n'
    shim+=macro(uapi,'VIDEO_MAX_PLANES')
    for name in ['enum v4l2_quantization','enum v4l2_colorspace','struct __kernel_v4l2_timeval','struct v4l2_timecode','struct v4l2_buffer']:
        shim+=block(uapi,r'\b'+name+r'\s*\{')+';\n'
    shim+=re.search(r'^#define v4l2_fourcc\(a, b, c, d\).*\n[^\n]+',uapi,re.M)[0]+'\n'
    for name in FORMATS:shim+=macro(uapi,'V4L2_PIX_FMT_'+name)
    (linux/'videodev2.h').write_text('#pragma once\n'+shim)
    (out/'is-config.h').write_text(macro(config,'CAPTURE_NODE_MAX'))
    (out/'metadata.h').write_text(text(PREFIX+'include/v12_0_0/is-metadata-vendor.h'))
    code='/* Exact pinned Samsung GPL-2.0 declaration/calculation oracle. */\n#include <stddef.h>\n#include "metadata.h"\n'
    code+=macro(common,'IS_MAX_PLANES')
    for name in ['struct is_frame_cfg','struct is_fmt','struct is_crop']:
        code+=block(types,r'\b'+name+r'\s*\{')+';\n'
    code+='#define NUM_OF_META_PLANE 1\n#define BITS_PER_BYTE 8\n#define max(a,b) ((a)>(b)?(a):(b))\n#define dbg(...) ((void)0)\n'
    helpers=['setup_plane_widths','widths0_sps','widths01_420_sps','widths01_2p_420_sps']
    extracted={}
    for name in helpers:
        actual=block(formats,r'static void '+name+r'\s*\(')
        code+=actual+'\n';extracted[name]=hashlib.sha256(actual.encode()).hexdigest()
    code+='static struct is_fmt donor_formats[] = {\n'
    records=[]
    for name in FORMATS:
        candidates=re.findall(r'\.pixelformat\s*=\s*V4L2_PIX_FMT_'+name+r',(?P<body>.*?)\.setup_plane_sz\s*=\s*(\w+),',formats,re.S)
        candidates=[c for c in candidates if re.search(r'\.hw_bitwidth\s*=\s*DMA_INOUT_BIT_WIDTH_8BIT',c[0]) and re.search(r'\.sbwc_type\s*=\s*NONE',c[0])]
        if len(candidates)!=1:raise ValueError('Ambiguous or absent uncompressed8bit format '+name)
        body,helper=candidates[0]
        if helper not in helpers:raise ValueError('Unexpected source size helper')
        bpp=re.search(r'\.bitsperpixel\s*=\s*\{([^}]+)\}',body)[1]
        planes=int(re.search(r'\.num_planes\s*=\s*(\d+)\s*\+\s*NUM_OF_META_PLANE',body)[1])
        record=dict(format=name,image_planes=planes,bitsperpixel=[int(n.strip()) for n in bpp.split(',')],helper=helper)
        records.append(record)
        code+='{.name="'+name+'",.num_planes='+str(planes+1)+',.bitsperpixel={'+bpp+'},.setup_plane_sz='+helper+'},\n'
    code+='};\nvoid donor_calculate(unsigned kind,uint32_t w,uint32_t h,const uint32_t bpl[2],uint32_t sizes[3]){\nstruct is_frame_cfg fc={0};fc.format=&donor_formats[kind];fc.width=w;fc.height=h;fc.bytesperline[0]=bpl[0];fc.bytesperline[1]=bpl[1];fc.format->setup_plane_sz(&fc,sizes);}\n'
    code+='#if defined(__APPLE__)\n#define CAM_SECTION __attribute__((section("__DATA,__camlayout"),used))\n#else\n#define CAM_SECTION __attribute__((section(".cam_layout"),used))\n#endif\n'
    code+='CAM_SECTION const uint64_t donor_layout[]={sizeof(struct camera2_shot_ext),sizeof(struct camera2_stream),sizeof(struct is_crop),offsetof(struct is_crop,w),sizeof(struct v4l2_buffer),offsetof(struct camera2_shot_ext,shot),sizeof(struct camera2_node),CAPTURE_NODE_MAX,VIDEO_MAX_PLANES};\n'
    code+='const uint32_t donor_fourccs[]={'+','.join('V4L2_PIX_FMT_'+name for name in FORMATS)+'};\n'
    (out/'donor.c').write_text(code)
    (out/'donor.h').write_text('#include <stdint.h>\nvoid donor_calculate(unsigned,uint32_t,uint32_t,const uint32_t[2],uint32_t[3]);\nextern const uint64_t donor_layout[9];\nextern const uint32_t donor_fourccs[5];\n')
    (out/'extract.json').write_text(json.dumps(dict(formats=records,exact_function_sha256=extracted,shim='Fixed-width Linux types;exact source V4L2,timeval,format/frame/crop declarations;selected CAPTURE_NODE_MAX;no kernel implementation'),indent=2)+'\n')
    return records
