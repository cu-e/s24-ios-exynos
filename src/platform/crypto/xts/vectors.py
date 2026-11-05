#!/usr/bin/env python3
"""Parse untouched primary NIST records; independently cross-check via OpenSSL EVP."""
import ctypes as C
import ctypes.util
import hashlib,json,re,sys,zipfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
URL='https://csrc.nist.gov/CSRC/media/Projects/Cryptographic-Algorithm-Validation-Program/documents/aes/XTSTestVectors.zip'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    archive=Path(sys.argv[1]);out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True)
    libpath=Path('/usr/lib64/libcrypto.so.3').resolve()
    lib=C.CDLL(str(libpath))
    for name,args,result in [('EVP_CIPHER_CTX_new',[],C.c_void_p),('EVP_CIPHER_CTX_free',[C.c_void_p],None),('EVP_aes_128_xts',[],C.c_void_p),('EVP_aes_256_xts',[],C.c_void_p),('EVP_EncryptInit_ex',[C.c_void_p,C.c_void_p,C.c_void_p,C.c_void_p,C.c_void_p],C.c_int),('EVP_EncryptUpdate',[C.c_void_p,C.c_void_p,C.POINTER(C.c_int),C.c_void_p,C.c_int],C.c_int),('EVP_EncryptFinal_ex',[C.c_void_p,C.c_void_p,C.POINTER(C.c_int)],C.c_int),('OpenSSL_version',[C.c_int],C.c_char_p)]:
        f=getattr(lib,name);f.argtypes=args;f.restype=result
    def oracle(k,iv,p):
        ctx=lib.EVP_CIPHER_CTX_new();assert ctx
        buf=C.create_string_buffer(len(p)+16);n=C.c_int();last=C.c_int()
        try:
            assert lib.EVP_EncryptInit_ex(ctx,(lib.EVP_aes_128_xts if len(k)==32 else lib.EVP_aes_256_xts)(),None,k,iv)==1
            # One entire data-unit update, respecting OpenSSL XTS API.
            assert lib.EVP_EncryptUpdate(ctx,buf,C.byref(n),p,len(p))==1
            assert lib.EVP_EncryptFinal_ex(ctx,C.byref(buf,n.value),C.byref(last))==1
            assert n.value+last.value==len(p)
            return buf.raw[:len(p)]
        finally:lib.EVP_CIPHER_CTX_free(ctx)
    vectors=[];excluded=[];files={}
    with zipfile.ZipFile(archive) as z:
        for name in sorted(z.namelist()):
            if not name.endswith('.rsp'):continue
            raw=z.read(name);files[name]=hashlib.sha256(raw).hexdigest()
            if '128 hex str' not in name:
                excluded.append({'file':name,'reason':'sequence-number format excluded; raw128-bit i is used','count':len(re.findall(rb'^COUNT =',raw,re.M))});continue
            direction=None
            for paragraph in re.split(r'\n\s*\n',raw.decode().replace('\r','')):
                if '[ENCRYPT]' in paragraph:direction='encrypt'
                if '[DECRYPT]' in paragraph:direction='decrypt'
                rec=dict(re.findall(r'^(\w+) = (\w+)\s*$',paragraph,re.M))
                if 'COUNT' not in rec:continue
                bits=int(rec['DataUnitLen'])
                if bits%128:
                    excluded.append({'file':name,'direction':direction,'count':rec['COUNT'],'bits':bits,'reason':'partial-bit/block input not exposed by selected callback'});continue
                k,iv,p,c=(bytes.fromhex(rec[f]) for f in ['Key','i','PT','CT'])
                assert len(p)==len(c)==bits//8 and len(iv)==16 and len(k) in [32,64]
                assert oracle(k,iv,p)==c, (name,rec['COUNT'])
                vectors.append({'source':'NIST','file':name,'direction':direction,'count':int(rec['COUNT']),'key':k.hex(),'iv':iv.hex(),'pt':p.hex(),'ct':c.hex()})
    nist_count=len(vectors)
    # Deterministic independent backend vectors, including long units and all split positions.
    for n in [16,32]:
        for blocks in [1,2,3,7,16,31,32,33,127,256]:
            seed=f's24-xts-oracle-v1/{n}/{blocks}'.encode()
            stream=hashlib.shake_256(seed).digest(2*n+16+16*blocks)
            k,iv,p=stream[:2*n],stream[2*n:2*n+16],stream[2*n+16:]
            vectors.append({'source':'OpenSSL-EVP','key':k.hex(),'iv':iv.hex(),'pt':p.hex(),'ct':oracle(k,iv,p).hex()})
    data={'primary_url':URL,'archive_sha256':sha(archive),'files':files,'nist_count':nist_count,'oracle_extra_count':len(vectors)-nist_count,'excluded':excluded,'oracle':{'path':str(libpath),'sha256':sha(libpath),'version':lib.OpenSSL_version(0).decode(),'interface':'EVP AES-XTS, one whole-unit EncryptUpdate'},'vectors':vectors}
    (out/'vectors.json').write_text(json.dumps(data,indent=2)+'\n')
    maximum=max(len(bytes.fromhex(v['pt'])) for v in vectors)
    def arr(h):return '{'+','.join('0x'+h[i:i+2] for i in range(0,len(h),2))+'}'
    header=['/* Generated from pinned primary NIST and independent OpenSSL inputs. */',f'#define VECTOR_MAX {maximum}',f'#define VECTOR_COUNT {len(vectors)}','struct vector { unsigned n,bytes,key,iv,pt,ct; };','static const struct vector vectors[] = {']
    blob=bytearray()
    for v in vectors:
        offsets=[]
        for key in ['key','iv','pt','ct']:
            offsets.append(len(blob));blob.extend(bytes.fromhex(v[key]))
        header.append('{'+','.join(str(x) for x in [len(v['key'])//4,len(v['pt'])//2,*offsets])+'},')
    header.append('};\nstatic const unsigned char vector_bytes[] = '+arr(blob.hex())+';\n')
    (out/'vectors.h').write_text('\n'.join(header))
    print(json.dumps({'nist':nist_count,'oracle_extra':len(vectors)-nist_count,'excluded':len(excluded),'maximum_bytes':maximum,'archive_sha256':sha(archive)}))
if __name__=='__main__':main()
