#!/usr/bin/env python3
"""Primary NIST cases plus an independent Python-integer/OpenSSL RSA oracle.

Only public verification inputs are serialized. Test private material stays
under ignored artifacts and is never embedded in JSON/header outputs.
"""
import argparse,base64,datetime,hashlib,json,os,re,shutil,subprocess,zipfile
from pathlib import Path
OID={'SHA1':'06052b0e03021a','SHA224':'0609608648016503040204',
     'SHA256':'0609608648016503040201','SHA384':'0609608648016503040202',
     'SHA512':'0609608648016503040203','SHA512/224':'0609608648016503040205',
     'SHA512/256':'0609608648016503040206'}
ALGORITHM={'SHA1':'sha1','SHA224':'sha224','SHA256':'sha256','SHA384':'sha384',
           'SHA512':'sha512','SHA512/224':'sha512_224','SHA512/256':'sha512_256'}
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def integer_bytes(value,size=None):return value.to_bytes(size or max(1,(value.bit_length()+7)//8),'big')
def em(k,oid,digest_bytes,null=True):
    if oid is None:info=digest_bytes
    else:
        identifier=oid+(b'\x05\0' if null else b'')
        algorithm=b'\x30'+bytes([len(identifier)])+identifier
        info=b'\x30'+bytes([len(algorithm)+len(digest_bytes)+2])+algorithm+b'\x04'+bytes([len(digest_bytes)])+digest_bytes
    if k<len(info)+11:raise ValueError('RFC8017 encoded message too short')
    return b'\0\1'+b'\xff'*(k-len(info)-3)+b'\0'+info
def oracle(n,e,sig,oid,hash_bytes):
    n=int.from_bytes(n,'big');e=int.from_bytes(e,'big');s=int.from_bytes(sig,'big')
    k=(n.bit_length()+7)//8
    if len(sig)!=k or s>=n:return False
    actual=integer_bytes(pow(s,e,n),k)
    return actual in [em(k,oid,hash_bytes,True),em(k,oid,hash_bytes,False)]
def parse(text,filename):
    state={};rows=[];excluded=[];ordinal=0
    for line in text.splitlines():
        line=line.strip()
        if line.startswith('[mod = '):state={};continue
        if '=' not in line or line.startswith('#'):continue
        key,value=[s.strip() for s in line.split('=',1)];state[key]=value
        finish=key=='Result' if filename.startswith('SigVer') else key=='S'
        if not finish:continue
        ordinal+=1
        odd=[field for field in ['Msg'] if len(state[field])%2]
        if odd:
            if state.get('Result','P').startswith('P'):raise ValueError('Primary positive has non-octet hex fields')
            excluded.append(dict(source=filename,record=ordinal,expected=False,reason='Odd hex digit count in octet field;no invented nibble/bit hashing semantics',fields=odd));continue
        hash_name={'SHA512224':'SHA512/224','SHA512256':'SHA512/256'}.get(state['SHAAlg'],state['SHAAlg']);message=bytes.fromhex(state['Msg'])
        n_value=int(state['n'],16);sig_value=int(state['S'],16)
        # CAVP's S is an RSA integer (one published positive has511 hex
        # digits). The octet callback needs RFC8017 I2OSP at modulus width.
        sig_bytes=max((n_value.bit_length()+7)//8,(sig_value.bit_length()+7)//8)
        row=dict(source=filename,algorithm=hash_name,n=state['n'],e=state['e'],
                 signature=integer_bytes(sig_value,sig_bytes).hex(),oid=OID[hash_name],hash=hashlib.new(ALGORITHM[hash_name],message).hexdigest(),
                 expected=state.get('Result','P').startswith('P'),message_sha256=hashlib.sha256(message).hexdigest())
        # Public source e may have an odd count of hex digits.
        for field in ['n','e','signature']:
            if len(row[field])%2:row[field]='0'+row[field]
        check=oracle(*[bytes.fromhex(row[f]) for f in ['n','e','signature','oid','hash']])
        if check!=row['expected']:raise ValueError('Independent Python oracle disagrees with primary result '+str(len(rows)))
        rows.append(row)
    return rows,state,excluded
def tlv(data):
    at=0;items=[]
    while at<len(data):
        tag=data[at];length=data[at+1];at+=2
        if length&0x80:
            count=length&127;length=int.from_bytes(data[at:at+count],'big');at+=count
        items.append((tag,data[at:at+length]));at+=length
    if at!=len(data):raise ValueError('Local synthetic key DER bounds')
    return items
def der(tag,data):
    length=bytes([len(data)]) if len(data)<128 else bytes([0x80+len(integer_bytes(len(data)))])+integer_bytes(len(data))
    return bytes([tag])+length+data
def public_der(n,e):
    def number(v):
        b=integer_bytes(v);return der(2,(b'\0' if b[0]&128 else b'')+b)
    rsa=der(0x30,number(n)+number(e))
    return der(0x30,bytes.fromhex('300d06092a864886f70d0101010500')+der(3,b'\0'+rsa))
def header(rows,target):
    data=bytearray();records=[];saved={}
    def store(value):
        b=bytes.fromhex(value) if value is not None else b''
        if b not in saved:saved[b]=len(data);data.extend(b)
        return saved[b],len(b)
    for row in rows:
        values=[]
        for key in ['n','e','signature','oid','hash']:values.extend(store(row[key]))
        values.append(int(row['expected']));records.append(values)
    out='/* Public primary/independent verification inputs;no private keys. */\n'
    out+='struct rsa_vector {unsigned n_off,n_len,e_off,e_len,sig_off,sig_len,oid_off,oid_len,hash_off,hash_len,valid;};\n'
    out+='static const unsigned char vector_bytes[]=\n'
    for at in range(0,len(data),48):out+='"'+''.join('\\x%02x'%b for b in data[at:at+48])+'"\n'
    out+=';\nstatic const struct rsa_vector rsa_vectors[]={\n'+''.join('{'+','.join(map(str,row))+'},\n' for row in records)+'};\n'
    out+='#define RSA_VECTOR_COUNT '+str(len(rows))+'u\n'
    out+='#define RSA_VECTOR_BYTES '+str(len(data))+'u\n'
    target.write_text(out)
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--archive',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    out=args.output;out.mkdir(parents=True,exist_ok=False);commands=[]
    def command(argv,name,timeout=60):
        available=int(re.search(r'^MemAvailable:\s*(\d+)',Path('/proc/meminfo').read_text(),re.M)[1])*1024
        if available<4*1024**3:raise RuntimeError('MemAvailable gate below4GiB')
        r=subprocess.run([str(s) for s in argv],capture_output=True,text=True,timeout=timeout)
        (out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr)
        commands.append(dict(argv=[str(s) for s in argv],exit_code=r.returncode,MemAvailable_bytes=available))
        if r.returncode:raise ValueError(name+' failed: '+r.stderr)
        return r.stdout
    archive=zipfile.ZipFile(args.archive);rows=[];members={};excluded=[]
    names=['SigVer15_186-3.rsp','SigVer15_186-3_TruncatedSHAs.rsp','SigGen15_186-3.rsp','SigGen15_186-3_TruncatedSHAs.rsp']
    for name in names:
        data=archive.read(name);members[name]=dict(sha256=hashlib.sha256(data).hexdigest(),bytes=len(data))
        parsed,_,skipped=parse(data.decode(),name);rows.extend(parsed);excluded.extend(skipped)
    primary_count=len(rows)
    # Published private test exponent is consumed transiently for malformed EM
    # controls. It is not copied into maintained fixtures.
    text=archive.read('SigGen15_186-3.txt').decode();state={}
    for line in text.splitlines():
        if '=' in line and not line.startswith('#'):
            k,v=[s.strip() for s in line.split('=',1)];state[k]=v
        if 'd' in state and 'n' in state and 'e' in state:break
    n,e,d=(int(state[k],16) for k in ['n','e','d']);k=(n.bit_length()+7)//8
    hashed=hashlib.sha256(b'RSA owned public boundary malformed-encoding controls').digest();oid=bytes.fromhex(OID['SHA256'])
    proper=em(k,oid,hashed)
    variants=[('valid-null-parameters',proper,oid,True),('valid-absent-parameters',em(k,oid,hashed,False),oid,True),
      ('valid-raw36',em(k,None,bytes(range(36))),None,True)]
    for name,index,value in [('wrong-type',1,2),('non-FF-padding',8,0x7e),('wrong-separator',proper.index(b'\0',2),0x01),('trailing-hash-byte',k-1,proper[-1]^1)]:
        changed=bytearray(proper);changed[index]=value;variants.append((name,bytes(changed),oid,False))
    wrong_oid=bytes.fromhex(OID['SHA384']);variants.append(('wrong-OID',em(k,wrong_oid,hashed),oid,False))
    for name,encoded,requested_oid,expected in variants:
        h=bytes(range(36)) if requested_oid is None else hashed
        signature=integer_bytes(pow(int.from_bytes(encoded,'big'),d,n),k)
        row=dict(source='independent-Python-pow/published-NIST-test-exponent',case=name,algorithm='raw' if requested_oid is None else 'SHA256',n=integer_bytes(n).hex(),e=integer_bytes(e).hex(),signature=signature.hex(),oid=requested_oid.hex() if requested_oid else None,hash=h.hex(),expected=expected)
        if oracle(integer_bytes(n),integer_bytes(e),signature,requested_oid,h)!=expected:raise ValueError('Derived oracle case mismatch')
        rows.append(row)
    openssl=Path(shutil.which('openssl')).resolve();version=command([openssl,'version'],'openssl-version')
    private=out/'synthetic-test-key.pem'
    command([openssl,'genpkey','-algorithm','RSA','-pkeyopt','rsa_keygen_bits:4096','-out',private],'openssl4096-generate')
    raw=base64.b64decode(''.join(line for line in private.read_text().splitlines() if not line.startswith('---')))
    fields=tlv(tlv(raw)[0][1])
    if fields[1][0]!=2:fields=tlv(tlv(fields[2][1])[0][1])
    values=[int.from_bytes(value,'big') for tag,value in fields if tag==2]
    n,e,d,p1,p2=values[1:6];key_bytes=integer_bytes(n);exponent=integer_bytes(e)
    (out/'digest.bin').write_bytes(hashed)
    command([openssl,'pkeyutl','-sign','-inkey',private,'-in',out/'digest.bin','-pkeyopt','rsa_padding_mode:pkcs1','-pkeyopt','digest:sha256','-out',out/'signature.bin'],'openssl4096-sign')
    (out/'public.der').write_bytes(public_der(n,e))
    command([openssl,'pkeyutl','-verify','-pubin','-keyform','DER','-inkey',out/'public.der','-in',out/'digest.bin','-sigfile',out/'signature.bin','-pkeyopt','rsa_padding_mode:pkcs1','-pkeyopt','digest:sha256'],'openssl4096-verify')
    signature=(out/'signature.bin').read_bytes()
    if not oracle(key_bytes,exponent,signature,oid,hashed):raise ValueError('4096-bit OpenSSL/Python oracle disagreement')
    rows.append(dict(source='independent-OpenSSL4096-and-Python-pow',case='max-modulus',algorithm='SHA256',n=key_bytes.hex(),e=exponent.hex(),signature=signature.hex(),oid=oid.hex(),hash=hashed.hex(),expected=True))
    # e+phi(N) remains below N and induces the same public operation. This
    # exercises a genuine full4096-bit public exponent without generating a
    # different private key or serializing one.
    large_e=e+(p1-1)*(p2-1)
    if large_e>=n or large_e.bit_length()!=4096 or pow(int.from_bytes(signature,'big'),large_e,n)!=int.from_bytes(em(512,oid,hashed),'big'):raise ValueError('Large public exponent fixture premise')
    rows.append({**rows[-1],'case':'max-public-exponent','e':integer_bytes(large_e).hex()})
    evidence=dict(archive=str(args.archive.resolve()),archive_sha256=digest(args.archive),members=members,primary_count=primary_count,total_count=len(rows),excluded=excluded,oracle=dict(path=str(openssl),sha256=digest(openssl),version=version.strip(),independent_math='Python integer pow and exact RFC8017 encoded-message comparison'),commands=commands,rows=rows)
    (out/'vectors.json').write_text(json.dumps(evidence,indent=2)+'\n');header(rows,out/'vectors.h')
    print(json.dumps(dict(primary=primary_count,total=len(rows),archive_sha256=digest(args.archive))))
if __name__=='__main__':
    import sys,traceback
    destination=Path(sys.argv[sys.argv.index('--output')+1]) if '--output' in sys.argv else None
    existed=destination.exists() if destination else True
    try:main()
    except Exception as error:
        if destination and destination.exists() and not existed:
            (destination/'failure.json').write_text(json.dumps(dict(outcome='fail',phase='vector-preparation',argv=sys.argv,exit_code=1,error=repr(error),recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat()),indent=2)+'\n')
        traceback.print_exc();raise SystemExit(1)
