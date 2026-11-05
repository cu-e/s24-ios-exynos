#!/usr/bin/env python3
"""Independent actual Apple-tree decoder and byte controls; no guest operations."""
import argparse,copy,hashlib,importlib.util,json,os,re,struct,subprocess
from pathlib import Path

ROOT=Path('/home/egor/dev/pet/s24-ios-exynos')
PRODUCER=ROOT/'worktrees/vm-027-20261106'
FINAL='250bce50945ab0c79235dabcd0bd355a44623d0d'
ENV=dict(os.environ,GIT_NO_LAZY_FETCH='1',GIT_OPTIONAL_LOCKS='0',PYTHONDONTWRITEBYTECODE='1')
def sha(path):
 with Path(path).open('rb')as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def load(path):return json.loads(Path(path).read_text())
def decode(data):
 """Iterative preorder reader; retain property order and absolute byte offsets."""
 if not 8<=len(data)<=65536:raise ValueError('size')
 position=0;flat={};root=None;frames=[dict(parent=None,left=1,depth=1)]
 def take(count):
  nonlocal position
  if count<0 or count>len(data)-position:raise ValueError('extent')
  start=position;position+=count;return data[start:position]
 while frames:
  frame=frames[-1]
  if not frame['left']:frames.pop();continue
  frame['left']-=1
  if frame['depth']>16 or len(flat)>=512:raise ValueError('budget')
  start=position;np,nc=struct.unpack('<II',take(8))
  if np<1 or np>2048 or nc>512:raise ValueError('counts')
  props=[];names=set()
  for _ in range(np):
   header=position;key=take(32);end=key.find(b'\0')
   if end<=0 or any(key[end+1:]):raise ValueError('property name')
   name=key[:end].decode('ascii')
   if name in names or not all(32<=ord(c)<=126 for c in name):raise ValueError('duplicate/invalid property')
   names.add(name);length=struct.unpack('<I',take(4))[0];value_at=position;value=take(length)
   if any(take((-length)%4)):raise ValueError('padding')
   props.append(dict(name=name,value=value,header=header,value_at=value_at))
  values={p['name']:p['value']for p in props};name=values.get('name',b'')
  if not name.endswith(b'\0')or b'\0'in name[:-1]:raise ValueError('node string')
  name=name[:-1].decode('ascii')
  if not name or len(name)>63 or '/'in name or name in ['.','..']:raise ValueError('node component')
  parent=frame['parent'];path='/'if parent is None else parent['path'].rstrip('/')+'/'+name
  if parent is None and name!='device-tree':raise ValueError('root')
  if path in flat:raise ValueError('duplicate node')
  node=dict(path=path,offset=start,props=props,children=[]);flat[path]=node
  if parent is None:root=node
  else:parent['children'].append(node)
  if nc:frames.append(dict(parent=node,left=nc,depth=frame['depth']+1))
 if position!=len(data):raise ValueError('trailing data')
 return root,flat
def encode(node):
 data=bytearray(struct.pack('<II',len(node['props']),len(node['children'])))
 for prop in node['props']:
  value=prop['value'];name=prop['name'].encode('ascii')
  data+=name.ljust(32,b'\0')+struct.pack('<I',len(value))+value+b'\0'*((-len(value))%4)
 for child in node['children']:data+=encode(child)
 return bytes(data)
def find(node,path):
 if node['path']==path:return node
 for child in node['children']:
  found=find(child,path)
  if found:return found
 return None
def set_prop(node,path,name,value):
 entry=find(node,path)
 for prop in entry['props']:
  if prop['name']==name:prop['value']=value;return
 raise KeyError((path,name))
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);args=ap.parse_args();out=args.out;out.mkdir(parents=True,exist_ok=False)
 report=dict(kind='host-test',origin='local-host',outcome='fail',checks=[],inputs={},source_reads=[],controls=[],compiler_executed=False,guest_executed=False)
 def check(name,condition):
  report['checks'].append(dict(name=name,passed=bool(condition)))
  if not condition:raise AssertionError(name)
 def bind(path,wanted=None,size=None):
  path=Path(path);actual=sha(path);report['inputs'][str(path)]=actual
  check('hash-'+str(path),wanted is None or actual==wanted)
  if size is not None:check('size-'+str(path),path.stat().st_size==size)
  return path
 def git(repo,spec):
  argv=['git','-C',str(repo),'show',spec];p=subprocess.run(argv,env=ENV,capture_output=True,timeout=15);report['source_reads'].append(dict(argv=argv,exit_code=p.returncode,stdout_sha256=hashlib.sha256(p.stdout).hexdigest(),stderr_sha256=hashlib.sha256(p.stderr).hexdigest(),environment_overrides={k:ENV[k]for k in['GIT_NO_LAZY_FETCH','GIT_OPTIONAL_LOCKS']}));check('pinned-git-read',p.returncode==0);return p.stdout
 try:
  capsule_path=PRODUCER/'docs/procedures/avf-guest-device-tree/evidence-capture.json';capsule=load(bind(capsule_path));check('exact-final-capsule',capsule_path.read_bytes()==git(ROOT,FINAL+':docs/procedures/avf-guest-device-tree/evidence-capture.json'))
  for row in capsule['artifact_bindings']:bind(ROOT/row['path'],row['sha256'],row['size'])
  historical=load(PRODUCER/'docs/procedures/avf-guest-device-tree/evidence.json');check('historical-inconclusive-retained',historical['outcome']=='inconclusive'and sha(PRODUCER/'docs/procedures/avf-guest-device-tree/evidence.json')==capsule['source_only_capsule_preserved']['sha256'])
  for row in historical['artifact_bindings']:bind(ROOT/row['path'],row['sha256'],row['size'])
  for name in ['tools/build/avf_guest_device_tree.py','fixtures/public/avf-guest-device-tree/capture.py','fixtures/public/avf-guest-device-tree/source-pins.json','fixtures/public/avf-guest-device-tree/actual_controls.py']:
   check('frozen-source-'+name,(PRODUCER/name).read_bytes()==git(ROOT,FINAL+':'+name))
  pins=load(PRODUCER/'fixtures/public/avf-guest-device-tree/source-pins.json');sources={}
  for row in pins['files']:
   path=bind(ROOT/row['path'],row['sha256'],row['size']);data=path.read_bytes();check('content-blob-'+path.name,hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==row['content_git_blob_sha1']);sources[path.name]=data.decode()
   if row['origin']=='canonical-Scion-source':
    relative=row['path'].split('/originals/scion/',1)[1]
    if path.name=='THIRD_PARTY_LICENSES.md':
     # The promisor reference has the tree entry but lacks this non-code blob.
     # Bind the cached bytes to the pinned tree's object ID without fetching.
     argv=['git','-C',str(ROOT/'references/scion-avf'),'ls-tree',pins['scion_commit'],'--',relative];p=subprocess.run(argv,env=ENV,capture_output=True,timeout=15);report['source_reads'].append(dict(argv=argv,exit_code=p.returncode,stdout_sha256=hashlib.sha256(p.stdout).hexdigest(),stderr_sha256=hashlib.sha256(p.stderr).hexdigest(),environment_overrides={k:ENV[k]for k in['GIT_NO_LAZY_FETCH','GIT_OPTIONAL_LOCKS']}));check('pinned-license-tree-identity',p.returncode==0 and p.stdout.decode().strip()=='100644 blob '+row['content_git_blob_sha1']+'\t'+relative)
    else:check('genuine-Scion-'+path.name,data==git(ROOT/'references/scion-avf',pins['scion_commit']+':'+relative))
  writer=sources['avfboot.c'];check('genuine-serialization-writer','uint32_t *counts[16]'in writer and'*(volatile uint32_t *)(w->cur + 32) = len;'in writer and'w->cur += 36 + ((len + 3) & ~3u);'in writer and'ba->deviceTreeLength = dt_len;'in writer)
  check('genuine-timer-fixed-27',re.search(r'#define\s+GIC_INTID_VTIMER\s+27\b',sources['gic_v3_irq.c'])and'virtual-timer-intid'not in sources['gic_v3_irq.c'])
  check('genuine-UART-PCI-consumer-selection','strcmp(uart_compat, "ns16550a")'in sources['pe_serial.c']and'pci.shift = 20;'in sources['hakios.pci.c']and'pci.shift = 16;'in sources['hakios.pci.c'])
  capture=load(PRODUCER/'artifacts/avf-guest-device-tree/capture-1/report.json');plan=capture['plan'];check('capture-pass-boundaries',capture['outcome']=='pass'and capture['exit_code']==0 and not capture['after']['owned_processes']and capture['after']['owned_tree_rss_bytes']==0 and not capture['xnu_executed']and not capture['pid1_executed'])
  check('exact-reviewed-plan',plan==load(PRODUCER/'artifacts/avf-guest-device-tree/capture-plan-2.json')and sha(PRODUCER/'artifacts/avf-guest-device-tree/capture-plan-2.json')==capsule['plan_sha256'])
  for row in plan['pins'].values():bind(row['path'],row['sha256'],row['size'])
  bind(plan['accepted_supervisor']['path'],plan['accepted_supervisor']['sha256']);check('actual-runner-source',sha(PRODUCER/'fixtures/public/avf-guest-device-tree/capture.py')==plan['capture_script_sha256'])
  sent=[x['sent']for x in capture['qmp']if'sent'in x];check('exact-QMP-sequence',[x['execute']for x in sent]==['qmp_capabilities','stop','query-status','pmemsave','quit'])
  paused=next(x['received']['return']for x in capture['qmp']if x.get('received',{}).get('id')==3 and'return'in x['received']);check('actual-paused-before-save',paused=={'status':'paused','running':False})
  extent=capture['dynamic_extent'];dump=PRODUCER/'artifacts/avf-guest-device-tree/capture-1/apple-tree.adt';check('exact-pmemsave-dynamic-extent',sent[3]['arguments']==dict(val=extent['address'],size=extent['length'],filename=str(dump))and 0x40000000<=extent['address']<extent['address']+extent['length']<=0x50000000)
  check('host-quit-cleanup',any(x.get('received',{}).get('event')=='SHUTDOWN'and x['received']['data']=={'guest':False,'reason':'host-qmp-quit'}for x in capture['qmp']))
  console=(dump.parent/'console.log').read_text();match=re.search(r'device tree (0x[0-9a-f]+)\+(0x[0-9a-f]+) boot_args (0x[0-9a-f]+)',console);check('actual-console-extent',match and tuple(int(match[i],16)for i in[1,2,3])==(extent['address'],extent['length'],extent['boot_args_address'])and'VM005 SYNTHETIC SPIN-CONTROL'in console and extent['address']!=0x48200000)
  check('bounded-historical-capture',capture['elapsed_seconds']<55 and capture['peak_total_owned_rss_bytes']<=512*1024**2 and len(capture['admission'])==3 and all(x['MemAvailable_bytes']>=4*1024**3 for x in capture['admission']))
  samples=[json.loads(s)for s in(dump.parent/'samples.jsonl').read_text().splitlines()];check('continuous-observed-floor',all(s['MemAvailable_bytes']>=4*1024**3 for s in samples))
  data=bind(dump,'afa048b454b658399636030abe71bc706665fb722564459b93e75609f7d6d491',12540).read_bytes();root,nodes=decode(data);check('independent-exact-byte-reconstruction',encode(root)==data)
  spec=importlib.util.spec_from_file_location('frozen_DT_parser',PRODUCER/'tools/build/avf_guest_device_tree.py');dt=importlib.util.module_from_spec(spec);spec.loader.exec_module(dt)
  parsed=dt.parse(data);check('independent-node-and-property-decoding',set(parsed)==set(nodes)and all(parsed[p]['properties']=={v['name']:v['value']for v in n['props']}and parsed[p]['offset']==n['offset']and parsed[p]['value_offsets']=={v['name']:v['value_at']for v in n['props']}and parsed[p]['child_count']==len(n['children'])for p,n in nodes.items()))
  selected=dt.preflight(parsed,require_pci=True);check('exact-actual-selected-preflight',selected==capsule['actual_preflight']and len(nodes)==14 and len(selected['checks'])==38)
  values=lambda path:{p['name']:p['value']for p in nodes[path]['props']}
  chosen=values('/chosen');io=struct.unpack('<QQQ',values('/arm-io')['ranges']);gic=struct.unpack('<QQQQ',values('/arm-io/gic')['reg']);uart=struct.unpack('<QQ',values('/arm-io/uart0')['reg']);pci=struct.unpack('<QQ',values('/pci0')['ecam']);bus=struct.unpack('<II',values('/pci0')['bus-range']);cpu=values('/cpus/cpu0')
  check('actual-console-register-map',(io[1]+gic[0],io[1]+gic[2],gic[3],io[1]+uart[0])==(0x8000000,0x80a0000,0xf60000,0x9000000)and pci==(0x4010000000,0x10000000)and bus==(0,255))
  check('actual-one-CPU-HVC-frequency',int.from_bytes(cpu['reg'],'little')==0 and int.from_bytes(cpu['cpu-id'],'little')==0 and cpu['state']==b'running\0'and chosen['psci-method']==b'hvc\0'and int.from_bytes(cpu['timebase-frequency'],'little')==0x3b9aca0)
  check('actual-no-ramdisk','RAMDisk'not in values('/chosen/memory-map'))
  def negative(name,raw):
   path=out/(name+'.adt');path.write_bytes(raw)
   try:dt.preflight(dt.parse(raw),require_pci=True)
   except dt.TreeError as error:report['controls'].append(dict(name=name,accepted=True,sha256=sha(path),size=len(raw),error=str(error)))
   else:raise AssertionError('invalid actual-byte control accepted: '+name)
  def bytecase(name,offset,value):
   raw=bytearray(data);raw[offset:offset+len(value)]=value;negative(name,bytes(raw))
  def semantic(name,path,key,value):
   tree=copy.deepcopy(root);set_prop(tree,path,key,value);negative(name,encode(tree))
  bytecase('huge-root-property-count',0,struct.pack('<I',0xffffffff));bytecase('huge-root-child-count',4,struct.pack('<I',0xffffffff));negative('trailing-zero',data+b'\0');negative('partial-final-property',data[:-4]);negative('oversize-tree',data+b'\0'*(65537-len(data)))
  first=nodes['/']['props'][0];second=nodes['/']['props'][1];bytecase('unterminated-property-name',first['header'],b'A'*32);bytecase('nonzero-property-name-padding',first['header']+5,b'X');bytecase('duplicate-property-name',second['header'],b'name'.ljust(32,b'\0'));bytecase('embedded-node-terminator',first['value_at']+2,b'\0')
  padded=next(p for n in nodes.values()for p in n['props']if len(p['value'])%4);bytecase('nonzero-property-value-padding',padded['value_at']+len(padded['value']),b'X')
  semantic('wrong-platform','/','platform-name',b't8000\0');semantic('unknown-PSCI','/chosen','psci-method',b'foo\0');semantic('DRAM-overflow','/chosen','dram-base',struct.pack('<Q',0xfffffffffffffff0));semantic('IO-overflow','/arm-io','ranges',struct.pack('<QQQ',0,0xfffffffffffffff0,64));semantic('GIC-overlap','/arm-io/gic','reg',struct.pack('<QQQQ',gic[0],gic[1],gic[0],gic[1]));semantic('GIC-outside-IO','/arm-io/gic','reg',struct.pack('<QQQQ',io[2],gic[1],gic[2],gic[3]));semantic('timer-mismatch','/arm-io/gic','virtual-timer-intid',struct.pack('<I',26))
  semantic('UART-not-console','/arm-io/uart0','boot-console',struct.pack('<I',0));semantic('unknown-UART','/arm-io/uart0','compatible',b'arm,unknown\0');semantic('CPU-zero-frequency','/cpus/cpu0','timebase-frequency',struct.pack('<Q',0));semantic('CPU-nonconsecutive-id','/cpus/cpu0','cpu-id',struct.pack('<I',1));semantic('CPU-none-running','/cpus/cpu0','state',b'waiting\0');semantic('PCI-reversed-buses','/pci0','bus-range',struct.pack('<II',2,1));semantic('PCI-too-small-config','/pci0','ecam',struct.pack('<QQ',pci[0],1<<20));semantic('partial-PCI-range','/pci0','pci-ranges',values('/pci0')['pci-ranges']+b'X');semantic('partial-INTx-record','/pci0','intx-map',values('/pci0')['intx-map']+b'X');semantic('invalid-PCI-probe-only','/pci0','probe-only',struct.pack('<I',2))
  tree=copy.deepcopy(root);parent=find(tree,'/arm-io');parent['children'].append(copy.deepcopy(find(tree,'/arm-io/uart0')));negative('duplicate-node',encode(tree))
  tree=copy.deepcopy(root);set_prop(tree,'/pram','name',b'..\0');negative('path-component-node',encode(tree))
  tree=copy.deepcopy(root);parent=tree
  for i in range(17):
   node=dict(path='',props=[dict(name='name',value=('review-depth'+str(i)).encode()+b'\0')],children=[]);parent['children'].append(node);parent=node
  negative('excessive-depth',encode(tree))
  tree=copy.deepcopy(root);tree['props'].append(dict(name='review-unknown',value=b'\xff\0'));unknown=dt.parse(encode(tree));check('well-formed-unknown-property-preserved',unknown['/']['properties']['review-unknown']==b'\xff\0'and dt.preflight(unknown,require_pci=True)==selected)
  report.update(outcome='pass',summary='Independent actual12540-byte Apple-tree decode, selected launch/source/QMP bindings and malformed-byte controls passed; no XNU/PID1 inference',node_count=len(nodes),property_count=sum(len(n['props'])for n in nodes.values()),negative_controls=len(report['controls']),selected_property_checks=38,launch=dict(io_base=io[1],io_size=io[2],GICD=io[1]+gic[0],GICR=io[1]+gic[2],UART=io[1]+uart[0],PCI_base=pci[0],PCI_size=pci[1],bus_range=bus),compiler_executed=False,guest_executed=False)
 except Exception as error:report['error']=repr(error)
 report['auditor_sha256']=sha(__file__);(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report.get(k)for k in['outcome','error','node_count','property_count','negative_controls','summary']},indent=2));return report['outcome']!='pass'
if __name__=='__main__':raise SystemExit(main())
