#!/usr/bin/env python3
"""Independent REVALLOC-001; borrowed source APIs, no target execution."""
import contextlib, copy, ctypes as C, hashlib, importlib.util, json, os, resource, signal, struct, time
from pathlib import Path
ROOT=Path('/home/egor/dev/pet/s24-ios-exynos'); HERE=Path(__file__).resolve().parent
FC=ROOT/'worktrees/vm-048-20261106'; OUT=HERE/'runtime-003'; OUT.mkdir(exist_ok=False)
START=time.monotonic(); rows=[]; bindings={}
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''): h.update(b)
 return h.hexdigest()
def bind(p,expected=None):
 d=sha(p); bindings[str(p)]=d
 if expected: assert d==expected,(str(p),d)
 return d
def sample():
 mem={x.split(':')[0]:int(x.split()[1])*1024 for x in Path('/proc/meminfo').read_text().splitlines()}
 psi={x.split()[0]:{k:float(v) for k,v in (y.split('=') for y in x.split()[1:])} for x in Path('/proc/pressure/memory').read_text().splitlines()}
 return dict(monotonic=time.monotonic(),available=mem['MemAvailable'],psi=psi)
def allowed(s): return s['available']>=4*1024**3 and s['psi']['full']['avg10']<2 and s['psi']['some']['avg10']<10
def status(): return {x.split(':')[0]:int(x.split()[1])*1024 for x in Path('/proc/self/status').read_text().splitlines() if x.startswith(('VmHWM:','VmRSS:'))}
result=dict(schema=1,task='REV-048',experiment='REVALLOC-001',admission=[],cases=rows,bindings=bindings,product_qualification='not-granted; synthetic controls only',raw_rusage_start=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
def save():
 result.update(elapsed=time.monotonic()-START,proc=status(),raw_rusage_end=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
 (HERE/'supplement.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
for i in range(3):
 if i: time.sleep(1)
 result['admission'].append(sample())
if not all(map(allowed,result['admission'])):
 result['outcome']='resource-deferred'; save(); raise SystemExit(3)
signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('120s controller deadline'))); signal.alarm(120)
def load(name,p,expected):
 bind(p,expected); spec=importlib.util.spec_from_file_location(name,p); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
def case(name,fn,reject=False):
 try:
  value=fn()
  if reject: raise AssertionError('unexpected acceptance')
  rows.append(dict(name=name,outcome='pass',observed=value))
 except (ValueError,OSError,RuntimeError) as e:
  rows.append(dict(name=name,outcome='pass' if reject else 'fail',exception=repr(e)))
 except Exception as e: rows.append(dict(name=name,outcome='fail',exception=repr(e)))
def expect(x): assert x; return True
try:
 a=load('review_allocator',FC/'tools/build/avf_guest_allocator_retention.py','d5ef2661c63d28c6d1ea42b5ead365bfcb5ca54cfca2dd08bd657d0f3c98570d')
 cu=load('review_cu',ROOT/'worktrees/vm-022-link-cursor-20261106/tools/build/avf_guest_link_inputs.py','9f80e32305ce84e33ab27bcf37d589465a97c2d03c5eb6830fd3540f204400c5')
 old=json.loads((HERE/'evidence.json').read_text());source=a.expected_source();witnesses=list(old['historical'].values())
 inp=json.loads((FC/'fixtures/public/avf-allocator-retention/inputs.json').read_text())
 base=ROOT/next(e['path'] for e in inp['witnesses'] if e['id']=='osdata')
 with cu.macho_snapshot(base) as(s,v):
  sec=dict(a.metadata_sections(s,v)['fixed']); rows0=list(a.relocations(s,sec)); target=rows0[0]; sym=cu.macho_symbol(s,v,target['index']); symoff=v['symbol_table']['offset']+16*target['index']+8
  selected=[r for r in rows0 if r['index']==target['index']]
 with base.open('rb') as f: raw=f.read(4*1024**2)
 def addend(name,offset,delta):
  b=bytearray(raw);struct.pack_into('<Q',b,symoff,sym['value']-delta)
  for r in selected:struct.pack_into('<q',b,sec['offset']+r['address'],delta+offset)
  p=OUT/name;p.write_bytes(b)
  with cu.macho_snapshot(p) as(s,v):return a.inspect_object(s,v,source,symbol_at=cu.macho_symbol)
 baseline=set(old['historical']['osdata']['metadata_records'])
 for delta in (-1,1):
  case('compensated-signed-inline-'+str(delta),lambda delta=delta:expect(set(addend('compensated'+str(delta),0,delta)['metadata_records'])==baseline))
 changed=addend('substring',1,1)
 case('nonzero-string-substring-offset',lambda:expect({r['record']['signature'] for r in changed['metadata_records'].values()}=={'2'}))
 fixture=FC/'docs/procedures/avf-allocator-retention/runs/controls-006/synthetic-linked-layout.macho'
 contract=dict(source=source,selection=dict(use_lto=False,dead_strip=False,pointer_encoding='unslid-u64',kc_format='static'),witnesses=witnesses,required=[])
 def image(change):
  with cu.macho_snapshot(fixture,image=True) as(s,v):
   change(v);return a.validate(s,v,contract,symbol_at=cu.macho_symbol)
 def boundaries(v,key,delta):
  v['external_symbols']=dict(v['external_symbols'].items());v['external_symbols'][key]=dict(v['external_symbols'][key]);v['external_symbols'][key]['value']+=delta
 case('final-boundary-end-must-equal-section-end',lambda:image(lambda v:boundaries(v,a.BOUNDARIES[1],8)),True)
 def ordinal(v):
  v['external_symbols']=dict(v['external_symbols'].items());name=a.BOUNDARIES[0];v['external_symbols'][name]=dict(v['external_symbols'][name],type=15,section=1)
 case('final-boundary-N-SECT-ordinal',lambda:image(ordinal),True)
 def ambiguous(v):
  s=next(x for x in v['sections'] if x['name']=='__cstring');v['sections'].append(dict(s))
 case('final-ambiguous-cstring-mapping',lambda:image(ambiguous),True)
 case('section-record-upper-bound',lambda:image(lambda v:next(x for x in v['sections'] if x['name']=='__kalloc_type').update(size=64*(a.MAX_RECORDS+1))),True)
 # File-byte mutation of the image pointer and load-command encoding.
 with fixture.open('rb') as f: original=f.read(1024**2)
 with cu.macho_snapshot(fixture,image=True) as(s,v):
  fixed=a.metadata_sections(s,v)['fixed'];cs=next(x for x in v['sections'] if x['name']=='__cstring')
 def binary(name,offset,value,fmt):
  p=OUT/name;b=bytearray(original);struct.pack_into(fmt,b,offset,value);p.write_bytes(b)
  with cu.macho_snapshot(p,image=True) as(s,v):return a.validate(s,v,contract,symbol_at=cu.macho_symbol)
 case('final-pointer-at-cstring-exclusive-end',lambda:binary('stringend',fixed['offset']+16,cs['address']+cs['size'],'<Q'),True)
 case('final-pointer-null',lambda:binary('null',fixed['offset']+16,0,'<Q'),True)
 case('unsupported-chained-fixup-command',lambda:binary('fixup',32,0x80000034,'<I'),True)
 def read_bound():
  with cu.CoherentFile(fixture) as s:return s.read_range(0,1024**2+1)
 case('borrowed-range-one-MiB-bound',read_bound,True)
 result['outcome']='pass' if all(r['outcome']=='pass' for r in rows) else 'fail'
except BaseException as e:result['outcome']='fail';result['controller_exception']=repr(e)
finally:
 signal.alarm(0);result['after']=sample()
 if not allowed(result['after']) or status()['VmHWM']>256*1024**2:result['outcome']='resource-deferred'
 save()
print(json.dumps(dict(outcome=result['outcome'],cases=len(rows),failed=[r for r in rows if r['outcome']!='pass'],controller_exception=result.get('controller_exception'),proc=result['proc'])))
raise SystemExit(0 if result['outcome']=='pass' else 1)
