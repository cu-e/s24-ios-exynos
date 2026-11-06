#!/usr/bin/env python3
"""Real-file parser/refusal and source-vector controls, never target execution."""
import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
from types import SimpleNamespace

sys.dont_write_bytecode = True
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--main',type=Path,required=True)
parser.add_argument('--vm008',type=Path,required=True)
parser.add_argument('--out',type=Path,required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[3]
path = root/'tools/build/avf_guest_link_inputs.py'
spec = importlib.util.spec_from_file_location('vm022_production',path)
m = importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
args.out = args.out.resolve();args.out.mkdir(parents=True,exist_ok=False)
report = dict(kind='host-test',origin='local-host',outcome='fail',source_only=True,
    checks=[],executor_sha256=m.sha(path),target_tool_executed=False,corpus_reaudited=False,
    kernel_image_produced=False,actual_product_admitted=False,initial_process=m.proc_status())
def require(name,value):
    if not value:raise AssertionError(name)
    report['checks'].append(name)
def reject(name,call):
    try:call()
    except (ValueError,struct.error,UnicodeDecodeError):report['checks'].append(name);return
    raise AssertionError('Missing rejection: '+name)
try:
    common = m.accepted_runner(args.main)
    future = root/'artifacts/avf-guest-link-inputs/link-execute-1'
    control = SimpleNamespace(main=args.main,vm008=args.vm008,execute_out=future,admission=None)
    plan = m.production_vectors(control,common)
    require('1080 exact unique source-supported ordered IDs',len(plan['ordered_ids'])==len(set(plan['ordered_ids']))==1080)
    require('eight genuine filelist Make vectors',len(plan['filelist_commands'])==8)
    require('fourteen genuine HIB and one KLD source selections',
        sum(len(row['variables']['HIB_FILES'].split()) for row in plan['components'].values())==14 and
        sum(len(row['variables']['KLD_FILES'].split()) for row in plan['components'].values())==1)
    require('link-only qualified runtime resource route exactly once',plan['link_argv'].count('-resource-dir')==1 and
            plan['link_argv'][plan['link_argv'].index('-resource-dir')+1]==plan['runtime_root'])
    require('DEVELOPMENT does not force RELEASE exports or discard undefined obligations',
            not any('-undefined' in arg or '-exported_symbols_list' in arg for arg in plan['link_argv']))
    require('1083 source archive members exclude nonlto',plan['archive_members']==1083 and not any(arg.endswith('/nonlto.o') for arg in plan['archive_argv']))
    require('no source-vector production root created',not future.exists())
    package_args = SimpleNamespace(**vars(control));package_args.execute_out=root/'artifacts/avf-guest-link-inputs/xnup-execute-1'
    package = m.xnup_vectors(package_args,common)
    require('missing image remains null rather than synthesized',package['image'] is None and package['argv'] is None)
    require('no guest execution implemented',not package['qemu_execution_implemented'] and not plan['qemu_execution_implemented'])
    reject('unqualified APFS/resource profile refuses before any producer reads',lambda:m.admission_inputs(
        dict(schema='avf-guest-link-admission-v1',profile={'manifest':{'sha256':common.FIREHOSE_MANIFEST}}),plan,common))
    frozen = args.main/'worktrees/vm-022-tail-cancellation-20261106/tools/build/avf_guest_link_inputs.py'
    require('exact corrected tail candidate baseline',m.sha(frozen)=='99d8db30fcfb3c510dadcecf1fb89121ed5062d3af3379442ac2e905c303b060')
    before = {node.name:node for node in ast.parse(frozen.read_text()).body if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name!='main'}
    after = {node.name:node for node in ast.parse(path.read_text()).body if isinstance(node,(ast.FunctionDef,ast.ClassDef))}
    require('all inherited tail/cleanup function and class ASTs unchanged',
            all(ast.dump(node)==ast.dump(after[name]) for name,node in before.items()))
    def malformed(name,data):
        file=args.out/(name+'.malformed');file.write_bytes(data);return file
    header=lambda count,extent,kind=2,cpu=0x100000c:struct.pack('<8I',0xfeedfacf,cpu,0,kind,count,extent,0,0)
    reject('reject actual short MachO file',lambda:m.bounded_macho(malformed('short',bytes(12)),image=True))
    reject('reject ELF rather than MachO',lambda:m.bounded_macho(malformed('elf',b'\x7fELF'+bytes(28)),image=True))
    reject('reject object passed as final image',lambda:m.bounded_macho(malformed('object',header(0,0,kind=1)),image=True))
    reject('reject wrong architecture image',lambda:m.bounded_macho(malformed('wrong-cpu',header(0,0,cpu=7)),image=True))
    reject('reject load commands beyond actual file',lambda:m.bounded_macho(malformed('commands',header(1,72)),image=True))
    reject('reject unaligned load command size',lambda:m.bounded_macho(malformed('command-size',header(1,8)+struct.pack('<II',25,7)),image=True))
    segment=struct.pack('<II16s4Q4I',25,72,b'__TEXT',0xfffffff007004000,8,104,16,5,5,0,0)
    reject('reject segment extent beyond actual file',lambda:m.bounded_macho(malformed('segment',header(1,72)+segment),image=True))
    thread=struct.pack('<4I',5,288,7,68)+bytes(272)
    reject('reject wrong ARM64 thread flavor',lambda:m.bounded_macho(malformed('thread',header(1,288)+thread),image=True))
    reject('reject malformed archive header',lambda:m.stream_archive(malformed('ar',b'!<arch>\n'+bytes(60))))
    reject('reject XNUP aggregate length mismatch',lambda:m.inspect_xnup(malformed('xnup-length',struct.pack('<II',0x50554e58,1)),dict(file_size=1,sha256='0'*64)))
    reject('reject XNUP missing kernel entries',lambda:m.inspect_xnup(malformed('xnup-empty',struct.pack('<II',0x50554e58,24)+bytes(24)),dict(file_size=1,sha256='0'*64)))
    entry=lambda name,data:struct.pack('<16sII',name,len(data),0)+data+bytes(-len(data)%16)
    body=entry(b'kernel',b'x')+entry(b'cmdline',b'-v avf_exit=1\0')
    witness=dict(file_size=1,sha256=hashlib.sha256(b'x').hexdigest())
    reject('reject actual XNUP body without terminal entry',lambda:m.inspect_xnup(
        malformed('xnup-no-terminator',struct.pack('<II',0x50554e58,len(body))+body),witness))
    duplicate=entry(b'kernel',b'x')*2+bytes(24)
    reject('reject duplicate XNUP kernel entry',lambda:m.inspect_xnup(
        malformed('xnup-duplicate',struct.pack('<II',0x50554e58,len(duplicate))+duplicate),witness))
    # Integer source vectors plus actual existing shim header; not a kernel image.
    layout_vector=dict(segments=[dict(address=0xfffffff007004000,size=0x200000)],entry=0xfffffff007004000)
    layout=m.shim_layout(layout_vector,package['shim']['path'],4096)
    require('actual shim header plus source-sized console layout vector fits256MiB',
            layout['kernel_low']>layout['shim_end'] and not layout['runtime_qualified'])
    too_large=dict(segments=[dict(address=0xfffffff007004000,size=220*1024**2)],entry=0xfffffff007004000)
    reject('reject source layout vector exceeding genuine shim reserve',lambda:m.shim_layout(too_large,package['shim']['path'],4096))
    reject('reject oversized u32 XNUP payload extent',lambda:m.shim_layout(layout_vector,package['shim']['path'],2**32))
    reject('reject malformed Linux shim Image header',lambda:m.shim_layout(layout_vector,malformed('shim-header',bytes(64)),4096))
    # Positive parsing uses actual fresh source-built pthread bytes; raw product
    # review is pending, so these observations grant zero link/provider credit.
    descriptor=args.main/'worktrees/vm-021-20261106/fixtures/public/avf-guest-pthread/built-component.json'
    built=common.load_project(descriptor,'7e4a149b08b03026c29a6e3059903fa329e238715ff4cbd4c0ac9aab4d5d5353')
    actual=m.stream_archive(built['archive']['path'])
    require('stream actual fresh3-member pthread archive ordinal bytes',
            [(r['name'],r['sha256']) for r in actual]==[(r['name'],r['sha256']) for r in built['archive']['members']])
    reject('reject actual archive with truncated final member/padding',lambda:m.stream_archive(
        malformed('truncated-real-ar',Path(built['archive']['path']).read_bytes()[:-1])))
    object_row=built['objects'][0];view=m.bounded_macho(object_row['path'])
    require('inspect actual fresh pthread object symbol definitions/imports',view['sha256']==object_row['sha256'] and
        sorted(name for name,row in view['external_symbols'].items() if row['undefined'])==sorted(object_row['imports']) and
        sorted(name for name,row in view['external_symbols'].items() if not row['undefined'])==sorted(object_row['definitions']))
    reject('actual relocatable guest object cannot be packaged as kernel',lambda:m.bounded_macho(object_row['path'],image=True))
    report['raw_component_only_parser_witness']=dict(path=str(descriptor),sha256=m.sha(descriptor),independent_acceptance=False,link_credit=0)
    report['outcome']='pass'
except Exception as error:report['error']=repr(error)
finally:
    report['final_process']=m.proc_status()
    (args.out/'evidence.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
raise SystemExit(0 if report['outcome']=='pass' else 1)
