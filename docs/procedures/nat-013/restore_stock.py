#!/usr/bin/env python3
"""NAT-013: stock-RECOVERY restore for this measured e1s, one session per Download Mode entry.

Based on docs/procedures/nat-012/restore_stock.py (codex-stock-rescue-20261110-r2), which restored
the stock image in its third attempt (restore-003). Changes, from the NAT-012 failures:

- A Download Mode entry gets exactly one Odin session. Before any USB I/O, the tool records
  the USB enumeration (host boot id, bus, device number) in a ledger and refuses an enumeration that
  is already there. A new attempt needs a physical re-entry, so the device is enumerated again.
- An explicit state machine allows commands only in protocol order. After EndSession, only the
  normal reboot is allowed; a second handshake or BeginSession on the same link is refused.
- The tool refuses to start while any other process holds the USB device node open.
- report.json keeps stages separate: PIT validated, upload acknowledged, session end confirmed,
  reboot confirmed. This tool never reports a pass. Only `assess` with a full-partition readback
  from Android can turn the outcome into a pass.

The image, target, PIT and bounds are fixed. There is no argument for another image or partition,
no PIT write, erase, repartition, EFS clear or boot-chain command, and no automatic retry.
Running `restore` writes RECOVERY and needs its own owner decision; NAT-013 only tests it on the host.
"""
import argparse
import datetime
import hashlib
import json
import os
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
IMAGE = ROOT / 'devices/recovery/backups/2026-11-10/recovery.img'
STOCK = '96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67'
PIT_SHA256 = 'a169ae2c9dc0b11066a3738ccc6913fff94c2ed2c458c6aec1c94108c58b891a'
SIZE = 100663296
PART = 1048576
SEQUENCE = 30 * PART
TARGET = (0, 8, 18)                      # binary type, device type (UFS), identifier
BOUNDS = (75152, 24576)                  # start block, block count (4096-byte blocks)
VENDOR, PRODUCT = 0x04e8, 0x685d
TIMEOUT_MS = 120000


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# ---------------------------------------------------------------------------------------------
# PIT: exact hash plus the original (unweakened) odin4 structural rules.

def pit_entries(b):
    if len(b) < 28:
        raise ValueError('PIT shorter than its header')
    magic, count = struct.unpack_from('<II', b)
    if magic != 0x12349876 or not 0 < count <= 512 or len(b) < 28 + 132 * count:
        raise ValueError('invalid PIT extent')
    rows = []
    for i in range(count):
        off = 28 + 132 * i
        fields = struct.unpack_from('<9I', b, off)
        name = b[off + 36:off + 68].split(b'\0')[0]
        file_name = b[off + 68:off + 100].split(b'\0')[0]
        rows.append((i, fields, name, file_name))
    return rows


def printable(s):
    return all(0x20 <= c <= 0x7e and c not in b'/\\' for c in s)


def validate_pit(b, expected_sha256=PIT_SHA256):
    """Return the RECOVERY entry fields or raise. Nothing is skipped or tolerated."""
    if expected_sha256 is not None and hashlib.sha256(b).hexdigest() != expected_sha256:
        raise ValueError('PIT differs from the measured table')
    rows = pit_entries(b)
    seen = set()
    for i, fields, name, file_name in rows:
        if not name or not printable(name):
            raise ValueError(f'PIT entry {i}: empty or invalid partition name')
        if file_name and not printable(file_name):
            raise ValueError(f'PIT entry {i}: invalid file name')
        if fields[2] == 0 or fields[2] in seen:
            raise ValueError(f'PIT entry {i}: zero or duplicate identifier {fields[2]}')
        seen.add(fields[2])
    recovery = [fields for _, fields, name, _ in rows if name == b'RECOVERY']
    if len(recovery) != 1:
        raise ValueError('RECOVERY is missing or ambiguous')
    v = recovery[0]
    if v[:3] != TARGET or v[5:7] != BOUNDS or v[6] * 4096 != SIZE:
        raise ValueError('wrong RECOVERY target or bounds')
    return v


# ---------------------------------------------------------------------------------------------
# Wire packets and the session state machine.

ALLOWED = {
    (0x64, 0): ('handshaken',), (0x64, 5): ('session',), (0x65, 1): ('packet_size',), (0x65, 2): ('pit',),
    (0x65, 3): ('pit',), (0x64, 2): ('pit_done',), (0x66, 0): ('total_set',),
    (0x66, 2): ('file', 'sequence_done'), (0x66, 3): ('sequence',), (0x67, 0): ('upload_done',),
    (0x67, 1): ('ended',),
}


def packet(cmd, sub, words=()):
    if (cmd, sub) not in ALLOWED:
        raise ValueError('forbidden command')
    if (cmd, sub) == (0x66, 3):
        if len(words) != 8 or words[0] != 0 or tuple(words[2:5]) != TARGET or tuple(words[6:]) != (0, 0):
            raise ValueError('forbidden target or flags')
        if not 0 < words[1] <= SEQUENCE or words[5] not in (0, 1):
            raise ValueError('invalid sequence boundary')
    return struct.pack('<' + 'I' * (2 + len(words)), cmd, sub, *words).ljust(1024, b'\0')


class ProtocolError(RuntimeError):
    pass


class Session:
    """One Odin session on one USB enumeration. States move forward only."""

    def __init__(self, dev, report):
        self.dev, self.report, self.state = dev, report, 'new'
        self.trace = report.setdefault('trace', [])

    def _write(self, b):
        n = self.dev.write(1, b, timeout=TIMEOUT_MS)
        if n != len(b):
            raise ProtocolError(f'short write {n}/{len(b)}; no automatic retry')

    def _read(self, n):
        b = bytes(self.dev.read(0x81, n, timeout=TIMEOUT_MS))
        if len(b) != n:
            raise ProtocolError(f'short read {len(b)}/{n}')
        return b

    def handshake(self):
        if self.state != 'new':
            raise ProtocolError('a second handshake on this link is refused')
        self.state = 'handshaking'
        self._write(b'ODIN')
        if self._read(4) != b'LOKE':
            raise ProtocolError('handshake failed')
        self.state = 'handshaken'

    def command(self, cmd, sub, words=(), expected=0, n=8, next_state=None):
        if (cmd, sub) not in ALLOWED or self.state not in ALLOWED[(cmd, sub)]:
            raise ProtocolError(f'command {cmd:#x}/{sub} refused in state {self.state}')
        row = dict(time=now(), cmd=hex(cmd), subcmd=sub, words=list(words))
        self.trace.append(row)
        self._write(packet(cmd, sub, words))
        r = self._read(n)
        if n == 8:
            kind, result = struct.unpack('<II', r)
            row.update(response_kind=hex(kind), result=result)
            if kind != cmd or (expected is not None and result != expected):
                raise ProtocolError(f'command rejected: {row}')
        else:
            row.update(length=len(r), sha256=hashlib.sha256(r).hexdigest())
        if next_state:
            self.state = next_state
        return r

    def data_part(self, chunk, idx):
        if self.state != 'sequence':
            raise ProtocolError(f'data refused in state {self.state}')
        self._write(chunk)
        kind, ack = struct.unpack('<II', self._read(8))
        if (kind, ack) != (0, idx):
            raise ProtocolError(f'data ack mismatch {(kind, ack)} for part {idx}')


STAGES = ('pit_validated', 'upload_acknowledged', 'session_end_confirmed', 'reboot_confirmed')


def outcome(report):
    s = report['stages']
    if not s['pit_validated']:
        return 'aborted-before-write'
    if not s['upload_acknowledged']:
        return 'upload-incomplete'
    if not s['session_end_confirmed']:
        return 'acknowledged-not-flushed'
    if not s['reboot_confirmed']:
        return 'flushed-reboot-unconfirmed'
    return 'awaiting-readback'


def run_session(dev, image, report, save=lambda: None, expected_pit=PIT_SHA256):
    """Drive one complete session. The caller owns the ledger, the device and the report file."""
    if len(image) != SIZE or hashlib.sha256(image).hexdigest() != STOCK:
        raise ValueError('wrong stock bytes')
    report['stages'] = {k: False for k in STAGES}
    report['outcome'] = outcome(report)
    s = Session(dev, report)
    try:
        s.handshake()
        s.command(0x64, 0, (4,), expected=0x38000, next_state='session')
        s.command(0x64, 5, (PART,), next_state='packet_size')
        r = s.command(0x65, 1, expected=None, next_state='pit')
        size = struct.unpack('<II', r)[1]
        if size != 8192:
            raise ProtocolError('unexpected PIT size')
        pit = bytearray()
        for i in range((size + 499) // 500):
            pit.extend(s.command(0x65, 2, (i,), n=min(500, size - len(pit))))
        validate_pit(bytes(pit), expected_pit)
        report['pit_sha256'] = hashlib.sha256(pit).hexdigest()
        s.command(0x65, 3, next_state='pit_done')
        report['stages']['pit_validated'] = True
        save()
        s.command(0x64, 2, (SIZE, 0), next_state='total_set')
        s.command(0x66, 0, next_state='file')
        acked = 0
        for offset in range(0, SIZE, SEQUENCE):
            chunk = image[offset:offset + SEQUENCE]
            s.command(0x66, 2, (len(chunk),), next_state='sequence')
            for idx in range(len(chunk) // PART):
                s.data_part(chunk[idx * PART:(idx + 1) * PART], idx)
            last = int(offset + len(chunk) == SIZE)
            s.command(0x66, 3, (0, len(chunk)) + TARGET + (last, 0, 0),
                      next_state='upload_done' if last else 'sequence_done')
            acked = offset + len(chunk)
            report['acknowledged_bytes'] = acked
            save()
        report['stages']['upload_acknowledged'] = acked == SIZE
        save()
        # The acknowledgements above do not show that S-Boot committed the bytes: NAT-012's second
        # session acknowledged every part and sequence, then never answered EndSession.
        s.command(0x67, 0, next_state='ended')
        report['stages']['session_end_confirmed'] = True
        save()
        s.command(0x67, 1, next_state='rebooted')
        report['stages']['reboot_confirmed'] = True
    except Exception as e:  # recorded, then re-raised: no retry and no second session
        report['error'] = f'{type(e).__name__}: {e}'
        report['state_at_error'] = s.state
        raise
    finally:
        report['outcome'] = outcome(report)
        save()
    return report


# ---------------------------------------------------------------------------------------------
# Host-side guards: enumeration ledger and concurrent users of the device node.

def enumeration_key(bus, address, boot_id_path='/proc/sys/kernel/random/boot_id'):
    boot_id = Path(boot_id_path).read_text().strip()
    return f'{boot_id}:{bus:03d}:{address:03d}'


def claim_enumeration(ledger, key, out):
    """Append the key before any USB I/O. An existing key means this entry already had a session."""
    ledger.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(ledger, os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX)
        size = os.fstat(fd).st_size
        lines = os.pread(fd, size, 0).decode().splitlines() if size else []
        for line in lines:
            if json.loads(line)['key'] == key:
                raise ProtocolError('this Download Mode entry already had a session; '
                                    'a new attempt needs a physical re-entry and a new decision')
        os.write(fd, (json.dumps(dict(key=key, claimed_at=now(), out=str(out))) + '\n').encode())
    finally:
        os.close(fd)


def device_node_users(bus, address, proc='/proc'):
    node = f'/dev/bus/usb/{bus:03d}/{address:03d}'
    users = []
    for pid in os.listdir(proc):
        if not pid.isdigit() or int(pid) == os.getpid():
            continue
        try:
            for fd in os.listdir(f'{proc}/{pid}/fd'):
                if os.readlink(f'{proc}/{pid}/fd/{fd}') == node:
                    users.append(int(pid))
                    break
        except OSError:
            continue
    return users


# ---------------------------------------------------------------------------------------------
# Assessment: combine the restore report with an Android readback (nat-012/check_android.py).

def assess(report, readback):
    if report.get('outcome') != 'awaiting-readback':
        return dict(outcome='fail', reason=f"restore stopped at {report.get('outcome')}; readback alone "
                    'cannot show which bytes are on the partition', stages=report.get('stages'))
    if not readback:
        return dict(outcome='inconclusive', reason='no Android readback yet', stages=report['stages'])
    props = readback.get('properties', {})
    booted = props.get('sys.boot_completed') == '1'
    hash_ok = readback.get('recovery_hash_match') is True
    stages = dict(report['stages'], android_booted=booted, recovery_readback_matches=hash_ok)
    if booted and hash_ok:
        return dict(outcome='pass', stages=stages)
    if booted and readback.get('recovery_hash_match') is False:
        return dict(outcome='fail', reason='RECOVERY readback differs from the stock image', stages=stages)
    return dict(outcome='inconclusive', reason='Android not fully booted or hash not read', stages=stages)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest='action', required=True)
    r = sub.add_parser('restore', help='write stock RECOVERY in one fresh session (needs an owner decision)')
    r.add_argument('--bus', type=int, required=True)
    r.add_argument('--address', type=int, required=True)
    r.add_argument('--out', type=Path, required=True)
    r.add_argument('--ledger', type=Path, default=ROOT / 'artifacts/nat-013/sessions.jsonl')
    a_ = sub.add_parser('assess', help='combine a restore report with an Android readback')
    a_.add_argument('--report', type=Path, required=True)
    a_.add_argument('--readback', type=Path)
    a = p.parse_args(argv)
    if a.action == 'assess':
        rb = json.loads(a.readback.read_text()) if a.readback else None
        result = assess(json.loads(a.report.read_text()), rb)
        print(json.dumps(result, indent=2))
        return 0 if result['outcome'] == 'pass' else 2

    image = IMAGE.read_bytes()
    if len(image) != SIZE or hashlib.sha256(image).hexdigest() != STOCK:
        raise ValueError('wrong stock bytes')
    users = device_node_users(a.bus, a.address)
    if users:
        raise ProtocolError(f'device node is open in other processes {users}; no concurrent flasher')
    a.out.mkdir(parents=True, exist_ok=False)
    key = enumeration_key(a.bus, a.address)
    claim_enumeration(a.ledger, key, a.out)
    report = dict(started_at=now(), enumeration=key, image_sha256=STOCK, target=list(TARGET))

    def save():
        (a.out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')

    import usb.core
    import usb.util
    dev = usb.core.find(idVendor=VENDOR, idProduct=PRODUCT, bus=a.bus, address=a.address)
    if dev is None:
        raise ProtocolError('exact USB device disappeared')
    usb.util.claim_interface(dev, 1)
    try:
        run_session(dev, image, report, save)
    finally:
        report['finished_at'] = now()
        save()
        usb.util.release_interface(dev, 1)
        usb.util.dispose_resources(dev)
        print('Restore outcome:', report['outcome'], '- Android readback and `assess` are required.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
