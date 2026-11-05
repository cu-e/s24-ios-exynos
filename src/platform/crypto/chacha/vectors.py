#!/usr/bin/env python3
"""Parse primary RFC8439 hex records and independently cross-check OpenSSL EVP."""
from pathlib import Path
import ctypes as C,hashlib,json,re,sys
HERE=Path(__file__).resolve().parent
RFC_SHA='25bef70fbf7a07ff45c2fe4cb7c6ce954eac687413d8610603268b4e4415324c'
def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def block(text,start,stop):return text.split(start,1)[1].split(stop,1)[0]
def hex_rows(text):
    out=bytearray()
    for line in text.splitlines():
        match=re.match(r'^\s*\d{3}\s+((?:[0-9a-f]{2}(?: |$))+)',line)
        if match:out.extend(bytes.fromhex(match[1]))
    return bytes(out)
def primary(path):
    if sha(path)!=RFC_SHA:raise ValueError('Primary RFC bytes differ')
    text=Path(path).read_text();first=block(text,'\n2.8.2.  Example and Test Vector for AEAD_CHACHA20_POLY1305','\n3.  Implementation Advice')
    a={'source':'RFC8439-2.8.2','key':hex_rows(block(first,'  Key:','   IV:')),'nonce':hex_rows(block(first,'   32-bit fixed-common part:','   Setup for generating'))+hex_rows(block(first,'   IV:','   32-bit fixed-common part:')),'aad':hex_rows(block(first,'   AAD:','  Key:')),'pt':hex_rows(block(first,'  Plaintext:','   AAD:')),'ct':hex_rows(block(first,'  Ciphertext:','  AEAD Construction'))}
    a['tag']=bytes.fromhex(re.search(r'Tag:\s*([0-9a-f:]{47})',first)[1].replace(':',''))
    last=block(text,'\nA.5.  ChaCha20-Poly1305 AEAD Decryption','\nAppendix B.')
    b={'source':'RFC8439-A.5','key':hex_rows(block(last,'  The ChaCha20 Key','  Ciphertext:')),'nonce':hex_rows(block(last,'  The nonce:','  The AAD:')),'aad':hex_rows(block(last,'  The AAD:','  Received Tag:')),'ct':hex_rows(block(last,'  Ciphertext:','  The nonce:')),'tag':hex_rows(block(last,'  Received Tag:','   First, we calculate')),'pt':hex_rows(last.split('  Plaintext::',1)[1])}
    for v in [a,b]:
        if not(len(v['key'])==32 and len(v['nonce'])==12 and len(v['aad'])==12 and len(v['tag'])==16 and len(v['pt'])==len(v['ct'])):raise ValueError('Primary RFC field extent')
    if len(a['pt'])!=114 or len(b['pt'])!=265:raise ValueError('Primary RFC message extent')
    return [a,b]
def main():
    rfc=Path(sys.argv[1]);out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=False)
    mem=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024
    if mem<4*1024**3:raise ValueError('MemAvailable below4GiB; oracle not executed')
    path=Path('/usr/lib64/libcrypto.so.3').resolve();header=Path('/usr/include/openssl/evp.h');lib=C.CDLL(str(path))
    declarations=[('EVP_CIPHER_CTX_new',[],C.c_void_p),('EVP_CIPHER_CTX_free',[C.c_void_p],None),('EVP_chacha20_poly1305',[],C.c_void_p),('EVP_CIPHER_CTX_ctrl',[C.c_void_p,C.c_int,C.c_int,C.c_void_p],C.c_int),('EVP_EncryptInit_ex',[C.c_void_p,C.c_void_p,C.c_void_p,C.c_void_p,C.c_void_p],C.c_int),('EVP_EncryptUpdate',[C.c_void_p,C.c_void_p,C.POINTER(C.c_int),C.c_void_p,C.c_int],C.c_int),('EVP_EncryptFinal_ex',[C.c_void_p,C.c_void_p,C.POINTER(C.c_int)],C.c_int),('OpenSSL_version',[C.c_int],C.c_char_p)]
    for name,args,result in declarations:f=getattr(lib,name);f.argtypes=args;f.restype=result
    # Genuine installed public control macros, not guessed opaque SDK records.
    h=header.read_text();macros=dict(re.findall(r'^\s*#\s*define\s+(EVP_CTRL_\w+)\s+(\w+)',h,re.M))
    def constant(name):
        value=macros[name]
        return int(value,0) if value.startswith(('0x','0X')) or value.isdigit() else constant(value)
    ivctrl=constant('EVP_CTRL_AEAD_SET_IVLEN');tagctrl=constant('EVP_CTRL_AEAD_GET_TAG')
    def oracle(k,n,a,p):
        ctx=lib.EVP_CIPHER_CTX_new();assert ctx
        output=C.create_string_buffer(len(p)+16);count=C.c_int();last=C.c_int();tag=C.create_string_buffer(16)
        try:
            assert lib.EVP_EncryptInit_ex(ctx,lib.EVP_chacha20_poly1305(),None,None,None)==1
            assert lib.EVP_CIPHER_CTX_ctrl(ctx,ivctrl,12,None)==1
            assert lib.EVP_EncryptInit_ex(ctx,None,None,k,n)==1
            if a:assert lib.EVP_EncryptUpdate(ctx,None,C.byref(count),a,len(a))==1
            count.value=0
            if p:assert lib.EVP_EncryptUpdate(ctx,output,C.byref(count),p,len(p))==1
            assert lib.EVP_EncryptFinal_ex(ctx,C.byref(output,count.value),C.byref(last))==1
            assert count.value+last.value==len(p)
            assert lib.EVP_CIPHER_CTX_ctrl(ctx,tagctrl,16,tag)==1
            return output.raw[:len(p)],tag.raw
        finally:lib.EVP_CIPHER_CTX_free(ctx)
    vectors=primary(rfc)
    for v in vectors:
        if oracle(v['key'],v['nonce'],v['aad'],v['pt'])!=(v['ct'],v['tag']):raise ValueError('Independent oracle disagrees with primary RFC')
    for n in [0,1,2,15,16,17,31,32,63,64,65,127,128,129,255,256,257,1024,4096]:
        for an in [0,15,17]:
            stream=hashlib.shake_256(('s24-chacha-oracle-v1/%d/%d'%(n,an)).encode()).digest(32+12+an+n)
            k,nonce=stream[:32],stream[32:44];aad=stream[44:44+an];pt=stream[44+an:];ct,tag=oracle(k,nonce,aad,pt)
            vectors.append(dict(source='OpenSSL-EVP',key=k,nonce=nonce,aad=aad,pt=pt,ct=ct,tag=tag))
    data=dict(primary_url='https://www.rfc-editor.org/rfc/rfc8439.txt',primary_sha256=sha(rfc),oracle=dict(path=str(path),sha256=sha(path),header=str(header),header_sha256=sha(header),version=lib.OpenSSL_version(0).decode(),interface='EVP_chacha20_poly1305; genuine public header controls',control_values=dict(iv_length=ivctrl,get_tag=tagctrl)),vectors=[{k:v.hex() if isinstance(v,bytes) else v for k,v in row.items()} for row in vectors])
    (out/'vectors.json').write_text(json.dumps(data,indent=2)+'\n')
    blob=bytearray();rows=[]
    for v in vectors:
        offsets=[]
        for field in ['key','nonce','aad','pt','ct','tag']:offsets.append(len(blob));blob.extend(v[field])
        rows.append('{'+','.join(str(n) for n in [len(v['aad']),len(v['pt']),*offsets])+'},')
    header=['/* Generated from untouched primary RFC and independent OpenSSL EVP. */',f'#define VECTOR_COUNT {len(vectors)}','#define VECTOR_MAX 4096','#define AAD_MAX 17','struct vector { unsigned aad_bytes,text_bytes,key,nonce,aad,pt,ct,tag; };','static const struct vector vectors[]={',*rows,'};','static const unsigned char vector_blob[]={'+','.join('0x%02x'%x for x in blob)+'};']
    (out/'vectors.h').write_text('\n'.join(header)+'\n');print(json.dumps(dict(primary_vectors=2,independent_extra=len(vectors)-2,vectors=len(vectors),MemAvailable_before_bytes=mem)))
if __name__=='__main__':main()
