#!/usr/bin/env python3
"""Replay untouched ordinary NIST TDES records and an independent OpenSSL oracle."""
import ctypes as C,hashlib,importlib.util,json,sys,zipfile
from pathlib import Path
sys.dont_write_bytecode=True
MAIN=Path('/home/egor/dev/pet/s24-ios-exynos')
PINS={'KAT_TDES.zip':'19d8841f84ae3415350b069a4768bd416c05a0533ee43e905ab099adb8ccb374','tdesmmt.zip':'04db93728ebf994330b0ba4555d397f8f03c29fd8547d9d586219fabe00e8c78'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 cache,out=map(Path,sys.argv[1:]);out.mkdir(parents=True,exist_ok=True)
 parser=MAIN/'tools/research/crypto-candidates/verify.py'
 spec=importlib.util.spec_from_file_location('primary_parser',parser);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 libpath=Path('/usr/lib64/libcrypto.so.3').resolve();lib=C.CDLL(str(libpath))
 signatures=[('OSSL_PROVIDER_load',[C.c_void_p,C.c_char_p],C.c_void_p),('OSSL_PROVIDER_unload',[C.c_void_p],C.c_int),('EVP_CIPHER_CTX_new',[],C.c_void_p),('EVP_CIPHER_CTX_free',[C.c_void_p],None),('EVP_EncryptInit_ex',[C.c_void_p,C.c_void_p,C.c_void_p,C.c_void_p,C.c_void_p],C.c_int),('EVP_CIPHER_CTX_set_padding',[C.c_void_p,C.c_int],C.c_int),('EVP_EncryptUpdate',[C.c_void_p,C.c_void_p,C.POINTER(C.c_int),C.c_void_p,C.c_int],C.c_int),('EVP_EncryptFinal_ex',[C.c_void_p,C.c_void_p,C.POINTER(C.c_int)],C.c_int),('OpenSSL_version',[C.c_int],C.c_char_p),('DES_set_odd_parity',[C.c_void_p],None),('DES_is_weak_key',[C.c_void_p],C.c_int)]
 for name in ['des_ecb','des_cbc','des_ede_ecb','des_ede_cbc','des_ede3_ecb','des_ede3_cbc']:signatures.append(('EVP_'+name,[],C.c_void_p))
 for name,args,result in signatures:f=getattr(lib,name);f.argtypes=args;f.restype=result
 providers=[]
 for name in [b'default',b'legacy']:
  p=lib.OSSL_PROVIDER_load(None,name)
  if not p:raise ValueError('Missing independent OpenSSL provider '+name.decode())
  providers.append(p)
 def oracle(k,iv,pt):
  name={8:'des',16:'des_ede',24:'des_ede3'}[len(k)]+('_cbc' if iv else '_ecb')
  ctx=lib.EVP_CIPHER_CTX_new();assert ctx
  out=C.create_string_buffer(len(pt)+16);n=C.c_int();last=C.c_int()
  try:
   assert lib.EVP_EncryptInit_ex(ctx,getattr(lib,'EVP_'+name)(),None,k,iv or None)==1
   assert lib.EVP_CIPHER_CTX_set_padding(ctx,0)==1
   assert lib.EVP_EncryptUpdate(ctx,out,C.byref(n),pt,len(pt))==1
   assert lib.EVP_EncryptFinal_ex(ctx,C.byref(out,n.value),C.byref(last))==1
   assert n.value+last.value==len(pt)
   return out.raw[:len(pt)]
  finally:lib.EVP_CIPHER_CTX_free(ctx)
 vectors=[];files={};excluded=[];primary=0;derived=0
 try:
  for archive,expected in PINS.items():
   path=cache/archive
   assert sha(path)==expected
   with zipfile.ZipFile(path) as z:
    for name in sorted(z.namelist()):
     if not name.lower().endswith('.rsp'):continue
     raw=z.read(name);files[archive+'/'+name]=hashlib.sha256(raw).hexdigest()
     if not Path(name).name.startswith(('TECB','TCBC')):
      excluded.append({'file':archive+'/'+name,'reason':'CFB/OFB mode is outside ECB/CBC callback scope'});continue
     if Path(name).name.startswith('TCBCI'):
      excluded.append({'file':archive+'/'+name,'reason':'interleaved CBCI, not ordinary CBC'});continue
     cases=m.parse_vectors(raw.decode(),name)
     for row in cases:
      k,iv,pt,ct=(bytes.fromhex(row[x]) for x in ['key','IV','plaintext','ciphertext'])
      assert oracle(k,iv,pt)==ct,(name,row['count'])
      v={'source':'NIST','file':archive+'/'+name,'count':row['count'],'direction':row['direction'],'key':k.hex(),'iv':iv.hex(),'pt':pt.hex(),'ct':ct.hex()}
      vectors.append(v);primary+=1
      for nk,label in [(k[:8],'repeated-key DES reduction'),(k[:16],'EDE2 local key form')]:
       if (len(nk)==8 and k[:8]==k[8:16]==k[16:]) or (len(nk)==16 and k[:8]==k[16:]):
        assert oracle(nk,iv,pt)==ct
        vectors.append(v|{'source':'NIST-derived '+label,'key':nk.hex()});derived+=1
  assert primary==1000,primary
  for n in [8,16,24]:
   for cbc in [0,1]:
    for blocks in [1,2,3,7,16,31]:
     stream=hashlib.shake_256(f's24-des-oracle-v1/{n}/{cbc}/{blocks}'.encode()).digest(n+8+blocks*8)
     k,iv,pt=stream[:n],stream[n:n+8] if cbc else b'',stream[n+8:]
     vectors.append({'source':'OpenSSL EVP','key':k.hex(),'iv':iv.hex(),'pt':pt.hex(),'ct':oracle(k,iv,pt).hex()})
  helpers=[]
  weakhex=['0101010101010101','FEFEFEFEFEFEFEFE','E0E0E0E0F1F1F1F1','1F1F1F1F0E0E0E0E','01FE01FE01FE01FE','FE01FE01FE01FE01','1FE01FE00EF10EF1','E01FE01FF10EF10E','01E001E001F101F1','E001E001F101F101','1FFE1FFE0EFE0EFE','FE1FFE1FFE0EFE0E','011F011F010E010E','1F011F010E010E01','E0FEE0FEF1FEF1FE','FEE0FEE0FEF1FEF1']
  keys=[bytes([x])*8 for x in range(256)]+[bytes.fromhex(x) for x in weakhex]
  keys += [bytes(b^1 for b in bytes.fromhex(x)) for x in weakhex]
  keys += [hashlib.shake_256(f's24-des-helper/{i}'.encode()).digest(8) for i in range(64)]
  for key in keys:
   block=C.create_string_buffer(key,8);lib.DES_set_odd_parity(block);parity=block.raw;weak=lib.DES_is_weak_key(block)
   assert weak in [0,1]
   helpers.append({'key':key.hex(),'parity':parity.hex(),'weak':weak})
  data={'primary_count':primary,'derived_count':derived,'oracle_extra_count':len(vectors)-primary-derived,'archive_sha256':PINS,'files':files,'excluded':excluded,'parser':{'path':str(parser),'sha256':sha(parser)},'oracle':{'path':str(libpath),'sha256':sha(libpath),'version':lib.OpenSSL_version(0).decode(),'interface':'EVP ECB/CBC no padding; default and legacy providers; public 8-byte DES helper pointers only','binary_source_rebuild_verified':False},'vectors':vectors,'helpers':helpers}
  (out/'vectors.json').write_text(json.dumps(data,indent=2)+'\n')
  blob=bytearray();header=['/* Generated primary NIST/oracle records, see vectors.json provenance. */',f'#define VECTOR_COUNT {len(vectors)}',f'#define VECTOR_MAX {max(len(v["pt"])//2 for v in vectors)}','struct vector { unsigned n,bytes,cbc,key,iv,pt,ct; };','static const struct vector vectors[] = {']
  for v in vectors:
   off=[]
   for key in ['key','iv','pt','ct']:off.append(len(blob));blob.extend(bytes.fromhex(v[key]))
   header.append('{'+','.join(map(str,[len(v['key'])//2,len(v['pt'])//2,bool(v['iv'])*1,*off]))+'},')
  header+=['};','struct helper { unsigned char key[8],parity[8];int weak; };','static const struct helper helpers[] = {']
  arr=lambda h:'{'+','.join('0x'+h[i:i+2] for i in range(0,len(h),2))+'}'
  for v in helpers:header.append('{'+arr(v['key'])+','+arr(v['parity'])+','+str(v['weak'])+'},')
  header+=['};','static const unsigned char vector_bytes[] = '+arr(blob.hex())+';']
  (out/'vectors.h').write_text('\n'.join(header)+'\n')
  print(json.dumps({k:data[k] for k in ['primary_count','derived_count','oracle_extra_count','oracle']}))
 finally:
  for p in reversed(providers):assert lib.OSSL_PROVIDER_unload(p)==1
if __name__=='__main__':main()
