#!/usr/bin/env python3
"""IOS-010: build apfsck (linux-apfs/apfsprogs, GPL-2.0) from the pinned checkout with the host C compiler.

The checker is an external host tool: it is built from the review files pinned in research/sources.json
(source id "apfsprogs"), without the upstream Makefiles, tests or scripts, into an uncommitted directory.  Nothing
here is linked into the kernel, the image or any project binary.  The compiler flags are the ones of the upstream
Makefiles (-Wall -Wno-address-of-packed-member -fno-strict-aliasing, include dir), plus a generated version.h that
carries the pinned revision (the Makefile writes the same macro from `git describe`).

usage: python3 -I tools/ios/build_apfsck.py OUT_DIR [--install-as PATH] [--report FILE]
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKOUT = ROOT / "references/apfsprogs"
LIB_SRCS = ["aes.c", "checksum.c", "libzbitmap.c", "parameters.c", "sha256.c", "unicode.c",
            "zlib_inflate/inffast.c", "zlib_inflate/inflate.c", "zlib_inflate/inftrees.c", "zlib_inflate/infutil.c"]
CK_SRCS = ["apfsck.c", "btree.c", "compress.c", "crypto.c", "dir.c", "extents.c", "htable.c", "inode.c", "key.c",
           "object.c", "snapshot.c", "spaceman.c", "super.c", "xattr.c"]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", type=Path)
    ap.add_argument("--install-as", type=Path, help="also copy the binary here (the donor check-image.sh looks for "
                    "xnu-deps/build/apfsprogs/apfsck/apfsck)")
    ap.add_argument("--report", type=Path)
    a = ap.parse_args()
    cc = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    if not cc:
        print("no host C compiler", file=sys.stderr)
        return 2
    v = subprocess.run([sys.executable, "-I", str(ROOT / "tools/sources.py"), "verify", "apfsprogs"],
                       capture_output=True, text=True, timeout=170)
    if v.returncode != 0:
        print("apfsprogs checkout does not verify:", (v.stderr or v.stdout).strip(), file=sys.stderr)
        return 1
    rep = json.loads(v.stdout)
    if not rep.get("clean"):
        print("apfsprogs checkout is not clean", file=sys.stderr)
        return 1
    out = a.out.resolve()
    if out.exists():
        shutil.rmtree(out)
    (out / "obj").mkdir(parents=True)
    (out / "version.h").write_text('#define GIT_COMMIT\t"%s"\n' % rep["revision"][-8:])
    cflags = ["-Wall", "-Wno-address-of-packed-member", "-fno-strict-aliasing", "-O2",
              "-I", str(CHECKOUT / "include"), "-I", str(out)]
    log, objs = [], []
    for group, srcs in (("lib", LIB_SRCS), ("apfsck", CK_SRCS)):
        for s in srcs:
            src = CHECKOUT / group / s
            obj = out / "obj" / (group + "_" + s.replace("/", "_")[:-2] + ".o")
            r = subprocess.run([cc, *cflags, "-c", str(src), "-o", str(obj)], capture_output=True, text=True, timeout=300,
                               cwd=str(CHECKOUT / group))
            log.append({"src": "%s/%s" % (group, s), "exit": r.returncode, "stderr_lines": len(r.stderr.splitlines())})
            if r.returncode != 0:
                print("compile failed: %s/%s\n%s" % (group, s, r.stderr[-800:]), file=sys.stderr)
                return 1
            objs.append(obj)
    binary = out / "apfsck"
    r = subprocess.run([cc, *cflags, "-o", str(binary), *[str(o) for o in objs]], capture_output=True, text=True, timeout=300)
    log.append({"link": "apfsck", "exit": r.returncode, "stderr_lines": len(r.stderr.splitlines())})
    if r.returncode != 0:
        print("link failed:", r.stderr[-800:], file=sys.stderr)
        return 1
    if a.install_as:
        a.install_as.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(binary, a.install_as)
    ver = subprocess.run([cc, "--version"], capture_output=True, text=True).stdout.splitlines()[0]
    report = {"source": "apfsprogs", "revision": rep["revision"], "review_files_verified": len(rep["review_file_sha256"]),
              "compiler": ver, "cflags": cflags, "binary_sha256": sha256(binary), "binary_bytes": binary.stat().st_size,
              "compile_steps": len(log), "warnings_total": sum(x.get("stderr_lines", 0) for x in log), "steps": log}
    text = (json.dumps(report, indent=1, sort_keys=True) + "\n").replace(str(ROOT) + "/", "")
    if a.report:
        a.report.write_text(text)
    print(text[:600])
    return 0


if __name__ == "__main__":
    sys.exit(main())
