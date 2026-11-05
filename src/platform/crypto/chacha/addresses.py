"""Inspect actual linked A64 address formation, never emulate crypto or call ABI.

Bounded ADR/ADRP+ADD/STR decoding checks callback addresses against independent
llvm-nm symbols. A surviving GOT load is rejected; it is not assumed relaxed.
"""
import re,struct
METHODS=['info','init','reset','setnonce','incnonce','aad','encrypt','finalize','decrypt','verify']
def prove(path,nm_text,image):
    raw=path.read_bytes();symbols={}
    for line in nm_text.splitlines():
        m=re.fullmatch(r'([0-9a-fA-F]{16})\s+([A-Za-z])\s+(\S+)',line.strip())
        if m:symbols[m[3]]=(int(m[1],16),m[2])
    delta=image['entry_pa']-image['entry_va']
    if delta&4095:raise ValueError('Expected page-aligned fixture load bias')
    def offset(va):
        for s in image['segments']:
            at=va-s['vmaddr']
            if 0<=at<=s['filesize']-4:return s['fileoff']+at
        raise ValueError('Instruction not within actual file-backed segment')
    result={}
    for name in ['_s24_chacha20poly1305_fill','_s24_chacha_cpu_prepare']:
        start=symbols[name][0];end=min(v for v,t in symbols.values() if t.lower()=='t' and v>start)
        if end-start>2048:raise ValueError('Unexpected address initializer code extent')
        regs={};stores=[]
        for pc in range(start,end,4):
            at=offset(pc);ins=struct.unpack_from('<I',raw,at)[0];rd=ins&31;rn=(ins>>5)&31
            if ins&0x9f000000 in [0x90000000,0x10000000]: # ADRP / ADR
                imm=((ins>>5)&0x7ffff)*4+((ins>>29)&3)
                if imm&(1<<20):imm-=1<<21
                regs[rd]=(pc&~4095)+(imm<<12) if ins&0x80000000 else pc+imm
            elif ins&0xff000000==0x91000000: # ADD Xd,Xn,#imm12{,LSL#12}
                imm=((ins>>10)&4095)<<(12 if ins&(1<<22) else 0)
                regs[rd]=None if regs.get(rn) is None else regs[rn]+imm
            elif ins&0xffc00000==0xf9400000: # LDR Xt,[Xn,#imm] (GOT not relaxed)
                regs[rd]=None
            elif ins&0xffc00000==0xf9000000: # STR Xt,[Xn,#imm12*8]
                off=((ins>>10)&4095)*8;value=regs.get(rd)
                if value in [symbols['_s24_chacha_'+m][0] for m in METHODS]:
                    stores.append(dict(instruction_va=pc,instruction_file_offset=at,table_offset=off,callback_va=value,callback_pa=value+delta))
        if len(stores)!=10:raise ValueError(name+': not exactly ten proven direct callback stores')
        for i,row in enumerate(stores):
            expected=symbols['_s24_chacha_'+METHODS[i]][0]
            if row['table_offset']!=8*i or row['callback_va']!=expected:raise ValueError(name+': actual callback target/field mismatch')
            row['symbol']='_s24_chacha_'+METHODS[i]
        result[name]=stores
    return dict(load_bias=delta,initializers=result,scope='Linked A64 instruction address/field proof; no crypto emulation, no assumed GOT relaxation')
