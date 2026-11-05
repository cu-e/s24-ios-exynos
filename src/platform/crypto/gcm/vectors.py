#!/usr/bin/env python3
"""Bounded representatives of every primary NIST parameter group + independent EVP."""
import ctypes as C,hashlib,json,re,sys,zipfile
from pathlib import Path
LIB=Path('/usr/lib64/libcrypto.so.3').resolve()
PIN='104ea7f8490d18e9a2e3f877a7579c112adcc3a990a878902dd7b611d94f596e'
ZIP='f9fc479e134cde2980b3bb7cddbcb567b2cd96fd753835243ed067699f26a023'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 archive,out=map(Path,sys.argv[1:]);out.mkdir(parents=True,exist_ok=True)
 assert sha(LIB)==PIN and sha(archive)==ZIP
 lib=C.CDLL(str(LIB));vp=C.c_void_p;ip=C.POINTER(C.c_int)
 signatures=[('EVP_CIPHER_CTX_new',[],vp),('EVP_CIPHER_CTX_free',[vp],None),('EVP_CIPHER_CTX_ctrl',[vp,C.c_int,C.c_int,vp],C.c_int),('OpenSSL_version',[C.c_int],C.c_char_p)]
 for bits in [128,192,256]:signatures.append((f'EVP_aes_{bits}_gcm',[],vp))
 for op in ['Encrypt','Decrypt']:
  signatures += [(f'EVP_{op}Init_ex',[vp,vp,vp,vp,vp],C.c_int),(f'EVP_{op}Update',[vp,vp,ip,vp,C.c_int],C.c_int),(f'EVP_{op}Final_ex',[vp,vp,ip],C.c_int)]
 for name,args,ret in signatures:f=getattr(lib,name);f.argtypes=args;f.restype=ret
 def oracle(k,iv,aad,data,tag=None):
  ctx=lib.EVP_CIPHER_CTX_new();assert ctx
  enc=tag is None;op='Encrypt' if enc else 'Decrypt';init=getattr(lib,'EVP_'+op+'Init_ex');update=getattr(lib,'EVP_'+op+'Update');final=getattr(lib,'EVP_'+op+'Final_ex')
  buf=C.create_string_buffer(len(data)+16);n=C.c_int();tail=C.c_int();tb=C.create_string_buffer(16)
  try:
   assert init(ctx,getattr(lib,f'EVP_aes_{8*len(k)}_gcm')(),None,None,None)==1
   assert lib.EVP_CIPHER_CTX_ctrl(ctx,9,len(iv),None)==1
   assert init(ctx,None,None,k,iv)==1
   assert update(ctx,None,C.byref(n),aad,len(aad))==1
   assert update(ctx,buf,C.byref(n),data,len(data))==1 and n.value==len(data)
   if not enc:
    tb.raw=tag+b'\0'*(16-len(tag));assert lib.EVP_CIPHER_CTX_ctrl(ctx,17,len(tag),tb)==1
   ok=final(ctx,C.byref(buf,n.value),C.byref(tail))
   assert tail.value==0
   if enc:assert ok==1 and lib.EVP_CIPHER_CTX_ctrl(ctx,16,16,tb)==1
   return buf.raw[:len(data)],tb.raw if enc else bool(ok)
  finally:lib.EVP_CIPHER_CTX_free(ctx)
 vectors=[];files={};coverage=[]
 with zipfile.ZipFile(archive) as z:
  for name in sorted(z.namelist()):
   raw=z.read(name);files[name]=hashlib.sha256(raw).hexdigest();group={};selected=set();total=0;groups=set();counts={'valid':0,'fail':0}
   for paragraph in re.split(r'\n\s*\n',raw.decode().replace('\r','')):
    for k,v in re.findall(r'^\[(\w+) = (\d+)\]',paragraph,re.M):group[k]=int(v)
    rec=dict(re.findall(r'^(\w+) = ([0-9a-f]*)\s*$',paragraph,re.M))
    if 'Count' not in rec:continue
    total+=1;bad=bool(re.search(r'^FAIL$',paragraph,re.M));g=tuple(sorted(group.items()));groups.add(g);key=(g,bad)
    if key in selected:continue
    selected.add(key);counts['fail' if bad else 'valid']+=1
    k,iv,aad,ct,tag=(bytes.fromhex(rec[f]) for f in ['Key','IV','AAD','CT','Tag'])
    assert len(k)*8==group['Keylen'] and len(iv)*8==group['IVlen'] and len(ct)*8==group['PTlen'] and len(aad)*8==group['AADlen'] and len(tag)*8==group['Taglen']
    pt,valid=oracle(k,iv,aad,ct,tag);assert valid==not_bad(bad),(name,rec['Count'])
    if not bad:assert pt==bytes.fromhex(rec['PT'])
    actual_ct,computed=oracle(k,iv,aad,pt);assert actual_ct==ct and ((computed[:len(tag)]==tag)==(not bad))
    vectors.append(dict(source='NIST',file=name,count=int(rec['Count']),parameters=group.copy(),bad=bad,key=k.hex(),iv=iv.hex(),aad=aad.hex(),pt=pt.hex(),ct=ct.hex(),tag=tag.hex(),computed=computed[:len(tag)].hex()))
   coverage.append(dict(file=name,total_records=total,parameter_groups=len(groups),selected=counts,selection='first valid and first FAIL per exact parameter group, if present'))
 nist=len(vectors)
 for kb in [16,24,32]:
  for i,n in enumerate([0,1,2,7,15,16,17,31,32,33,63,64,65,127,256]):
   ivn=[1,8,12,16,31,128][i%6];an=[0,1,15,16,17,31,32,33][i%8];tl=[4,5,7,8,12,13,14,15,16][i%9]
   s=hashlib.shake_256(f's24-gcm-v1/{kb}/{n}'.encode()).digest(kb+ivn+an+n);k=s[:kb];iv=s[kb:kb+ivn];a=s[kb+ivn:kb+ivn+an];pt=s[kb+ivn+an:];ct,t=oracle(k,iv,a,pt)
   vectors.append(dict(source='OpenSSL-EVP',bad=False,key=k.hex(),iv=iv.hex(),aad=a.hex(),pt=pt.hex(),ct=ct.hex(),tag=t[:tl].hex(),computed=t[:tl].hex()))
 data=dict(archive_sha256=sha(archive),primary_url='https://csrc.nist.gov/CSRC/media/Projects/Cryptographic-Algorithm-Validation-Program/documents/mac/gcmtestvectors.zip',files=files,coverage=coverage,nist_count=nist,oracle_extra_count=len(vectors)-nist,oracle=dict(path=str(LIB),sha256=sha(LIB),version=lib.OpenSSL_version(0).decode(),interface='EVP AES-GCM, IVLEN=9, GET_TAG=16, SET_TAG=17; provisional decryption output is not authenticated on FAIL'),vectors=vectors)
 (out/'vectors.json').write_text(json.dumps(data,indent=2)+'\n')
 blob=bytearray();rows=[]
 for v in vectors:
  offsets=[]
  for f in ['key','iv','aad','pt','ct','tag','computed']:offsets.append(len(blob));blob.extend(bytes.fromhex(v[f]))
  sizes=[len(v[f])//2 for f in ['key','iv','aad','pt','tag']]
  rows.append('{'+','.join(map(str,[*sizes,int(v['bad']),*offsets]))+'},')
 (out/'vectors.bin').write_bytes(blob)
 (out/'vectors.h').write_text('/* Generated primary/oracle representatives; binary payload avoids huge initializer compilation. */\n#define VECTOR_COUNT '+str(len(vectors))+'\n#define VECTOR_MAX '+str(max(len(v['pt'])//2 for v in vectors))+'\n#define AAD_MAX_VECTOR '+str(max(len(v['aad'])//2 for v in vectors))+'\nstruct vector { unsigned kb,ivn,an,n,tn,bad,key,iv,aad,pt,ct,tag,computed; };\nstatic const struct vector vectors[]={\n'+'\n'.join(rows)+'\n};\nextern const unsigned char s24_gcm_vector_bytes[];\n')
 # The path is controlled by caller and cannot contain assembler escapes.
 assert not any(c in str(out.resolve()) for c in ['"','\\','\n'])
 (out/'vectors.S').write_text('#ifdef __APPLE__\n.section __TEXT,__const\n.globl _s24_gcm_vector_bytes\n_s24_gcm_vector_bytes:\n#else\n.section .rodata\n.globl s24_gcm_vector_bytes\ns24_gcm_vector_bytes:\n#endif\n.incbin "'+str((out/'vectors.bin').resolve())+'"\n#ifndef __APPLE__\n.section .note.GNU-stack,"",@progbits\n#endif\n')
 print(json.dumps(dict(nist=nist,extra=len(vectors)-nist,blob_bytes=len(blob),coverage=coverage)))
def not_bad(bad):return not bad
if __name__=='__main__':main()
