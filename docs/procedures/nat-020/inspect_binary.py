#!/usr/bin/env python3
"""Independently disassemble the emitted containment stubs and guard (host only).

Uses Capstone, not the compiler that emitted the loader. No device access.
The NAT-006-derived verifier separately compares the whole packed kernel.
"""
from pathlib import Path
import argparse, hashlib, json, struct
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

def digest(b):return hashlib.sha256(b).hexdigest()

def elf_symbols(raw):
    assert raw[:6]==b'\x7fELF\x02\x01'
    shoff=struct.unpack_from('<Q',raw,40)[0]
    shsize,nsh=struct.unpack_from('<HH',raw,58)
    sections=[struct.unpack_from('<IIQQQQIIQQ',raw,shoff+i*shsize) for i in range(nsh)]
    result={}
    for s in sections:
        if s[1]!=2:continue
        st=sections[s[6]];strings=raw[st[4]:st[4]+st[5]]
        for o in range(s[4],s[4]+s[5],s[9]):
            no,info,other,index,value,size=struct.unpack_from('<IBBHQQ',raw,o)
            if not index or index>=len(sections) or not no:continue
            name=strings[no:strings.find(b'\0',no)].decode()
            sec=sections[index]
            result[name]=(value,size,sec[4]+value-sec[3])
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--build',required=True,type=Path)
    p.add_argument('--out',required=True,type=Path);a=p.parse_args()
    assert not a.out.exists()
    cs=Cs(CS_ARCH_ARM64,CS_MODE_ARM)
    manifest=json.loads((a.build/'storage-patches.json').read_text())
    raw=(a.build/'kernel.no-storage').read_bytes()
    assert digest(raw)==manifest['derived_sha256']
    decoded=[]
    for patch in manifest['patches']:
        fo=patch['file_offset'];address=int(patch['va'],16)
        actual=raw[fo:fo+8]
        assert actual.hex()==patch['after']
        instructions=list(cs.disasm(actual,address))
        expected=patch['return_value'] & 0xffffffff
        assert len(instructions)==2 and instructions[0].mnemonic=='mov' and instructions[1].mnemonic=='ret'
        register,value=instructions[0].op_str.split(', ')
        assert register=='w0' and int(value[1:],0)&0xffffffff==expected
        decoded.append(dict(symbol=patch['symbol'],address=hex(address),
            instructions=[i.mnemonic+' '+i.op_str for i in instructions]))
    elf=(a.build/'loader/loader.elf').read_bytes();symbols=elf_symbols(elf)
    guard,size,offset=symbols['recovery_guard']
    instructions=list(cs.disasm(elf[offset:offset+size],guard))
    arm_address=symbols['s5e_wdt_arm'][0]
    calls=[i for i in instructions if i.mnemonic=='bl' and int(i.op_str[1:],16)==arm_address]
    assert len(calls)==1,'guard must arm exactly once'
    preceding=[i for i in instructions if calls[0].address-20<=i.address<calls[0].address]
    assert any(i.mnemonic=='mov' and i.op_str=='w1, #0x53' for i in preceding), 'actual call must request 83 seconds'
    forbidden={symbols[n][0] for n in ['s5e_wdt_pet','s5e_wdt_disarm']}
    assert not any(i.mnemonic=='bl' and int(i.op_str[1:],16) in forbidden for i in instructions)
    entry,_,offset=symbols['el1_entry']
    entry_code=list(cs.disasm(elf[offset:offset+32],entry))
    assert entry_code[0].mnemonic=='mrs' and 'sctlr_el1' in entry_code[0].op_str
    assert [i.mnemonic for i in entry_code[1:3]]==['tbnz','tbnz']
    assert ', #0,' in entry_code[1].op_str and ', #2,' in entry_code[2].op_str
    halt=symbols['halt'][0]
    assert all(int(i.op_str.split(', ')[-1][1:],16)==halt for i in entry_code[1:3])
    result=dict(kind='host-test',outcome='pass',native_execution=False,patched_kernel=digest(raw),
        loader_elf=digest(elf),storage_entry_stubs=decoded,
        guard_disassembly=[dict(address=hex(i.address),instruction=i.mnemonic+' '+i.op_str) for i in instructions],
        actual_guard_arm_seconds=83,guard_pets_or_disarms=False,
        entry_mmu_and_cache_reject_before_stack=True,
        limitations=['No proof of clock calibration, reset survival, or automatic Android return.',
                     'No hardware memory isolation; fault containment is not absolute.'])
    a.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(outcome='pass',storage_stubs=len(decoded),guard_seconds=83)))

if __name__=='__main__':main()
