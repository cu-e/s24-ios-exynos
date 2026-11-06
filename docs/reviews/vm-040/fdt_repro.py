#!/usr/bin/env python3
"""Source-backed predicate controls only; no compiler, QEMU or guest."""
import copy,hashlib,importlib.util,json,resource,struct
from pathlib import Path
P=Path('/home/egor/dev/pet/s24-ios-exynos/worktrees/vm-040-eh-20261106')
HERE=Path(__file__).resolve().parent
resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,)*2)
spec=importlib.util.spec_from_file_location('frozen_collector',P/'tools/run/avf_kernel_boot.py');c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
path=P/'artifacts/avf-kernel-boot/controls-9efba94-1/fdt/authored-input.dtb'
raw=path.read_bytes();props=c.fdt(raw)
layout={'payload_base':0x48000000};package={'size':64}
def probe(name,p):
 r={'name':name,'properties':{node+':'+key:v.hex()for(node,key),v in p.items()}}
 try:r['collector_result']=c.fdt_contract(p,layout,package);r['collector_accepts']=True
 except Exception as e:r['collector_accepts']=False;r['error']=str(e)
 return r
rows=[probe('producer-published-positive-fdt',props)]
rows[-1]['shim_memory_node_found']=props.get(('/memory@40000000','device_type'))==b'memory\0'
for key,value in [(('/pl011@9000000','compatible'),b'xarm,pl011\0'),(('/intc@8000000','compatible'),b'xarm,gic-v3\0')]:
 p=copy.deepcopy(props);p[key]=value;row=probe('prefix-compatible-'+key[0],p)
 needle=b'arm,pl011'if'pl011'in key[0]else b'arm,gic-v3'
 row['exact_nul_delimited_shim_compatible']=needle in value.rstrip(b'\0').split(b'\0');rows.append(row)
p=copy.deepcopy(props);p[('/intc@8000000','reg')]=struct.pack('>4Q',0x08000000,0,0x080a0000,0);rows.append(probe('zero-gic-extents',p))
source=Path('/home/egor/dev/pet/s24-ios-exynos/worktrees/vm-007-20261105/artifacts/avf-kernel-source/compose-final-ed9fdbf/profiles/qemu/scion/avf/shim')
r={'kind':'source-control-only','QEMU_executed':False,'compiler_executed':False,'source_sha256':hashlib.sha256((P/'tools/run/avf_kernel_boot.py').read_bytes()).hexdigest(),'control_fdt_sha256':hashlib.sha256(raw).hexdigest(),'source_pins':[{ 'path':str(source/f),'sha256':hashlib.sha256((source/f).read_bytes()).hexdigest()}for f in['avfboot.c','fdtx.c']],'cases':rows,'limitations':'Published/modified host fixture properties only; source oracle follows exact source comparisons, no C/shim execution and no guest result.'}
out=HERE/'runs/fdt-predicates-1';out.mkdir(parents=True,exist_ok=False);(out/'report.json').write_text(json.dumps(r,indent=2,sort_keys=True)+'\n')
print(json.dumps({'cases':[{k:v for k,v in row.items()if k!='properties'}for row in rows]},indent=2))
