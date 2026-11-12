"""NAT-074 test helper: a minimal flattened-device-tree writer for synthetic /memory and /reserved-memory cases.

Only what the loader's fdt.c reads: root #address-cells/#size-cells = 2, memory@ nodes with reg, and a reserved-memory node with
`ranges` and children with reg. Output is a valid FDT v17 blob (header, empty memory reservation map, structure, strings)."""
import struct


def _align4(n):
    return (n + 3) & ~3


def fdt(memory, reserved=(), memreserve=()):
    """memory: [(base, size)] one node each; reserved: [(name, base, size)]; memreserve: [(base, size)] header map."""
    strings = bytearray()
    offs = {}

    def sname(n):
        if n not in offs:
            offs[n] = len(strings)
            strings.extend(n.encode() + b"\0")
        return offs[n]

    s = bytearray()

    def begin(name):
        b = name.encode() + b"\0"
        s.extend(struct.pack(">I", 1) + b + b"\0" * (_align4(len(b)) - len(b)))

    def end():
        s.extend(struct.pack(">I", 2))

    def prop(name, data):
        s.extend(struct.pack(">III", 3, len(data), sname(name)) + data + b"\0" * (_align4(len(data)) - len(data)))

    begin("")
    prop("#address-cells", struct.pack(">I", 2))
    prop("#size-cells", struct.pack(">I", 2))
    for i, (b, z) in enumerate(memory):
        begin(f"memory@{b:x}")
        prop("device_type", b"memory\0")
        prop("reg", struct.pack(">QQ", b, z))
        end()
    if reserved:
        begin("reserved-memory")
        prop("#address-cells", struct.pack(">I", 2))
        prop("#size-cells", struct.pack(">I", 2))
        prop("ranges", b"")
        for name, b, z in reserved:
            begin(f"{name}@{b:x}")
            prop("reg", struct.pack(">QQ", b, z))
            end()
        end()
    end()
    s.extend(struct.pack(">I", 9))
    rsv = b"".join(struct.pack(">QQ", b, z) for b, z in memreserve) + struct.pack(">QQ", 0, 0)
    off_rsv = 40
    off_struct = off_rsv + len(rsv)
    off_str = off_struct + len(s)
    total = off_str + len(strings)
    hdr = struct.pack(">10I", 0xD00DFEED, total, off_struct, off_str, off_rsv, 17, 16, 0, len(strings), len(s))
    return bytes(hdr + rsv + s + strings)
