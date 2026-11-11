"""Wire protocol of the NAT-041 usbmon engine (see engine/usbmon.h), as used by the host collector and the host tests.

The constants repeat engine/usbmon.h; test_engine.py parses the header and fails if any value here differs.
"""
import struct

VID = 0x1209
PID = 0x0001
PROTO_VERSION = 1

REQ_GET_INFO = 0x01
REQ_READ_RING = 0x02
REQ_GET_EXC = 0x03
REQ_SET_NONCE = 0x04
REQ_PEEK = 0x05

READ_MAX = 4096
NONCE_LEN = 16
BOOT_ID_LEN = 16

K_TEXT = 1
K_STAGE = 2
K_FAULT = 3
K_BOOT = 4
K_MARK = 5
K_DROP = 6
KIND_NAMES = {K_TEXT: "text", K_STAGE: "stage", K_FAULT: "fault", K_BOOT: "boot", K_MARK: "mark", K_DROP: "drop"}

REC_HDR = 8
REC_MAX = 1024

F_NONCE_SET = 1 << 0
F_FAULT = 1 << 1
F_HOLD = 1 << 2
F_CONNECTED = 1 << 3
F_CONFIGURED = 1 << 4

INFO_FMT = "<4sHHII16s16sIIQQIIIIQiIII"
INFO_SIZE = struct.calcsize(INFO_FMT)
EXC_FMT = "<4sHHII16s5Q31QII"
EXC_SIZE = struct.calcsize(EXC_FMT)
assert INFO_SIZE == 112 and EXC_SIZE == 328


def crc8(data):
    """CRC-8, polynomial 0x07, initial value 0, no reflection, no final xor."""
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def parse_info(raw):
    if len(raw) != INFO_SIZE:
        raise ValueError("GET_INFO reply is %d bytes, expected %d" % (len(raw), INFO_SIZE))
    (magic, version, size, flags, stage, boot_id, nonce, ring_size, next_seq, written, oldest, dropped, setups, stalls,
     faults, ticks, last_err, last_depcmd, events, resets) = struct.unpack(INFO_FMT, raw)
    if magic != b"S24L":
        raise ValueError("GET_INFO magic %r" % magic)
    if version != PROTO_VERSION or size != INFO_SIZE:
        raise ValueError("GET_INFO version %d size %d" % (version, size))
    return {"flags": flags, "stage": stage, "boot_id": boot_id, "nonce": nonce, "ring_size": ring_size,
            "next_seq": next_seq, "written": written, "oldest": oldest, "dropped": dropped, "setups": setups,
            "stalls": stalls, "faults": faults, "ticks": ticks, "last_err": last_err, "last_depcmd": last_depcmd,
            "events": events, "resets": resets}


def parse_exc(raw):
    if len(raw) != EXC_SIZE:
        raise ValueError("GET_EXC reply is %d bytes, expected %d" % (len(raw), EXC_SIZE))
    f = struct.unpack(EXC_FMT, raw)
    magic, version, size, valid, stage, boot_id = f[:6]
    if magic != b"S24X" or version != PROTO_VERSION or size != EXC_SIZE:
        raise ValueError("GET_EXC header %r %d %d" % (magic, version, size))
    esr, elr, far, spsr, sp = f[6:11]
    return {"valid": valid, "stage": stage, "boot_id": boot_id, "esr": esr, "elr": elr, "far": far, "spsr": spsr,
            "sp": sp, "x": list(f[11:42]), "count": f[42]}


def parse_ring_reply(raw):
    """-> (start, end, payload): start and end are the low 32 bits of stream offsets."""
    if len(raw) < 8:
        raise ValueError("READ_RING reply shorter than its header")
    start, end = struct.unpack("<II", raw[:8])
    return start, end, raw[8:]


def split_records(buf):
    """Parse whole records from the start of buf. -> (records, consumed, error)

    records: list of (seq, kind, payload). Stops at the first incomplete record (not an error) or the first record whose
    header checksum fails (error is a string and consumed points at that header).
    """
    out = []
    pos = 0
    while len(buf) - pos >= REC_HDR:
        hdr = buf[pos:pos + REC_HDR]
        if crc8(hdr[:7]) != hdr[7]:
            return out, pos, "header crc mismatch at +%d" % pos
        seq, length, kind = struct.unpack("<IHB", hdr[:7])
        if length > REC_MAX:
            return out, pos, "record length %d at +%d exceeds %d" % (length, pos, REC_MAX)
        if len(buf) - pos - REC_HDR < length:
            break
        out.append((seq, kind, bytes(buf[pos + REC_HDR:pos + REC_HDR + length])))
        pos += REC_HDR + length
    return out, pos, None


def decode_record(seq, kind, payload):
    """A JSON-friendly view of one record."""
    rec = {"seq": seq, "kind": KIND_NAMES.get(kind, "kind%d" % kind)}
    if kind == K_STAGE and len(payload) >= 4:
        rec["stage"] = struct.unpack("<I", payload[:4])[0]
        rec["text"] = payload[4:].decode("utf-8", "replace")
    elif kind == K_FAULT and len(payload) == 28:
        esr, elr, far, stage = struct.unpack("<QQQI", payload)
        rec.update(esr=esr, elr=elr, far=far, stage=stage)
    elif kind == K_DROP and len(payload) >= 4:
        rec["count"] = struct.unpack("<I", payload[:4])[0]
    else:
        rec["text"] = payload.decode("utf-8", "replace")
    return rec
