#!/usr/bin/env python3
"""Read-only review: recompute every (path, sha256) pair named in evidence files.

Pairs are found as {"path": P, "sha256": H}, {"X": P, "X_sha256": H} siblings
and {P: H} maps whose keys are existing file paths. Object files (*.o) are also
checked for an ARM64 Mach-O MH_OBJECT header. Prints and writes a JSON summary.
"""
import hashlib, json, os, re, struct, sys
from pathlib import Path

ROOT = Path('/home/egor/dev/pet/s24-ios-exynos')
HEX = re.compile(r'^[0-9a-f]{64}$')


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def resolve(p):
    q = Path(p)
    return q if q.is_absolute() else ROOT / q


def pairs(node, out):
    if isinstance(node, dict):
        if isinstance(node.get('path'), str) and isinstance(node.get('sha256'), str) and HEX.match(node['sha256']):
            out.append((node['path'], node['sha256']))
        for k, v in node.items():
            if isinstance(v, str) and isinstance(node.get(k + '_sha256'), str) and HEX.match(node[k + '_sha256']) and '/' in v:
                out.append((v, node[k + '_sha256']))
            if isinstance(v, str) and HEX.match(v) and '/' in k and resolve(k).is_file():
                out.append((k, v))
            pairs(v, out)
    elif isinstance(node, list):
        for v in node:
            pairs(v, out)


def macho_object(p):
    with open(p, 'rb') as f:
        head = f.read(16)
    if len(head) < 16:
        return False
    magic, cpu, _sub, filetype = struct.unpack('<IiiI', head)
    return magic == 0xfeedfacf and cpu == 0x0100000c and filetype == 1


def main():
    out_path, own, evidence = sys.argv[1], str(ROOT / sys.argv[2]), sys.argv[3:]
    inside = lambda p: str(resolve(p)).startswith(own)
    found, seen, queue = [], set(), list(evidence)
    depth = {e: 0 for e in evidence}
    while queue:  # follow referenced JSON evidence up to two levels
        e = queue.pop(0)
        if e in seen:
            continue
        seen.add(e)
        before = len(found)
        try:
            pairs(json.load(open(resolve(e))), found)
        except (ValueError, UnicodeDecodeError):
            continue
        for p, _h in found[before:]:
            if p.endswith('.json') and depth[e] < 2 and inside(p) and resolve(p).is_file() and p not in depth:
                depth[p] = depth[e] + 1
                queue.append(p)
    unique = sorted({(str(resolve(p)), h) for p, h in found if inside(p)})
    missing, mismatched, objects, bad_objects = [], [], 0, []
    for p, h in unique:
        f = resolve(p)
        if not f.is_file():
            missing.append(p); continue
        if sha(f) != h:
            mismatched.append(p)
        if f.suffix in ('.o', '.cpo'):
            objects += 1
            if not macho_object(f):
                bad_objects.append(p)
    result = dict(own=own, evidence={e: sha(resolve(e)) for e in evidence}, json_followed=len(seen), pairs=len(unique), missing=missing, mismatched=mismatched,
                  object_files=objects, non_arm64_macho_objects=bad_objects,
                  ok=not missing and not mismatched and not bad_objects)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(result, indent=1) + '\n')
    print(json.dumps({k: (v if not isinstance(v, list) else (len(v), v[:3])) for k, v in result.items() if k != 'evidence'}))


if __name__ == '__main__':
    main()
