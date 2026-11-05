#!/usr/bin/env python3
"""Bounded USB-001 host tests and ARM compilation; performs no device I/O."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess

ROOT=Path(__file__).resolve().parents[3]
SRC=Path(__file__).resolve().parent
DEFAULT_LAB=Path('/home/egor/dev/pet/s24-ios-exynos')
BSP_REV='f85e53cfa5497ead5d78821efbac84e51f37a4e1'
CURRENT_REV='417484173abc2c4fa93e738ea82ad9f2e84911b1'
FILES=[
 'arch/arm64/boot/dts/exynos/s5e9945-usb.dtsi',
 'arch/arm64/boot/dts/samsung/e1s/s5e9945-e1s_common.dtsi',
 'arch/arm64/boot/dts/samsung/e1s/e1s_eur_openx_w01_r17.dts',
 'include/dt-bindings/interrupt-controller/s5e9945.h',
 'drivers/usb/dwc3/dwc3-exynos.c',
 'drivers/usb/dwc3/dwc3-exynos-otg.c',
 'drivers/usb/dwc3/core.c',
 'drivers/phy/samsung/phy-exynos-usbdrd.c',
 'Documentation/devicetree/bindings/usb/samsung,exynos-dwc3.yaml']

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def enabled_repeater_nodes(text):
    """Extract declared enabled children of hsi2c_34 in the pinned retail DTS.

    This bounded source-fact extractor is not a DTS preprocessor or live-DTB
    validator. Literal #if 0 templates are excluded; unexpected directives
    inside a selected controller fail rather than guessing board selection.
    """
    text=re.sub(r'/\*.*?\*/|//[^\n]*','',text,flags=re.S)
    text=re.sub(r'^\s*#if\s+0\s*$.*?^\s*#endif\s*$','',text,flags=re.M|re.S)
    def body_at(start):
        depth=1;at=start
        while at<len(text) and depth:
            if text[at]=='"':
                at+=1
                while at<len(text) and text[at]!='"':
                    at+=2 if text[at]=='\\' else 1
            elif text[at]=='{':depth+=1
            elif text[at]=='}':depth-=1
            at+=1
        if depth:raise ValueError('Unbalanced pinned DTS source')
        return text[start:at-1],at
    def direct_properties(body):
        # Child nodes cannot supply their parent's status or compatible.
        depth=0;direct=[]
        for char in body:
            if char=='{':depth+=1
            elif char=='}':depth-=1
            elif depth==0:direct.append(char)
        return ''.join(direct)
    nodes=[]
    for controller in re.finditer(r'&hsi2c_34\s*\{',text):
        body,end=body_at(controller.end())
        if re.search(r'^\s*#(?!address-cells|size-cells)',body,re.M):
            raise ValueError('Unsupported conditional inside repeater controller')
        if not re.search(r'\bstatus\s*=\s*"okay"',direct_properties(body)):continue
        for child in re.finditer(r'([\w-]+-repeater@[\da-fA-F]+)\s*\{',body):
            child_body,_=body_at(controller.end()+child.end())
            props=direct_properties(child_body)
            if not re.search(r'\bstatus\s*=\s*"okay"',props):continue
            compatible=re.search(r'\bcompatible\s*=\s*"([^"\n]+)"',props)
            address=re.search(r'\breg\s*=\s*<(0x[\da-fA-F]+)>',props)
            if not compatible or not address:raise ValueError('Incomplete repeater source node')
            nodes.append(dict(node=child[1],compatible=compatible[1],I2C_7bit_address=hex(int(address[1],16)),status='okay'))
    return sorted(nodes,key=lambda node:node['compatible'])

def repeater_profile_matches(text,profile):
    nodes=enabled_repeater_nodes(text)
    return len(nodes)==2 and profile['I2C_controller']=='hsi2c_34' and nodes==sorted(profile['enabled_source_nodes'],key=lambda node:node['compatible'])

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',required=True)
    p.add_argument('--lab-root',type=Path,default=DEFAULT_LAB)
    p.add_argument('--host-clang',type=Path,default=Path('/home/egor/.local/bin/clang'))
    p.add_argument('--clang',type=Path,default=Path('/home/egor/Android/Sdk/ndk/28.2.13676358/toolchains/llvm/prebuilt/linux-x86_64/bin/clang'))
    args=p.parse_args()
    if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,79}',args.run):raise ValueError('Fresh canonical run name required')
    out=ROOT/'artifacts/usb-readonly'/args.run
    if out.resolve()!=out:raise ValueError('Symlink output is forbidden')
    out.mkdir(parents=True,exist_ok=False)
    lab=args.lab_root.resolve()
    report=dict(kind='host-test',origin='local-host',outcome='fail',recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
        commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),commands=[],checks=[],
        summary='Attempted bounded host USB/read-only protocol qualification;actual result and errors retained',
        device_executed=False,device_io=False,MMIO_executed=False,native_driver_built=False,ARM_executed=False,Apple_SDK_used=False)
    def check(name,value,**data):report['checks'].append(dict(name=name,pass_check=bool(value),**data))
    def run(argv,label,env=None,success=True):
        argv=[str(a) for a in argv]
        try:r=subprocess.run(argv,cwd=ROOT,capture_output=True,text=True,timeout=45,env=env)
        except subprocess.TimeoutExpired:
            report['commands'].append(dict(argv=argv,exit_code=None,timeout=True));raise RuntimeError('Actual process exceeded45 second deadline')
        stdout=out/(label+'.stdout.txt');stderr=out/(label+'.stderr.txt');stdout.write_text(r.stdout);stderr.write_text(r.stderr)
        report['commands'].append(dict(argv=argv,cwd=str(ROOT),exit_code=r.returncode,stdout=str(stdout.relative_to(lab)),stderr=str(stderr.relative_to(lab))))
        if success and r.returncode:raise RuntimeError(label+' failed: '+r.stderr[-1600:])
        return r.stdout
    try:
        snap=out/'source';snap.mkdir()
        for name in ['readonly.h','readonly.c','fixture.c','layout.cpp','sanitizer-control.c','check.py','profile.json','README.md']:
            shutil.copyfile(SRC/name,snap/name)
        source_review={}
        profile=json.loads((snap/'profile.json').read_text())['USB2_repeaters']
        for label,repo,revision in [('reference',lab/'references/s24-bsp-reference',BSP_REV),('comparison',lab/'references/s24-linux',CURRENT_REV)]:
            actual=run(['git','-C',repo,'rev-parse','HEAD'],label+'-revision').strip()
            check(label+'-pinned-head',actual==revision)
            rows={}
            for i,name in enumerate(FILES):
                text=run(['git','-C',repo,'show',revision+':'+name],label+'-source-'+str(i))
                rows[name]=dict(sha256=hashlib.sha256(text.encode()).hexdigest(),bytes=len(text.encode()))
                if label in ('reference','comparison'):
                    if name.endswith('s5e9945-usb.dtsi'):
                        check(label+'-exact-DWC3-PHY-source-tokens',all(s in text for s in ['"samsung,exynos-dwusb"','"synopsys,dwc3"','0x17900000 0x10000','0x178D0000 0x800','0x178E0000 0x800','phy_version = <0x600>','sub_phy_version = <0x801>','snps_usbdp_ram_mode = <1>','"aclk", "sclk", "bus"']))
                    elif name.endswith('s5e9945-e1s_common.dtsi'):
                        check(label+'-exact-board-enable-supplies-port',all(s in text for s in ['&udc {','&usbdrd_dwc3 {','maximum-speed = "super-speed"','phy,gpio_phy_port = <&gpc7 1 0x0>','vdd075_usb-supply = <&s5_l2_reg>','vdd12_usb-supply = <&s4_l4_reg>']))
                    elif name.endswith('e1s_eur_openx_w01_r17.dts'):
                        nodes=enabled_repeater_nodes(text)
                        check(label+'-complete-retail-eUSB-repeater-profile',repeater_profile_matches(text,profile),extracted_source_nodes=nodes)
                        for omitted in profile['enabled_source_nodes']:
                            incomplete={**profile,'enabled_source_nodes':[node for node in profile['enabled_source_nodes'] if node!=omitted]}
                            check(label+'-reject-profile-omission-'+omitted['compatible'],not repeater_profile_matches(text,incomplete))
                            disabled=text.replace('compatible = "'+omitted['compatible']+'"','compatible = "removed-for-negative-control"')
                            check(label+'-reject-source-mismatch-'+omitted['compatible'],not repeater_profile_matches(disabled,profile))
                    elif name.endswith('interrupt-controller/s5e9945.h'):
                        check(label+'-exact-source-IRQ-tokens',re.search(r'#define INTREQ__USB32DRD_GIC0\s+403\b',text) is not None and re.search(r'#define INTREQ__USB2_REMOTE_WAKEUP_GIC\s+401\b',text) is not None)
                    elif name.endswith('dwc3-exynos.c'):
                        check(label+'-actual-parent-and-core-DMA36-requests','dma_set_mask_and_coherent(dev, DMA_BIT_MASK(36))' in text and 'dma_set_mask_and_coherent(exynos->dwc->dev, DMA_BIT_MASK(36))' in text)
            source_review[label]=dict(repository=str(repo.relative_to(lab)),revision=revision,files=rows)
        source_review['comparison_note']='Equality/differences are source comparisons only;neither pin proves live BYH3 controller state or successful native operation.'
        source_review['identical_files']=[n for n in FILES if source_review['reference']['files'][n]['sha256']==source_review['comparison']['files'][n]['sha256']]
        (out/'source-review.json').write_text(json.dumps(source_review,indent=2)+'\n');report['source_review']=source_review
        flags=['-Wall','-Wextra','-Werror','-Wpedantic']
        for compiler,label in [('cc','host-cc'),(args.host_clang,'host-clang'),(args.clang,'target-clang')]:run([compiler,'--version'],label)
        run([args.host_clang,'-print-resource-dir'],'host-runtime-resource')
        run([args.host_clang,'-fsanitize=address,undefined','-###',snap/'sanitizer-control.c','-o',out/'control'],'host-runtime-link-plan')
        run([args.host_clang,'-std=c11',*flags,'-O1','-g','-fno-omit-frame-pointer','-fsanitize=address,undefined',snap/'sanitizer-control.c','-o',out/'control'],'sanitizer-control-build')
        for selector,diagnostic in [('asan','AddressSanitizer: heap-buffer-overflow'),('ubsan','runtime error: signed integer overflow')]:
            run([out/'control',selector],'negative-'+selector,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=1:halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'},success=False)
            check('verified-negative-'+selector,report['commands'][-1]['exit_code']!=0 and diagnostic in (out/('negative-'+selector+'.stderr.txt')).read_text())
        run(['cc','-std=c11',*flags,'-c',snap/'readonly.c','-o',out/'host-core.o'],'host-core')
        run(['c++','-std=c++17',*flags,'-c',snap/'layout.cpp','-o',out/'host-layout.o'],'host-layout')
        run([args.host_clang,'-std=c11',*flags,'-O1','-g','-fno-omit-frame-pointer','-fsanitize=address,undefined',snap/'readonly.c',snap/'fixture.c','-o',out/'fixture'],'host-sanitizer-build')
        image=out/'readonly-test-image';image.write_bytes(bytes(i%251 for i in range(131072)));before=sha(image)
        result=json.loads(run([out/'fixture',image],'host-sanitizer-run',env={**os.environ,'ASAN_OPTIONS':'detect_leaks=1:halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'}))
        expected=struct.pack('<4sHHQQQII',b'S24R',1,1,7,1,512,512,0).hex()
        check('independent-Python-wire-vector',result.get('golden_request_hex')==expected)
        check('actual-host-sanitizer-and-read-only-file',result.get('outcome')=='pass' and result.get('mutation_inputs')==20000 and result.get('readonly_file_read_bytes')==512 and result.get('device_io') is False and sha(image)==before)
        report['result']=result;report['object_headers']={}
        for target,label in [('aarch64-none-elf','aarch64-elf'),('arm64-apple-ios16.5','arm64-ios')]:
            for name,standard in [('readonly.c','-std=c11'),('layout.cpp','-std=c++17')]:
                obj=out/(label+'-'+name+'.o')
                run([args.clang,'--target='+target,'-ffreestanding',standard,*flags,'-c',snap/name,'-o',obj],label+'-'+name+'-compile')
                headers=run([args.clang.parent/'llvm-readobj','--file-headers',obj],label+'-'+name+'-headers')
                run([args.clang.parent/'llvm-nm','--undefined-only',obj],label+'-'+name+'-imports')
                check(label+'-'+name+'-real-format',('elf64-littleaarch64' if label=='aarch64-elf' else 'Mach-O arm64') in headers)
                report['object_headers'][obj.name]=headers
        report['outcome']='pass' if all(c['pass_check'] for c in report['checks']) else 'fail'
        report['summary']='Owned read-only block/client/server/DMA arithmetic boundary;host sanitizer,real read-only file,independent wire vector and4 ARM compile-only objects;no USB controller or device execution'
    except Exception as error:report['error']=str(error)
    files=sorted(p for p in out.rglob('*') if p.is_file())
    report['artifacts']=[str(p.relative_to(lab)) for p in files]
    report['sha256']={str(p.relative_to(lab)):sha(p) for p in files}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    evidence=dict(report);evidence['artifacts'].append(str((out/'report.json').relative_to(lab)));evidence['sha256'][str((out/'report.json').relative_to(lab))]=sha(out/'report.json')
    (out/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps({k:report.get(k) for k in ['outcome','error','result','summary']},indent=2))
    return 0 if report['outcome']=='pass' else 1

if __name__=='__main__':raise SystemExit(main())
