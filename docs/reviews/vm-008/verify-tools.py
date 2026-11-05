#!/usr/bin/env python3
"""Supplementary streamed checks of the selected IIG and install producer pins."""
import hashlib
import json
from pathlib import Path
import resource
import sys
import time

started=time.monotonic()
h=Path('/home/egor/dev/pet/s24-ios-exynos/worktrees/vm-008-20261105/artifacts/avf-kernel-headers')
out=Path(__file__).resolve().parent/'tools-verification.json'
result={'kind':'source-review','origin':'local-host','outcome':'fail','argv':[sys.executable,*sys.argv],'compiler_generator_guest_started':False,'bindings':{}}
def check(path,wanted):
    path=Path(path)
    with path.open('rb') as stream: actual=hashlib.file_digest(stream,'sha256').hexdigest()
    result['bindings'][str(path)]=actual
    if actual!=wanted: raise ValueError('Changed selected producer binding: '+str(path))
try:
    phase=json.loads((h/'iig-guard-1d8ebf6/report.json').read_text())
    producer=phase['public_iig_producer']
    check(producer['path'],producer['sha256'])
    check(producer['qualification_report'],producer['report_sha256'])
    lib=producer['libclang']
    check(lib['path'],lib['sha256']);check(lib['llvm_dependency'],lib['llvm_sha256'])
    parent=json.loads(Path(producer['qualification_report']).read_text())
    for name,wanted in parent['compiler_resource_headers_sha256'].items():
        check(Path('/usr/lib64/rocm/llvm/lib/clang/19/include')/name,wanted)
    for name,wanted in lib['c_api_headers_sha256'].items():
        check(Path('/usr/lib64/rocm/llvm/include')/name,wanted)
    install=json.loads((h/'headers-2/report.json').read_text())['header_host_tools']
    for key in ['decomment','replacecontents']: check(install[key],install[key+'_sha256'])
    check(h/'prepare-2/source/xnu/SETUP/decomment/decomment.c',install['source_sha256'])
    result['outcome']='pass'
except Exception as error: result['error']=repr(error)
finally:
    current={line.split(':',1)[0]:int(line.split()[1])*1024 for line in Path('/proc/self/status').read_text().splitlines() if line.startswith(('VmHWM:','VmRSS:'))}
    result.update(elapsed_seconds=round(time.monotonic()-started,3),files=len(result['bindings']),current_image_peak_rss_bytes=current['VmHWM'],current_rss_bytes=current['VmRSS'],raw_rusage_maxrss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024)
    out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='bindings'}))
sys.exit(0 if result['outcome']=='pass' else 1)
