"""Small independent bounded Mach-O64 nlist/relocation/instruction reader."""
import struct
from pathlib import Path
class Object:
 def __init__(self,path):
  self.data=Path(path).read_bytes();d=self.data;self.sections=[];self.symbols=[]
  assert len(d)>=32 and struct.unpack_from('<I',d)[0]==0xfeedfacf
  at=32;st=None
  for _ in range(struct.unpack_from('<I',d,16)[0]):
   cmd,size=struct.unpack_from('<II',d,at);assert size>=8 and at+size<=len(d)
   if cmd==0x19:
    n=struct.unpack_from('<I',d,at+64)[0];assert 72+80*n<=size
    for i in range(n):
     name,seg,addr,length,offset,align,rel,nrel,flags,_,_,_=struct.unpack_from('<16s16sQQ8I',d,at+72+80*i)
     self.sections.append(dict(name=name.rstrip(b'\0').decode(),segment=seg.rstrip(b'\0').decode(),addr=addr,size=length,offset=offset,flags=flags,rel=rel,nrel=nrel))
   elif cmd==2:st=struct.unpack_from('<4I',d,at+8)
   at+=size
  assert st;off,n,strings,length=st;assert off+16*n<=len(d) and strings+length<=len(d)
  for i in range(n):
   s,kind,section,desc,value=struct.unpack_from('<IBBHQ',d,off+16*i);assert s<length
   end=d.index(0,strings+s,strings+length);self.symbols.append(dict(name=d[strings+s:end].decode(),kind=kind,section=section,desc=desc,value=value))
  self.named={s['name']:s for s in self.symbols if s['name']}
 def strong(self,name):
  s=self.named[name];assert s['kind']==15 and not(s['desc']&0xc0) and s['section']>0;return s
 def read_va(self,va,n,section=None):
  candidates=[s for i,s in enumerate(self.sections,1) if (section is None or i==section) and s['addr']<=va and va+n<=s['addr']+s['size']]
  assert len(candidates)==1,(va,n,section)
  s=candidates[0];assert s['flags']&255 not in [1,12];at=s['offset']+va-s['addr'];assert at+n<=len(self.data);return self.data[at:at+n]
 def read(self,name,fmt,delta=0):
  s=self.named[name];return struct.unpack(fmt,self.read_va(s['value']+delta,struct.calcsize(fmt),s['section']))
 def relocations(self,section):
  s=self.sections[section-1];assert s['rel']+8*s['nrel']<=len(self.data);out=[]
  for i in range(s['nrel']):
   a,w=struct.unpack_from('<II',self.data,s['rel']+8*i);assert not(a&0x80000000)
   row=dict(va=s['addr']+a,index=w&0xffffff,pcrel=(w>>24)&1,length=(w>>25)&3,external=(w>>27)&1,type=w>>28)
   if row['external']:row['name']=self.symbols[row['index']]['name']
   else:
    v=struct.unpack('<Q',self.read_va(row['va'],8,section))[0] if row['length']==3 else None
    names=[x['name'] for x in self.symbols if x['section']==row['index'] and x['value']==v and x['name'].startswith('_')]
    row['name']=names[0] if len(names)==1 else None
   out.append(row)
  return out
 def pointer(self,name,delta):
  s=self.named[name];rows=[r for r in self.relocations(s['section']) if r['va']==s['value']+delta];assert len(rows)==1 and rows[0]['name'];return rows[0]['name']
 def insn(self,va,section=1):return struct.unpack('<I',self.read_va(va,4,section))[0]
 def calls(self,name,next_name,target):
  s=self.named[name];end=self.named[next_name]['value'];return sorted([r['va'] for r in self.relocations(s['section']) if s['value']<=r['va']<end and r['name']==target and r['type']==2 and r['pcrel']==1 and self.insn(r['va'],s['section'])&0xfc000000==0x94000000])
 def direct_calls(self,target):
  return [r for i in range(1,len(self.sections)+1) for r in self.relocations(i) if r['name']==target and r['type']==2]
def signed(n,bits):return n-(1<<bits) if n&(1<<(bits-1)) else n
def branch26(pc,word):
 assert word&0xfc000000 in [0x14000000,0x94000000];return pc+signed(word&0x3ffffff,26)*4
def cbz0(pc,word):
 assert word&0xff00001f==0xb4000000;return pc+signed((word>>5)&0x7ffff,19)*4
