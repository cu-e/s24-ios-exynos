#!/usr/bin/env python3
"""NAT-013: audit odin4 PIT validation (original vs. modified) against an actual PIT.

Offline only; no USB or phone access. The rules are transcribed from
references/odin4-nat008 at 338fde4569ee3b0743098714199361835f96015b
(src/usb/odin_protocol.cpp parse_pit_bytes; src/firmware/firmware_package.cpp
archive-to-PIT match loop and sanitize_filename) and from the saved working-tree
diff artifacts/recovery-rescue-20261110-01/prior-odin.diff. Output: report.json.
"""
import argparse, hashlib, json, struct, sys
from pathlib import Path

ENTRY, HEADER = 132, 28
RECOVERY_EXPECTED = dict(binary_type=0, device_type=8, identifier=18, block_size_or_offset=75152, block_count=24576)


def field(raw):
    s = raw.split(b'\0')[0].decode('latin-1')
    return s.rstrip(' \t')


def valid_string(s):
    return all(0x20 <= ord(c) <= 0x7e and c not in '/\\' for c in s)


def entries(pit):
    magic, count = struct.unpack_from('<II', pit)
    if magic != 0x12349876 or not 0 < count <= 512 or len(pit) < HEADER + ENTRY * count:
        raise ValueError('not a complete PIT')
    rows = []
    for i in range(count):
        off = HEADER + ENTRY * i
        v = struct.unpack_from('<9I', pit, off)
        rows.append(dict(index=i, binary_type=v[0], device_type=v[1], identifier=v[2], attributes=v[3],
                         update_attributes=v[4], block_size_or_offset=v[5], block_count=v[6],
                         partition=field(pit[off + 36:off + 68]), file=field(pit[off + 68:off + 100])))
    return rows


def parse(rows, modified):
    """Return (accepted entries, first fatal reason or None, per-entry notes)."""
    seen, kept, notes = set(), [], []
    for e in rows:
        reason = None
        if not e['partition']:
            reason = 'empty partition name'
        elif not valid_string(e['partition']):
            reason = 'invalid partition name'
        elif e['file'] and not valid_string(e['file']):
            reason = 'invalid file name'
        if reason:
            if not modified:
                return kept, f"entry {e['index']}: {reason}", notes
            notes.append(dict(index=e['index'], action='skipped', reason=reason))
            continue
        if e['identifier'] == 0:
            if not modified:
                return kept, f"entry {e['index']} ({e['partition']}): identifier 0", notes
            notes.append(dict(index=e['index'], action='accepted', reason='identifier 0'))
        elif e['identifier'] in seen:
            if not modified:
                return kept, f"entry {e['index']} ({e['partition']}): duplicate identifier {e['identifier']}", notes
            notes.append(dict(index=e['index'], action='accepted', reason=f"duplicate identifier {e['identifier']}"))
        else:
            seen.add(e['identifier'])
        kept.append(e)
    return kept, None, notes


def sanitize(name):
    while '.' in name and name[name.rfind('.'):].lower() in ('.lz4', '.ext4', '.img', '.bin'):
        name = name[:name.rfind('.')]
    return name


def match(kept, member):
    """odin4's loop: the first entry in table order that matches wins."""
    base = member.rsplit('/', 1)[-1]
    want, lower = sanitize(base).lower(), member.lower()
    hits = []
    for e in kept:
        f, p = e['file'], e['partition']
        if (f and (sanitize(f).lower() == want or f.lower() == base.lower())) or sanitize(p).lower() == want \
                or (f and f.lower() == lower):
            hits.append(e)
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pit', type=Path, required=True)
    ap.add_argument('--member', default='recovery.img')
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    pit = a.pit.read_bytes()
    rows = entries(pit)
    ids = {}
    for e in rows:
        ids.setdefault(e['identifier'], []).append(e['index'])
    report = dict(pit=str(a.pit), pit_sha256=hashlib.sha256(pit).hexdigest(), entries=len(rows),
                  odin4_base='338fde4569ee3b0743098714199361835f96015b', member=a.member,
                  identifier_zero=[e['index'] for e in rows if e['identifier'] == 0],
                  duplicate_identifiers={str(k): v for k, v in ids.items() if len(v) > 1},
                  empty_or_invalid_names=[e['index'] for e in rows if not e['partition'] or not valid_string(e['partition'])],
                  recovery_rows=[e for e in rows if e['partition'] == 'RECOVERY'])
    for label, modified in (('original', False), ('modified', True)):
        kept, fatal, notes = parse(rows, modified)
        hits = match(kept, a.member) if fatal is None else []
        first = hits[0] if hits else None
        report[label] = dict(parse_result='reject' if fatal else 'accept', fatal=fatal, notes=notes,
                             matches=[dict(index=h['index'], partition=h['partition'], identifier=h['identifier'],
                                           device_type=h['device_type']) for h in hits],
                             selected=None if first is None else first['index'],
                             selected_is_expected_recovery=bool(first) and all(first[k] == v for k, v in RECOVERY_EXPECTED.items())
                             and first['partition'] == 'RECOVERY',
                             selected_identifier_unique=bool(first) and len(ids[first['identifier']]) == 1)
    (a.out / 'report.json').write_text(json.dumps(report, indent=1) + '\n')
    print(json.dumps({k: report[k] for k in ('pit_sha256', 'entries', 'identifier_zero', 'duplicate_identifiers',
                                             'empty_or_invalid_names')}, indent=1))
    for label in ('original', 'modified'):
        r = report[label]
        print(label, r['parse_result'], r['fatal'], 'notes', len(r['notes']), 'matches', r['matches'],
              'expected', r['selected_is_expected_recovery'], 'unique-id', r['selected_identifier_unique'])


if __name__ == '__main__':
    sys.exit(main())
