#!/usr/bin/env python3
"""KRN-044: one-object rebuild loop for the kernel that runs on the phone.

The running kernel is STR-041's link (kernel.unstripped 4c9536d8...) with NAT-020's
deny_storage entry stubs (kernel.no-storage 7ceda59b...). This tool:

  1. replays one object's compile exactly as STR-027/STR-0xx executed it (argv, cwd and
     environment from that compile evidence), on the original source or on a changed copy
     (`--patch FILE` = a unified diff applied to a copy of the source; the original tree is
     never written);
  2. relinks with STR-041's recorded driver argv in a private copy of the link directory
     (objects + filelist rewritten to the copy, the substituted object replaced), so
     STR-041's worktree is never written;
  3. runs STR-041's independent image checks (verify_image.parse, nm -u, unique __start,
     one LC_UUID) on the result;
  4. applies NAT-020's deny_storage stub table to the result.

Host only. Runs the project's own pinned clang/ld (built from source in earlier tasks);
executes no upstream build script, never opens a phone.
"""
from pathlib import Path
import argparse, hashlib, importlib.util, json, os, shutil, subprocess, sys, time

ROOT = Path(__file__).resolve().parents[3]
STR041 = ROOT/'worktrees/str-041-e1s-native-link-image-20261110/artifacts/e1s-native-link/link-001'
PLAN = STR041/'execution-plan.json'
UNSTRIPPED_SHA = '4c9536d89b6ad61e49e8cc45e82820f00df4343c478d14685009ad504313595f'
NOSTORAGE_SHA = '7ceda59bdbedba4d32b80c319e35ec51fe766cf61daa648f80a0c42bbca3e407'
NOSTORAGE = ROOT/'artifacts/nat-020/build-003/kernel.no-storage'


def sha(b): return hashlib.sha256(b).hexdigest()
def fsha(p): return sha(Path(p).read_bytes())


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); sys.modules[name] = mod; spec.loader.exec_module(mod)
    return mod


def compile_record(object_id):
    """The executed compile (argv/cwd/env) of `object_id` from the compile evidence that produced STR-041's copy."""
    plan = json.loads(PLAN.read_text())
    copy = next(c for c in plan['copies'] if c['id'] == object_id)
    src_obj = Path(copy['source']['path'])
    build = src_obj.parents[2]  # .../build-NNN/objects/<component>/<file>
    ev = json.loads((build/'evidence.json').read_text())
    hits = [c['process'] for c in ev['commands'] if c['role'] == object_id]
    assert len(hits) == 1, f'{object_id}: {len(hits)} compile records in {build}'
    proc = hits[0]
    assert proc['argv'][proc['argv'].index('-o')+1] == str(src_obj), 'compile record output differs from the linked copy source'
    return plan, copy, proc


def run(argv, cwd, env, log):
    t = time.monotonic()
    r = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, timeout=600)
    log.append(dict(argv=argv, cwd=str(cwd), exit_code=r.returncode, seconds=round(time.monotonic()-t, 2),
                    stderr_tail=r.stderr.decode(errors='replace')[-2000:]))
    if r.returncode:
        errs = [l for l in r.stderr.decode(errors="replace").splitlines() if ' error: ' in l]
        raise SystemExit(f'command failed ({r.returncode}): {argv[0]}\n' + '\n'.join(errs[:20]) + '\n' + r.stderr.decode(errors="replace")[-1000:])
    return r


def compile_one(object_id, patch, out, log, flat=False):
    """Compile `object_id` as its compile evidence did, on a patched copy of its source when `patch` is given; -> (plan, copy, src, src_sha, obj, obj_sha)."""
    plan, copy, proc = compile_record(object_id)
    tag = '' if flat else object_id.replace('/', '_')   # the main object keeps KRN-044's flat paths (they reach the debug strings)
    for d in ('src', 'compile'):
        (out/d/tag).mkdir(parents=True, exist_ok=True)
    argv = list(proc['argv'])
    srcs = [i for i, x in enumerate(argv) if Path(x).suffix in ('.c', '.cpp', '.s', '.S') and not x.startswith('-') and argv[i-1] not in ('-o', '-MF', '-MT', '-MQ')]
    assert len(srcs) == 1, f'expected one source argument, found {[argv[i] for i in srcs]}'
    si = srcs[0]; src = Path(argv[si])
    src_sha = fsha(src)
    if patch:
        changed = out/'src'/tag/src.name
        shutil.copyfile(src, changed)
        run(['patch', '--no-backup-if-mismatch', '-s', str(changed), str(Path(patch).resolve())], out, None, log)
        argv[si] = str(changed)
        argv.insert(si, '-iquote' + str(src.parent))
    obj = out/'compile'/tag/Path(argv[argv.index('-o')+1]).name
    argv[argv.index('-o')+1] = str(obj)
    if '-MF' in argv: argv[argv.index('-MF')+1] = str(out/'compile'/tag/(obj.stem+'.d'))
    env = dict(proc['environment']); env.update(HOME=str(out/'home'), TMPDIR=str(out/'tmp'), TMP=str(out/'tmp'), TEMP=str(out/'tmp'))
    run(argv, proc['cwd'], env, log)
    return plan, copy, src, src_sha, obj, fsha(obj)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--object', default='iokit/MiniIOMobileFramebuffer.cpo')
    ap.add_argument('--patch', type=Path, help='unified diff applied to a copy of the object\'s source (patch -p0 style paths are ignored: the diff is applied to the single file)')
    ap.add_argument('--expect-string', action='append', default=[], help='byte string that must appear in the relinked kernel')
    ap.add_argument('--extra', action='append', default=[], metavar='OBJECT=PATCH',
                    help='(NAT-121) a further object compiled from a patched copy of its source and substituted in the same link')
    a = ap.parse_args()
    out = a.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    for d in ('home', 'tmp', 'compile', 'src'): (out/d).mkdir()
    log = []
    assert fsha(STR041/'kernel/kernel.unstripped') == UNSTRIPPED_SHA, 'STR-041 image changed'
    plan, copy, src, src_sha, obj, obj_sha = compile_one(a.object, a.patch, out, log, flat=True)
    subst = {a.object: obj}
    extras = []
    for e in a.extra:
        oid, _, pth = e.partition('=')
        assert oid and pth and oid not in subst, e
        _, ecopy, esrc, esha, eobj, eobj_sha = compile_one(oid, pth, out, log)
        subst[oid] = eobj
        extras.append(dict(object=oid, source=str(esrc), source_sha256=esha, patch=pth, patch_sha256=fsha(pth),
                           compiled_object_sha256=eobj_sha, linked_object_sha256=ecopy['source']['sha256']))

    # 2. relink in a private copy. The linker stores each object's absolute path in the debug map (N_OSO
    # stabs), so only a directory whose path has the same length as STR-041's can reproduce its bytes.
    want = len(str(STR041))
    stem = str(out/'link')
    assert len(stem) <= want, f'--out path too long for a same-length link directory ({len(stem)} > {want})'
    link = Path(stem + 'x'*(want-len(stem))); assert len(str(link)) == want
    (link/'objects').mkdir(parents=True); (link/'kernel').mkdir()
    old_objects = str(STR041/'objects'); new_objects = str(link/'objects')
    filelist = []
    for line in (STR041/'kernel/link.filelist').read_text().splitlines():
        assert line.startswith(old_objects+'/'), line
        rel = line[len(old_objects)+1:]
        dst = link/'objects'/rel; dst.parent.mkdir(parents=True, exist_ok=True)
        # N_OSO stabs also record each object's mtime: keep STR-041's mtimes (the substituted object gets the original's)
        if rel in subst: shutil.copyfile(subst[rel], dst); shutil.copystat(line, dst)
        else: shutil.copy2(line, dst)
        filelist.append(str(dst))
    linked = [l[len(new_objects)+1:] for l in filelist]
    assert all(o in linked for o in subst), 'object not in the link'
    (link/'kernel/link.filelist').write_text(''.join(f+'\n' for f in filelist))
    for name in ('all-alias.exp', 'all-kpi.exp', 'symbolsets.plist', 'symbolsets.xml.plist', 'version.o', 'lastkerneldataconst.o',
                 'lastkernelconstructor.o', 'nonlto.o', 'config'):
        s = STR041/'kernel'/name
        if s.is_dir(): shutil.copytree(s, link/'kernel'/name)
        elif s.exists(): shutil.copy2(s, link/'kernel'/name)
    old_kernel = str(STR041/'kernel'); new_kernel = str(link/'kernel')
    driver = [x.replace(old_kernel+'/', new_kernel+'/') for x in plan['driver']]
    assert driver[driver.index('-o')+1] == new_kernel+'/kernel.unstripped'
    (link/'home').mkdir(); (link/'tmp').mkdir()
    lenv = dict(PATH='/usr/bin:/bin', HOME=str(link/'home'), TMPDIR=str(link/'tmp'), TMP=str(link/'tmp'), TEMP=str(link/'tmp'), LC_ALL='C', LANG='C')
    # STR-041 stored the absolute object paths in the debug map (N_OSO); a different directory changes those bytes only.
    run(driver, new_kernel, lenv, log)
    image = link/'kernel/kernel.unstripped'; data = image.read_bytes()

    # 3. STR-041's independent checks
    vi = load('krn044_verify', ROOT/'fixtures/public/e1s-native-link-image/verify_image.py')
    view = vi.parse(data)
    names = [s['name'] for s in view['segments']]
    assert names == vi.SEGMENTS, names
    segs = {s['name']: s for s in view['segments']}
    assert segs['__TEXT']['vmaddr'] == vi.LINK_ADDRESS and segs['__TEXT']['fileoff'] == 0 and view['dylibs'] == 0
    ex = segs['__TEXT_EXEC']; assert ex['vmaddr'] <= view['entry'] < ex['vmaddr']+ex['vmsize']
    undefined = vi.tool('nm', '-u', str(image)).split(); assert not undefined, undefined[:20]
    start = [l.split() for l in vi.tool('nm', str(image)).splitlines() if l.endswith(' __start')]
    assert len(start) == 1 and int(start[0][0], 16) == view['entry']
    uuids = [l for l in vi.tool('otool', '-l', str(image)).splitlines() if l.strip().startswith('uuid ')]
    assert len(uuids) == 1
    found = {s: data.count(s.encode()) for s in a.expect_string}
    assert all(found.values()), f'expected strings missing: {found}'

    # 4. NAT-020's stubs on the result
    n20 = load('krn044_nat020', ROOT/'docs/procedures/nat-020/build.py')
    n20.KERNEL_SHA = sha(data)  # the stub table and its checks are unchanged; only the base identity differs
    stubbed, stub_report = n20.deny_storage(data)
    (out/'kernel.no-storage').write_bytes(stubbed)

    ref = (STR041/'kernel/kernel.unstripped').read_bytes()
    diff = [i for i in range(min(len(ref), len(data))) if ref[i] != data[i]] if len(ref) == len(data) else None
    # The only legitimate difference: the link directory's path text in the debug-map strings (same length).
    normalized = data.replace(str(link).encode(), str(STR041).encode())
    rest = [i for i in range(len(ref)) if ref[i] != normalized[i]] if len(ref) == len(normalized) else None
    rec = dict(schema='krn044-rebuild-v1', object=a.object, source=str(src), source_sha256=src_sha,
               patch=str(a.patch) if a.patch else None, patch_sha256=fsha(a.patch) if a.patch else None,
               compiled_object_sha256=obj_sha, linked_object_sha256=copy['source']['sha256'],
               object_identical=obj_sha == copy['source']['sha256'],
               kernel_unstripped=str(image), kernel_unstripped_sha256=sha(data), kernel_bytes=len(data),
               reference_unstripped_sha256=UNSTRIPPED_SHA, identical_to_reference=sha(data) == UNSTRIPPED_SHA,
               differing_bytes=len(diff) if diff is not None else 'size differs',
               differing_bytes_after_path_normalization=len(rest) if rest is not None else 'size differs',
               identical_after_path_normalization=sha(normalized) == UNSTRIPPED_SHA,
               link_directory=str(link),
               no_storage_of_normalized_identical_to_nat020=(setattr(n20, 'KERNEL_SHA', UNSTRIPPED_SHA) or sha(n20.deny_storage(normalized)[0]) == NOSTORAGE_SHA) if sha(normalized) == UNSTRIPPED_SHA else None,
               entry=hex(view['entry']), undefined_symbols=0, uuid=uuids[0].split()[-1], expect_strings=found,
               no_storage=str(out/'kernel.no-storage'), no_storage_sha256=sha(stubbed), stub_patches=len(stub_report['patches']),
               stub_changed_bytes=stub_report['changed_bytes'],
               no_storage_identical_to_nat020=sha(stubbed) == NOSTORAGE_SHA, extra_objects=extras, commands=log)
    (out/'rebuild.json').write_text(json.dumps(rec, indent=1)+'\n')
    print(json.dumps({k: rec[k] for k in ('object_identical', 'kernel_unstripped_sha256', 'identical_to_reference', 'differing_bytes',
                                          'identical_after_path_normalization', 'differing_bytes_after_path_normalization', 'no_storage_of_normalized_identical_to_nat020',
                                          'expect_strings', 'stub_patches', 'no_storage_sha256', 'no_storage_identical_to_nat020')}))


if __name__ == '__main__':
    main()
