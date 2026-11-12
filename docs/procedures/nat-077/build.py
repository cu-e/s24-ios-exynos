#!/usr/bin/env python3
"""NAT-077: build the hashing probe (src/hash-probe.c) as a static arm64 Mach-O init for the payload kernel, and the host test program.

  build.py --out DIR [--root-dev /dev/rmd1] [--chunk 131072]

DIR must not exist. It receives:
  hash-probe        the Mach-O (what mkpayload.py takes as --ramdisk, like NAT-065's probe-init)
  hash-probe.json   sizes, SHA-256 values, toolchain versions and the exact commands (no Apple data is involved at all)
  host-probe        the same C source compiled for the host with -DHOST_TEST (reads fd 3, prints on stdout)

Pipeline: clang -target arm64-apple-ios16.0 -c  ->  lld -flavor darwin (resolves relocations)  ->  mkstatic.py (static, ad-hoc signed
re-layout; see its docstring for why and what it refuses). Nothing here talks to the phone.
"""
import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "src"
sys.path.insert(0, str(HERE))
import mkstatic  # noqa: E402

TARGET = "arm64-apple-ios16.0"
# freestanding: no libc, no compiler-generated memcpy/memset (they would be undefined symbols and the link would fail), no stack protector
# (it needs a guard symbol), no unwind tables (they would add sections the static wrapper does not carry)
CFLAGS = ["-O2", "-Wall", "-Wextra", "-Werror", "-ffreestanding", "-fno-builtin", "-fno-stack-protector",
          "-fno-asynchronous-unwind-tables", "-fno-unwind-tables"]
LLD = ["lld", "-flavor", "darwin", "-arch", "arm64", "-platform_version", "ios", "16.0", "16.0", "-e", "_start"]
HOST_CFLAGS = ["-O2", "-Wall", "-Wextra", "-Werror", "-DHOST_TEST"]
DEFAULT_ROOT_DEV = "/dev/rmd1"
DEFAULT_CHUNK = 131072


def sha(b):
    return hashlib.sha256(b).hexdigest()


def run(argv):
    r = subprocess.run([str(a) for a in argv], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit("command failed (exit %d): %s\n%s%s" % (r.returncode, " ".join(map(str, argv)), r.stdout[-1000:], r.stderr[-2000:]))
    return r


def version(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    return (r.stdout or r.stderr).strip().splitlines()[0] if (r.stdout or r.stderr) else "unknown"


def defines(root_dev, chunk, console_dev=None):
    if not root_dev.startswith("/dev/") or '"' in root_dev or "\\" in root_dev:
        raise SystemExit("root device %r is not a plain /dev path" % root_dev)
    if chunk <= 0 or chunk % 512 or chunk > 1 << 20:
        raise SystemExit("chunk %d must be a positive multiple of 512 and at most 1 MiB (it lives on the 16 KiB-page user stack)" % chunk)
    d = ['-DROOT_DEV="%s"' % root_dev, "-DCHUNK=%d" % chunk]
    if console_dev:
        d.append('-DCONSOLE_DEV="%s"' % console_dev)
    return d


def link_probe(work, root_dev=DEFAULT_ROOT_DEV, chunk=DEFAULT_CHUNK, source=None, extra=()):
    """clang + lld -> the linked (still dynamic-flavoured) Mach-O; `source` and `extra` let tests feed a different C file or flags."""
    obj, linked = work / "hash-probe.o", work / "hash-probe.lld"
    cmd = ["clang", "-target", TARGET] + CFLAGS + defines(root_dev, chunk) + list(extra) + ["-I", SRC, "-c", source or SRC / "hash-probe.c", "-o", obj]
    run(cmd)
    lcmd = LLD + ["-o", linked, obj]
    run(lcmd)
    return linked, [cmd, lcmd]


def build_probe(work, root_dev=DEFAULT_ROOT_DEV, chunk=DEFAULT_CHUNK, extra=()):
    linked, cmds = link_probe(work, root_dev, chunk, extra=extra)
    out = work / "hash-probe"
    out.write_bytes(mkstatic.wrap(linked.read_bytes()))
    return out.read_bytes(), linked.read_bytes(), cmds


def build_host(out, extra=()):
    cmd = ["cc"] + HOST_CFLAGS + list(extra) + ["-I", SRC, SRC / "host-main.c", "-o", out]
    run(cmd)
    return cmd


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--root-dev", default=DEFAULT_ROOT_DEV)
    ap.add_argument("--chunk", type=int, default=DEFAULT_CHUNK)
    a = ap.parse_args(argv)
    if a.out.exists():
        raise SystemExit("%s exists: pick a new directory" % a.out)
    a.out.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="nat077-", dir=a.out) as w:
        work = str(w)
        probe, linked, cmds = build_probe(Path(w), a.root_dev, a.chunk)
    (a.out / "hash-probe").write_bytes(probe)
    hcmd = build_host(a.out / "host-probe")
    info = {
        "probe": {"bytes": len(probe), "sha256": sha(probe)},
        "lld_output": {"bytes": len(linked), "sha256": sha(linked)},
        "root_dev": a.root_dev, "chunk": a.chunk,
        "sources_sha256": {p.name: sha(p.read_bytes()) for p in sorted(SRC.iterdir()) if p.is_file()},
        "mkstatic_sha256": sha((HERE / "mkstatic.py").read_bytes()),
        "mkinit_sha256": mkstatic.MKINIT_SHA256,
        "toolchain": {"clang": version(["clang", "--version"]), "lld": version(["lld", "-flavor", "darwin", "--version"]),
                      "cc": version(["cc", "--version"])},
        "commands": [" ".join(map(str, c)).replace(work, "$WORK").replace(str(a.out), "$OUT").replace(str(HERE.parents[2]), "$REPO")
                     for c in cmds + [hcmd]],
    }
    (a.out / "hash-probe.json").write_text(json.dumps(info, indent=2, sort_keys=True) + "\n")
    print("%s: %d bytes sha256 %s" % (a.out / "hash-probe", len(probe), sha(probe)))


if __name__ == "__main__":
    main()
