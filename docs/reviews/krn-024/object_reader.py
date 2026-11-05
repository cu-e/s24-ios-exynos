"""Independent small readers for local, trusted ar and thin ARM64 objects."""
import struct

def members(data):
    assert data[:8] == b'!<arch>\n'
    result = []; at = 8
    while at < len(data):
        assert at+60 <= len(data) and data[at+58:at+60] == b'`\n'
        name = data[at:at+16].decode().strip()
        length = int(data[at+48:at+58]); start = at+60; end = start+length
        assert end <= len(data)
        body = data[start:end]
        if name.startswith('#1/'):
            count = int(name[3:]); assert count <= len(body)
            name = body[:count].rstrip(b'\0').decode(); body = body[count:]
        else:
            name = name.rstrip('/')
        if not name.startswith('__.SYMDEF'):
            result.append((name,body))
        at = end+(length&1)
    assert at == len(data)
    return result

class Object:
    def __init__(self,data):
        self.data = data; self.sections = []; self.symbols = []; self.named = {}
        magic,cpu,_,kind,ncmds,size,_,_ = struct.unpack_from('<8I',data)
        assert magic == 0xfeedfacf and cpu == 0x100000c and kind == 1
        assert 32+size <= len(data)
        cursor = 32; table = None
        for _ in range(ncmds):
            command,extent = struct.unpack_from('<II',data,cursor)
            assert extent >= 8 and cursor+extent <= 32+size
            if command == 0x19:
                count = struct.unpack_from('<I',data,cursor+64)[0]
                assert extent >= 72+80*count
                for i in range(count):
                    values = struct.unpack_from('<16s16sQQ8I',data,cursor+72+i*80)
                    self.sections.append(dict(name=values[0].rstrip(b'\0').decode(),address=values[2],
                        size=values[3],offset=values[4],reloc=values[6],nreloc=values[7]))
            elif command == 2:
                assert table is None; table = struct.unpack_from('<4I',data,cursor+8)
            cursor += extent
        assert cursor == 32+size and table
        symoff,count,stroff,strsize = table
        assert symoff+16*count <= len(data) and stroff+strsize <= len(data)
        for i in range(count):
            index,kind,sect,desc,value = struct.unpack_from('<IBBHQ',data,symoff+16*i)
            assert index < strsize
            finish = data.index(b'\0',stroff+index,stroff+strsize)
            name = data[stroff+index:finish].decode()
            row = dict(name=name,kind=kind,section=sect,value=value,description=desc)
            self.symbols.append(row)
            if kind&0xe == 0xe and not kind&0xe0:
                self.named[name] = row

    def exported(self):
        return {r['name'] for r in self.symbols if r['kind']&1 and not r['kind']&0xe0
                and (r['kind']&0xe != 0 or r['value'] != 0)}

    def imported(self):
        return {r['name'] for r in self.symbols if r['kind']&1 and not r['kind']&0xe0
                and r['kind']&0xe == 0 and r['value'] == 0}

    def location(self,name,delta=0,length=0):
        row = self.named[name]; section = self.sections[row['section']-1]
        offset = row['value']-section['address']+delta
        assert 0 <= offset <= section['size'] and length <= section['size']-offset
        position = section['offset']+offset; assert position+length <= len(self.data)
        return section,offset,position

    def values(self,name,count,delta=0,code='Q'):
        fmt = '<'+str(count)+code
        _,_,pos = self.location(name,delta,struct.calcsize(fmt))
        return list(struct.unpack_from(fmt,self.data,pos))

    def string_pointer(self,name,delta):
        section,offset,pos = self.location(name,delta,8); targets = []
        for i in range(section['nreloc']):
            loc,info = struct.unpack_from('<iI',self.data,section['reloc']+8*i)
            if loc == offset: targets.append(info)
        assert len(targets) == 1
        info = targets[0]
        assert info>>28 == 0 and (info>>24)&1 == 0 and (info>>25)&3 == 3
        addend = struct.unpack_from('<Q',self.data,pos)[0]; index = info&0xffffff
        if info&(1<<27):
            target = self.symbols[index]; sect = target['section']; address = target['value']+addend
        else:
            sect = index; address = addend
        assert 1 <= sect <= len(self.sections)
        target = self.sections[sect-1]; off = address-target['address']
        assert 0 <= off < target['size']
        start = target['offset']+off
        end = self.data.index(b'\0',start,target['offset']+target['size'])
        return self.data[start:end].decode()
