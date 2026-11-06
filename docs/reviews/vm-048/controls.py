#!/usr/bin/env python3
"""Independent REVALLOC-001; borrowed source APIs, no target execution."""
import contextlib, copy, ctypes as C, hashlib, importlib.util, json, os, resource, signal, struct, time
from pathlib import Path
ROOT=Path('/home/egor/dev/pet/s24-ios-exynos'); HERE=Path(__file__).resolve().parent
FC=ROOT/'worktrees/vm-048-20261106'; OUT=HERE/'runtime-002'; OUT.mkdir(exist_ok=False)
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
 (HERE/'evidence.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
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
 inp=json.loads((FC/'fixtures/public/avf-allocator-retention/inputs.json').read_text()); bind(FC/'fixtures/public/avf-allocator-retention/inputs.json')
 cu=load('review_cu',ROOT/inp['cu_core']['path'],inp['cu_core']['sha256'])
 bind(FC/'docs/procedures/avf-allocator-retention/evidence.json','acd3bdfe4015ce83a5096eba5eac74047ae406afd15f8651bf03bc6c0ab11f25')
 bind(FC/'docs/procedures/avf-allocator-retention/runs/controls-006/evidence.json','8b37c569b4960b0f1dd6f88cd490a1e83cb24dc0a77aa43c52521cfd43ced35c')
 for group in ('source_files','provenance'):
  for v in inp[group].values(): bind(ROOT/v['path'],v['sha256'])
 for v in inp['witnesses']: bind(ROOT/v['path'],v['sha256'])
 bind(ROOT/inp['historical_osarray_raw']['path'],inp['historical_osarray_raw']['sha256'])
 with contextlib.ExitStack() as stack:
  source=a.source_contract({k:stack.enter_context(cu.CoherentFile(ROOT/v['path'])) for k,v in inp['source_files'].items()})
 case('exact-eight-source-contract',lambda:expect(source==a.expected_source()))
 class Fixed(C.Structure): _fields_=[('zone',C.c_void_p),('stats',C.c_void_p),('name',C.c_void_p),('next',C.c_void_p),('signature',C.c_void_p),('flags',C.c_uint32),('size',C.c_uint32),('unused',C.c_void_p*2)]
 class Variable(C.Structure): _fields_=[('version',C.c_uint16),('size_header',C.c_uint16),('size_type',C.c_uint32),('stats',C.c_void_p),('name',C.c_void_p),('next',C.c_void_p),('heap',C.c_uint16),('zones',C.c_uint8*22),('signature_header',C.c_void_p),('signature_type',C.c_void_p),('flags',C.c_uint32)]
 case('independent-LP64-layout-arithmetic',lambda:expect(C.sizeof(C.c_void_p)==8 and C.sizeof(Fixed)==64 and C.sizeof(Variable)==80 and {k:getattr(Fixed,k).offset for k in ('name','signature','flags','size')}=={'name':16,'signature':32,'flags':40,'size':44} and {k:getattr(Variable,k).offset for k in ('name','signature_header','signature_type','flags')}=={'name':16,'signature_header':56,'signature_type':64,'flags':72}))
 witnesses=[]; detail={}; detached=[]
 for entry in inp['witnesses']:
  with cu.macho_snapshot(ROOT/entry['path'],image=False) as (s,v):
   if entry['id']=='kalloc':
    boundary=a.boundary_references(s,v,symbol_at=cu.macho_symbol); case('genuine-kalloc-boundary-pairs',lambda:expect(sum(boundary['counts'].values())==16 and boundary['arm64_explicit_addend_pairs']==17)); result['boundary']=boundary
   else:
    w=a.inspect_object(s,v,source,symbol_at=cu.macho_symbol); witnesses.append(w); detached.append(w); detail[entry['id']]=w
    case('genuine-'+entry['id']+'-historical-only',lambda:expect(w['qualification']=='historical-object-byte-witness-only'))
    for kind,sec in a.metadata_sections(s,v).items():
     for row in a.relocations(s,sec):
      sym=cu.macho_symbol(s,v,row['index']); raw=s.read_range(sec['offset']+row['address'],8); add=int.from_bytes(raw,'little',signed=True); target=v['sections'][sym['section']-1]; delta=sym['value']+add-target['address']; string=s.read_range(target['offset']+delta,min(4096,target['size']-delta)).split(b'\0')[0].decode('ascii')
      actual=next(p for p in w['pointers'] if p['kind']==kind and p['address']==row['address'])
      assert actual['target_address']==sym['value']+add and actual['inline_addend']==add
    detail[entry['id']]['independent_raw_relocation_crosscheck']=True
 result['historical']=detail
 case('detached-witness-json-after-close',lambda:expect(bool(json.dumps(detached))))
 # Copies of existing bytes; mutations affect only our owned scratch.
 base=ROOT/next(e['path'] for e in inp['witnesses'] if e['id']=='osdata')
 with cu.macho_snapshot(base,image=False) as (s,v):
  sec=a.metadata_sections(s,v)['fixed']; reloc=next(iter(a.relocations(s,sec))); sym=cu.macho_symbol(s,v,reloc['index']); meta=dict(sec); symbol=dict(sym)
 assert base.stat().st_size<4*1024**2
 with base.open('rb') as stream: raw=stream.read(4*1024**2)
 assert len(raw)<4*1024**2
 def object_trial(name,edit,verify=None):
  p=OUT/(name+'.o'); data=bytearray(raw); edit(data); p.write_bytes(data)
  with cu.macho_snapshot(p,image=False) as (s,v):
   w=a.inspect_object(s,v,source,symbol_at=cu.macho_symbol)
   return verify(w) if verify else w['qualification']
 def put(data,offset,value,fmt='<Q'): struct.pack_into(fmt,data,offset,value)
 case('copied-real-reserved-field',lambda:object_trial('reserved',lambda b:put(b,meta['offset'],1)),True)
 case('copied-real-zero-type-size',lambda:object_trial('zero-size',lambda b:put(b,meta['offset']+44,0,'<I')),True)
 case('copied-real-inline-positive-outside-cstring',lambda:object_trial('positive-overflow',lambda b:put(b,meta['offset']+reloc['address'],2**63-1,'<q')),True)
 case('copied-real-inline-negative-underflow',lambda:object_trial('negative-underflow',lambda b:put(b,meta['offset']+reloc['address'],-2**63,'<q')),True)
 case('copied-real-wrong-relocation-width',lambda:object_trial('wrong-width',lambda b:put(b,meta['relocation_offset']+4,(struct.unpack_from('<I',b,meta['relocation_offset']+4)[0]&~(3<<25))|(2<<25),'<I')),True)
 case('copied-real-bad-original-symbol-ordinal',lambda:object_trial('bad-symbol',lambda b:put(b,meta['relocation_offset']+4,(struct.unpack_from('<I',b,meta['relocation_offset']+4)[0]&0xff000000)|0xffffff,'<I')),True)
 # Direct relocation parser with signed24 payloads and real owned FD bytes.
 def pair(add,following=3):
  p=OUT/'pair'; bits=(10<<28)|(2<<25)|(add&0xffffff); p.write_bytes(struct.pack('<iIiI',0,bits,0,(following<<28)|(2<<25)|(1<<24 if following==3 else 0)))
  with cu.CoherentFile(p) as s: return list(a.relocations(s,dict(relocation_count=2,relocation_offset=0,size=4)))
 case('signed24-negative-ADDEND-payload-not-symbol-index',lambda:expect(pair(-7)[1]['explicit_addend']==-7))
 case('signed24-positive-ADDEND',lambda:expect(pair(0x7fffff,4)[1]['explicit_addend']==0x7fffff))
 case('ADDEND-requires-page-follower',lambda:pair(1,5),True)
 fixture=FC/'docs/procedures/avf-allocator-retention/runs/controls-006/synthetic-linked-layout.macho'; bind(fixture,'85c3941c74720906ba267978842ad0f9556018de849a72b56bbdb63ebd715943')
 contract=dict(source=source,selection=dict(use_lto=False,dead_strip=False,pointer_encoding='unslid-u64',kc_format='static'),witnesses=witnesses,required=[])
 def image_trial(change=None,c=None):
  with cu.macho_snapshot(fixture,image=True) as (s,v):
   if change: change(v)
   return a.validate(s,v,c or contract,symbol_at=cu.macho_symbol)
 img=image_trial(); result['synthetic_empty_required']=img
 case('synthetic-empty-requirements-incomplete-zero-authority',lambda:expect(img['required_retention']=='incomplete-no-required-record-proof' and img['product_qualification']=='not-granted-by-byte-validator'))
 # Select all fingerprints present in fixture; false liveness digests remain proof inputs only.
 with cu.macho_snapshot(fixture,image=True) as (s,v):
  fps={a.sha_value(a.semantic_record(s,v,section,kind,i)) for kind,section in a.metadata_sections(s,v).items() for i in range(0,section['size'],a.LAYOUTS[kind]['stride'])}
 req=copy.deepcopy(contract)
 for w in witnesses:
  for fp,r in w['metadata_records'].items():
   if fp in fps: req['required'].append(dict(object_sha256=[w['object_sha256']],fingerprint=fp,minimum=1,liveness_proof_sha256='0'*64))
 assert req['required']
 positive=image_trial(c=req); result['synthetic_required']=positive
 case('arbitrary-digest-synthetic-minimum-still-zero-authority',lambda:expect(positive['required_retention']=='pass' and positive['product_qualification']=='not-granted-by-byte-validator'))
 for key in ('use_lto','dead_strip'):
  bad=copy.deepcopy(contract);bad['selection'][key]=True;case('different-'+key+'-requires-new-qualification',lambda bad=bad:image_trial(c=bad),True)
 def data_parent(v): return next(x for x in v['segments'] if x['name']=='__DATA_CONST')
 case('final-writable-protection-refused',lambda:image_trial(lambda v:data_parent(v).update(initial=3)),True)
 case('final-nonexact-maximum-protection-refused',lambda:image_trial(lambda v:data_parent(v).update(maximum=5)),True)
 case('final-parent-file-map-refused',lambda:image_trial(lambda v:data_parent(v).update(offset=data_parent(v)['offset']+8)),True)
 case('final-unresolved-metadata-relocation',lambda:image_trial(lambda v:next(x for x in v['sections'] if x['name']=='__kalloc_type').update(relocation_count=1)),True)
 case('final-misaligned-stride',lambda:image_trial(lambda v:next(x for x in v['sections'] if x['name']=='__kalloc_var').update(size=79)),True)
 bad=copy.deepcopy(req);bad['required'][0]['minimum']=999;case('required-count-cannot-exceed-witness',lambda:image_trial(c=bad),True)
 bad=copy.deepcopy(req);bad['required'][0]['object_sha256']=['f'*64];case('required-object-identity-not-substitutable',lambda:image_trial(c=bad),True)
 # Coherent snapshot identity/lifetime: each case owns one fresh path.
 def coherence(name,mutation):
  p=OUT/name;p.write_bytes(b'0123456789abcdef')
  with cu.CoherentFile(p) as s:
   s.digest();mutation(p);return s.read_range(0,1)
 case('coherent-growth-refused',lambda:coherence('growth',lambda p:p.open('ab').write(b'x')),True)
 case('coherent-truncation-refused',lambda:coherence('truncate',lambda p:p.write_bytes(b'1')),True)
 def swap(p): q=p.with_suffix('.new');q.write_bytes(b'0123456789abcdef');os.replace(q,p)
 case('coherent-same-size-path-swap-refused',lambda:coherence('swap',swap),True)
 p=OUT/'closed';p.write_bytes(b'abcd')
 with cu.CoherentFile(p) as s: escaped=s; iterator=s.iter_range(0,4,chunk=1)
 case('closed-borrowed-range-refused',lambda:escaped.read_range(0,1),True)
 case('escaped-range-generator-refused',lambda:next(iterator),True)
 with cu.macho_snapshot(fixture,image=True) as (s,v): index=v['external_symbols']; iterator=index.items();next(iterator)
 case('closed-symbol-index-refused',lambda:index.get('__start'),True)
 case('escaped-symbol-cursor-refused',lambda:next(iterator),True)
 result['outcome']='pass' if all(r['outcome']=='pass' for r in rows) else 'fail'
except BaseException as e:
 result['outcome']='fail'; result['controller_exception']=repr(e)
finally:
 signal.alarm(0);result['after']=sample()
 if not allowed(result['after']): result['outcome']='resource-deferred'
 if status()['VmHWM']>256*1024**2: result['outcome']='resource-deferred'
 save()
print(json.dumps(dict(outcome=result['outcome'],cases=len(rows),failed=[r for r in rows if r['outcome']!='pass'],controller_exception=result.get('controller_exception'),elapsed=result['elapsed'],proc=result['proc'])))
raise SystemExit(0 if result['outcome']=='pass' else 1)
