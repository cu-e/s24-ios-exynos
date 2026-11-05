#!/usr/bin/env python3
"""Exact primary RFC3962 parsing, direct EVP-CS3 and whole-CBC derived oracle."""
import ctypes as C,hashlib,json,re,sys
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
RFC_SHA='1a6bf9edff650f92e8c5f85a450335c168545169bfdd51977393d15a6932f1f0'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def primary(text):
 text=text.split('Some test vectors for CBC with ciphertext stealing, using an initial',1)[1].split('Normative References',1)[0]
 rows=[];row={};section=None;key=bytearray()
 for line in text.splitlines():
  label=line.strip()
  if label in ['AES 128-bit key:','IV:','Input:','Output:','Next IV:']:
   if label=='IV:' and row:
    if set(row)!={'iv','pt','ct','next_iv'}:raise ValueError('incomplete primary record')
    rows.append(row);row={}
   section={'AES 128-bit key:':'key','IV:':'iv','Input:':'pt','Output:':'ct','Next IV:':'next_iv'}[label]
   if section!='key':row[section]=bytearray()
   continue
  m=re.fullmatch(r'\s*([0-9a-f]{4}):\s*((?:[0-9a-f]{2}(?:\s+|$))+)\s*',line)
  if m:
   if section is None:raise ValueError('unlabeled primary hex')
   target=key if section=='key' else row[section]
   if int(m[1],16)!=len(target):raise ValueError('primary byte offsets reordered')
   target.extend(bytes.fromhex(m[2]))
 if row:rows.append(row)
 if len(key)!=16 or [len(x['pt']) for x in rows]!=[17,31,32,47,48,64]:raise ValueError('primary corpus count/length changed')
 result=[]
 for i,x in enumerate(rows):
  if len(x['iv'])!=16 or len(x['next_iv'])!=16 or len(x['ct'])!=len(x['pt']):raise ValueError('malformed primary record')
  result.append({'source':'RFC3962 AppendixB','record':i,'algorithm':2,'key':key.hex(),**{k:bytes(v).hex() for k,v in x.items()}})
 return result

def primary_nist(text):
 text=text.replace('\f','')
 def field(section,label):
  lines=section.splitlines();start=next(i for i,x in enumerate(lines) if x.strip()==label)+1;data=bytearray();seen=False
  for line in lines[start:]:
   if re.fullmatch(r'\s*[0-9A-F]{8}(?:\s+[0-9A-F]{8})*\s*',line):data.extend(bytes.fromhex(line));seen=True
   elif seen:break
  if not data:raise ValueError('missing published NIST '+label)
  return bytes(data)
 iv=field(text.split('CBC-AES128 (Encryption)',1)[0],'IV is');rows=[]
 for bits in [128,192,256]:
  rest=text.split('CBC-AES'+str(bits)+' (Encryption)',1)[1];enc,dec=rest.split('CBC-AES'+str(bits)+' (Decryption)',1)
  if bits!=256:dec=dec.split('CBC-AES'+str(bits+64)+' (Encryption)',1)[0]
  key,pt,ct=(field(enc,x) for x in ['Key is','Plaintext is','Ciphertext is'])
  if (field(dec,'Key is'),field(dec,'Plaintext is'),field(dec,'Ciphertext is'))!=(key,pt,ct):raise ValueError('published NIST encryption/decryption mismatch')
  if len(iv)!=16 or len(key)!=bits//8 or len(pt)!=64 or len(ct)!=64:raise ValueError('published NIST lengths changed')
  rows.append({'source':'NIST official AES_CBC.pdf published CBC example','algorithm':2,'key':key.hex(),'iv':iv.hex(),'pt':pt.hex(),'ct':ct.hex(),'next_iv':ct[-16:].hex()})
 return rows

def main():
 library,source,nist_source,out=map(Path,sys.argv[1:]);out.mkdir(parents=True,exist_ok=True)
 if digest(source)!=RFC_SHA:raise ValueError('pinned primary RFC changed')
 if digest(nist_source)!='e9393d4b55e0fb327205ce7876913b8413e2c4df25e168671accdb019f6fc65c':raise ValueError('pinned published NIST text changed')
 lib=C.CDLL(str(library.resolve()))
 for name,args,result in [('cts3_oracle_init',[],C.c_int),('cts3_oracle_finish',[],None),('cts3_oracle_version',[],C.c_char_p),('cts3_oracle_encrypt',[C.c_char_p,C.c_int,C.c_void_p,C.c_size_t,C.c_void_p,C.c_size_t,C.c_void_p,C.c_size_t,C.c_void_p,C.c_void_p],C.c_int)]:
  f=getattr(lib,name);f.argtypes=args;f.restype=result
 if lib.cts3_oracle_init()!=1:raise ValueError('independent provider unavailable')
 mapped={Path(line.split(maxsplit=5)[5].strip()).resolve() for line in Path('/proc/self/maps').read_text().splitlines() if len(line.split(maxsplit=5))==6 and '/libcrypto.so.'in line}
 if mapped!={Path('/usr/lib64/libcrypto.so.3').resolve()}:raise ValueError('unexpected actual mapped libcrypto '+str(mapped))
 modules={str(Path(line.split(maxsplit=5)[5].strip()).resolve()) for line in Path('/proc/self/maps').read_text().splitlines() if len(line.split(maxsplit=5))==6 and '/ossl-modules/'in line}
 provider_hashes={p:digest(Path(p))for p in sorted(modules)}
 def encrypt(algorithm,key,iv,data,cs3=False):
  buf=C.create_string_buffer(len(data)+16);next_iv=C.create_string_buffer(len(iv))
  if lib.cts3_oracle_encrypt(algorithm.encode(),cs3,key,len(key),iv,len(iv),data,len(data),buf,next_iv)!=1:raise ValueError('independent oracle failed '+algorithm)
  return buf.raw[:len(data)],next_iv.raw
 def cipher(a,n):return 'AES-'+str(n*8)+'-CBC' if a==2 else {8:'DES-CBC',16:'DES-EDE-CBC',24:'DES-EDE3-CBC'}[n]
 def expected(a,key,iv,pt):
  b=len(iv);d=(len(pt)-1)%b+1
  padded=pt+b'\0'*(b-d)
  full,next_iv=encrypt(cipher(a,len(key)),key,iv,padded)
  derived=full[:-2*b]+full[-b:]+full[-2*b:-b][:d]
  if a==2:
   direct,direct_iv=encrypt(cipher(a,len(key))+'-CTS',key,iv,pt,True)
   if (direct,direct_iv)!=(derived,next_iv):raise ValueError('independent native EVP-CS3 disagrees with whole-CBC permutation')
  return derived,next_iv
 try:
  vectors=primary(source.read_text());prim_count=len(vectors)
  for v in vectors:
   key,iv,pt,ct,niv=(bytes.fromhex(v[k]) for k in ['key','iv','pt','ct','next_iv'])
   if expected(2,key,iv,pt)!=(ct,niv):raise ValueError('primary RFC mismatch')
  # Parser controls alter actual primary representation, not production code.
  text=source.read_text();start=text.index('Some test vectors for CBC with ciphertext stealing, using an initial');bad=text[:start]+text[start:].replace('0010:  20\n','0011:  20\n',1)
  if bad==text:raise ValueError('primary negative did not mutate an actual selected offset')
  try:primary(bad)
  except ValueError:parser_negative=True
  else:raise ValueError('reordered primary offset accepted')
  for a,n,b in [(0,8,8),(1,16,8),(1,24,8),(2,16,16),(2,24,16),(2,32,16)]:
   lengths=list(range(b+1,3*b+1))+[4*b-1,4*b,4*b+1,7*b-1,7*b,7*b+1,16*b+1]
   for profile in [0,1]:
    for size in lengths:
     stream=hashlib.shake_256(f's24-cs3-v1/{a}/{n}/{size}/{profile}'.encode()).digest(n+b+size)
     key=stream[:n];iv=stream[n:n+b] if profile else bytes(b);pt=stream[n+b:]
     ct,niv=expected(a,key,iv,pt)
     vectors.append({'source':'OpenSSL native EVP-CS3' if a==2 else 'OpenSSL whole-CBC normative derived CS3','algorithm':a,'key':key.hex(),'iv':iv.hex(),'pt':pt.hex(),'ct':ct.hex(),'next_iv':niv.hex()})
  nist=primary_nist(nist_source.read_text())
  for v in nist:
   key,iv,pt,ct,niv=(bytes.fromhex(v[k]) for k in ['key','iv','pt','ct','next_iv'])
   if encrypt(cipher(2,len(key)),key,iv,pt)!=(ct,niv):raise ValueError('published NIST CBC mismatch')
   derived=ct[:-32]+ct[-16:]+ct[-32:-16]
   if expected(2,key,iv,pt)!=(derived,niv):raise ValueError('published NIST-derived CS3 mismatch')
   vectors.append(v|{'source':'NIST published CBC plus normative full-block CS3 swap (derived, not published CTS vector)','ct':derived.hex()})
  for v in vectors:
   key,iv,pt=(bytes.fromhex(v[k]) for k in ['key','next_iv','pt'])
   chained,chained_iv=expected(v['algorithm'],key,iv,pt);v['chain_ct']=chained.hex();v['chain_iv']=chained_iv.hex()
  cbc=list(nist)
  for n in [16,24,32]:
   for blocks in [1,2,3,5,8]:
    stream=hashlib.shake_256(f's24-cbc16-fixture/{n}/{blocks}'.encode()).digest(n+16+16*blocks)
    key,iv,pt=stream[:n],stream[n:n+16],stream[n+16:];ct,niv=encrypt(cipher(2,n),key,iv,pt)
    cbc.append({'source':'OpenSSL plain CBC fixture qualification','algorithm':2,'key':key.hex(),'iv':iv.hex(),'pt':pt.hex(),'ct':ct.hex(),'next_iv':niv.hex()})
  data={'primary':{'url':'https://www.rfc-editor.org/rfc/rfc3962.txt','sha256':RFC_SHA,'count':prim_count,'lengths':[len(bytes.fromhex(v['pt'])) for v in vectors[:prim_count]]},'derived_extra_count':len(vectors)-prim_count,'nist_published_cbc_count':len(nist),'nist_derived_cs3_count':len(nist),'nist_text_sha256':digest(nist_source),'parser_negative_reordered_offsets':parser_negative,'oracle':{'library':str(library.resolve()),'sha256':digest(library),'version':lib.cts3_oracle_version().decode(),'libcrypto_path':str(Path('/usr/lib64/libcrypto.so.3').resolve()),'libcrypto_sha256':digest(Path('/usr/lib64/libcrypto.so.3').resolve()),'binary_source_rebuild_verified':False,'actual_mapped_libcrypto':[str(x)for x in mapped],'provider_module_hashes':provider_hashes,'AES':'actual EVP-CBC-CTS/CS3 AND independent whole-CBC permutation, genuine public C headers/opaque contexts','DES_TDES':'whole independent OpenSSL CBC plus normative permutation; not a native OpenSSL DES-CS3 mode or published CTS vector'},'vectors':vectors,'cbc_fixture':cbc}
  (out/'vectors.json').write_text(json.dumps(data,indent=2)+'\n')
  blob=bytearray();header=['/* Actual pinned RFC/independent oracle records; see vectors.json. */',f'#define VECTOR_COUNT {len(vectors)}',f'#define CBC_VECTOR_COUNT {len(cbc)}',f'#define VECTOR_MAX {max(len(v["pt"])//2 for v in vectors)}','struct vector {unsigned algorithm,n,b,bytes,key,iv,pt,ct,next_iv,chain_ct,chain_iv;};']
  for table,name in [(vectors,'vectors'),(cbc,'cbc_vectors')]:
   header+=['static const struct vector '+name+'[] = {']
   for v in table:
    off=[]
    for field in ['key','iv','pt','ct','next_iv','chain_ct','chain_iv']:off.append(len(blob));blob.extend(bytes.fromhex(v.get(field,v['ct'] if field=='chain_ct' else v['next_iv'])))
    header.append('{'+','.join(map(str,[v['algorithm'],len(v['key'])//2,len(v['iv'])//2,len(v['pt'])//2,*off]))+'},')
   header+=['};']
  header+=['static const unsigned char vector_bytes[] = {'+','.join(hex(x) for x in blob)+'};']
  (out/'vectors.h').write_text('\n'.join(header)+'\n')
  print(json.dumps({'primary':prim_count,'total_cs3':len(vectors),'genuine_cbc16_fixture':len(cbc),'oracle_version':data['oracle']['version']}))
 finally:lib.cts3_oracle_finish()
if __name__=='__main__':main()
