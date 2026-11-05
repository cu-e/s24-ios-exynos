#!/usr/bin/env python3
"""Build source oracles without executing any Linux hardware callback."""
import hashlib
import json
from pathlib import Path
import re


def function(text, name):
    match = re.search(r"(?:static\s+)?(?:inline\s+)?[\w*]+\s+" + re.escape(name) + r"\s*\(", text)
    if not match:
        raise ValueError("Missing genuine source function " + name)
    start = match.start()
    brace = text.index("{", match.end())
    depth, end = 1, brace + 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


def generate(cache, out):
    cache, out = Path(cache), Path(out)
    files = {
        "pcm": cache / "include/sound/pcm.h",
        "rdma": cache / "sound/soc/samsung/exynos/abox/abox_rdma.c",
        "wdma": cache / "sound/soc/samsung/exynos/abox/abox_wdma.c",
        "abox": cache / "sound/soc/samsung/exynos/abox/abox.h",
        "sizes": cache / "include/linux/sizes.h",
        "formats": cache / "sound/core/pcm_misc.c",
    }
    source = {name: path.read_text() for name, path in files.items()}
    fragments = {}
    for name in ("bytes_to_frames", "frames_to_bytes"):
        fragments[name] = function(source["pcm"], name)
    for direction in ("rdma", "wdma"):
        fragments[direction + "_pointer"] = function(source[direction], "abox_" + direction + "_pointer")
        body = function(source[direction], "abox_" + direction + "_hw_params")
        begin = body.index("pcmtask_msg->channel_id = id;")
        finish = body.index("\n\tret = abox_" + direction + "_request_ipc", begin)
        fragments[direction + "_set_buffer"] = body[begin:finish]
        begin = body.index("pcmtask_msg->msgtype = PCM_PLTDAI_HW_PARAMS;")
        finish = body.index("\n\tret = abox_" + direction + "_request_ipc", begin)
        fragments[direction + "_hw_params"] = body[begin:finish]
    macros = []
    for name in ("SZ_16", "SZ_128", "SZ_64K", "SZ_256K", "SZ_1M"):
        macros.append(re.search(r"^#define\s+" + name + r"\s+[^\n]+", source["sizes"], re.M)[0])
    for name in ("BUFFER_BYTES_MIN", "BUFFER_BYTES_MAX", "PERIOD_BYTES_MIN", "PERIOD_BYTES_MAX",
                 "IOVA_RDMA_BUFFER_BASE", "IOVA_RDMA_BUFFER", "IOVA_WDMA_BUFFER_BASE", "IOVA_WDMA_BUFFER"):
        macros.append(re.search(r"^#define\s+" + name + r"(?:\([^\n]*?\))?\s+[^\n]+", source["abox"], re.M)[0])
    formats = []
    for name in ("S16_LE", "S24_LE", "S24_3LE", "S32_LE"):
        pattern = r"\[SNDRV_PCM_FORMAT_" + name + r"\]\s*=\s*\{.*?\n\t\}"
        record = re.search(pattern, source["formats"], re.S)[0]
        formats.append(record[record.index("{"):])
    # Host scaffolding supplies only context objects/accessors. Source functions,
    # integer macros and initializers below remain byte-for-byte source slices.
    prelude = r'''
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include "oracle_api.h"
typedef long snd_pcm_sframes_t;
typedef unsigned long snd_pcm_uframes_t;
struct snd_pcm_runtime { unsigned int frame_bits; };
struct device { int unused; };
struct abox_dma_data { struct device *dev; unsigned int id, pointer; int type; };
struct snd_soc_dai { struct abox_dma_data *data; };
struct snd_soc_pcm_runtime { struct snd_soc_dai *dai; };
struct snd_pcm_substream { struct snd_pcm_runtime *runtime; struct snd_soc_pcm_runtime *rtd; };
struct snd_soc_component { int unused; };
#define asoc_substream_to_rtd(p) ((p)->rtd)
#define asoc_rtd_to_cpu(p,n) ((void)(n),(p)->dai)
#define snd_soc_dai_get_drvdata(p) ((p)->data)
#define abox_dbg(dev,...) ((void)(dev))
enum { PLATFORM_NORMAL, PLATFORM_CALL, PLATFORM_COMPRESS, PLATFORM_REALTIME, PLATFORM_VI_SENSING, PLATFORM_SYNC };
static int abox_rdma_progress(struct abox_dma_data *data) { (void)data; abort(); }
static int abox_wdma_progress(struct abox_dma_data *data) { (void)data; abort(); }
static unsigned abox_dma_read_pointer(struct abox_dma_data *data) { (void)data; abort(); }
struct snd_pcm_hw_params { unsigned rate,width,channels,format,period,periods; };
#define params_period_bytes(p) ((p)->period)
#define params_periods(p) ((p)->periods)
#define params_rate(p) ((p)->rate)
#define params_width(p) ((p)->width)
#define params_channels(p) ((p)->channels)
#define params_format(p) ((p)->format)
/* Oracle-local lookup index, never an ALSA or firmware ABI format value. */
#define SNDRV_PCM_FORMAT_S24_3LE 2
struct pcm_format_data { unsigned char width,phys; signed char le,signd; unsigned char silence[8]; };
'''
    ipc = cache / "include/sound/samsung/abox_ipc.h"
    chunks = ["/* Generated test oracle. Preserve GPL/component source notices in the source cache. */\n", prelude,
              '#include "' + str(ipc.resolve()) + '"\n', "\n".join(macros),
              "\nstatic const struct pcm_format_data formats[] = {\n" + ",\n".join(formats) + "\n};\n"]
    chunks += [fragments[k] + "\n" for k in ("bytes_to_frames", "frames_to_bytes", "rdma_pointer", "wdma_pointer")]
    chunks += [r'''
uint64_t oracle_value(unsigned i) {
    const uint64_t values[] = { sizeof(ABOX_IPC_MSG), sizeof(struct IPC_PCMTASK_MSG),
      sizeof(struct PCMTASK_SET_BUFFER), sizeof(struct PCMTASK_HW_PARAMS),
      offsetof(ABOX_IPC_MSG,msg.pcmtask.param), offsetof(ABOX_IPC_MSG,msg.pcmtask.param.setbuff.phys),
      IPC_PCMPLAYBACK, IPC_PCMCAPTURE, PCM_SET_BUFFER, PCM_PLTDAI_HW_PARAMS,
      PCM_PLTDAI_POINTER, PCM_PLTDAI_CLOSED, BUFFER_BYTES_MAX, PERIOD_BYTES_MIN, PERIOD_BYTES_MAX,
      IOVA_RDMA_BUFFER(0), IOVA_WDMA_BUFFER(0), sizeof(enum PCMMSG) };
    return i < sizeof(values)/sizeof(values[0]) ? values[i] : 0;
}
unsigned oracle_width(unsigned i) { return i < 4 ? formats[i].width : 0; }
unsigned oracle_physical_width(unsigned i) { return i < 4 ? formats[i].phys : 0; }
uint64_t oracle_frame_bytes(unsigned bits, unsigned frames) {
    struct snd_pcm_runtime runtime = {bits}; return frames_to_bytes(&runtime,frames);
}
uint64_t oracle_pointer(unsigned direction, unsigned frame_bits, unsigned pointer) {
    struct snd_pcm_runtime runtime = {frame_bits};
    struct device dev = {0};
    struct abox_dma_data data = {&dev,0,pointer,PLATFORM_NORMAL};
    struct snd_soc_dai dai = {&data}; struct snd_soc_pcm_runtime rtd = {&dai};
    struct snd_pcm_substream stream = {&runtime,&rtd};
    return direction ? abox_wdma_pointer(NULL,&stream) : abox_rdma_pointer(NULL,&stream);
}
void oracle_message(unsigned direction, unsigned kind, unsigned format,
 unsigned rate, unsigned channels, unsigned period_bytes, unsigned periods, unsigned pointer, void *out) {
    ABOX_IPC_MSG msg;
    memset(&msg,0xa5,sizeof(msg));
    struct IPC_PCMTASK_MSG *pcmtask_msg = &msg.msg.pcmtask;
    struct snd_pcm_hw_params parameters = {rate,oracle_width(format),channels,format,period_bytes,periods};
    struct snd_pcm_hw_params *params = &parameters;
    unsigned id = 0, iova = direction ? IOVA_WDMA_BUFFER(id) : IOVA_RDMA_BUFFER(id);
''']
    for direction, code in ((0, "rdma"), (1, "wdma")):
        chunks.append(("    if" if direction == 0 else "    else if") + f" (direction == {direction}) {{\n")
        chunks.append(fragments[code + "_set_buffer"] + "\n")
        chunks.append("        if (kind == 1) {\n" + fragments[code + "_hw_params"] + "\n        }\n    }\n")
    chunks.append(r'''
    if (kind == 2 || kind == 3) {
        pcmtask_msg->msgtype = kind == 2 ? PCM_PLTDAI_POINTER : PCM_PLTDAI_CLOSED;
        pcmtask_msg->param.pointer = pointer;
    }
    memcpy(out,&msg,sizeof(msg));
}
#ifdef ORACLE_MAIN
#include <stdio.h>
int main(void) {
    printf("{\"layout\":[");
    for (unsigned i=0;i<18;i++) printf("%s%llu",i?",":"",(unsigned long long)oracle_value(i));
    printf("],\"physical_widths\":[");
    for(unsigned i=0;i<4;i++) printf("%s%u",i?",":"",oracle_physical_width(i));
    puts("]}"); return 0;
}
#endif
''')
    (out / "oracle.c").write_text("\n".join(chunks))
    metadata = {"files": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files.values()},
                "unchanged_fragments": {name: {"sha256": hashlib.sha256(code.encode()).hexdigest(), "text": code}
                                        for name, code in fragments.items()},
                "integer_macros": macros, "unchanged_format_initializers": formats,
                "scaffolding": "Context/accessor objects only; hardware fallback functions abort. Private format lookup indices make no ABI-ID claim."}
    (out / "oracle-source.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return metadata
