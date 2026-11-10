#!/usr/bin/env python3
"""NAT-006: build a RECOVERY-format E1S XNU test image and the stock RECOVERY restore package.

Host only. Never flashes, never talks to a device. The output is meant for a later, separately authorized test.

  e1s_recovery.py --root MAIN_CHECKOUT --run ID [--kernel MACHO]

Pipeline:
  1. tools/build/e1s.py builds the loader with the accepted STR-002/STR-005/STR-019 patches.
  2. The NAT-006 loader patch (size-only reserved-memory nodes, S-Boot bootargs framebuffer) is applied on top
     and the loader is rebuilt with the same compiler flags.
  3. The upstream mkadt.py synthesizes the ADT (no Apple donor data); mkpayload.py packs the project-built
     STR-041 kernel and the ADT into a SWEETXNU payload; append_payload.py appends it to the loader Image.
  4. A boot image header v2 is written from the verified stock RECOVERY backup: header fields, recovery_dtbo
     and DTB stay byte-identical; only the kernel, ramdisk, sizes and id change. The AVB footer mirrors the
     Magisk-patched init_boot that this S-Boot is measured to accept (NAT-001): in-partition vbmeta copied,
     hash descriptor image_size updated, digest and signature left stale.
  5. The restore package is the stock backup itself, checked against the on-device hash, plus an Odin tar.
  6. docs/procedures/nat-006/verify_image.py re-parses everything independently.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tarfile

TOOLS = Path(__file__).resolve().parents[1]
REPO = TOOLS.parent  # where this tool, its patch and its verifier live (may be a worktree)
PROC = REPO / "docs/procedures/nat-006"

PARTITION_SIZE = 100663296  # RECOVERY, measured (NAT-001)
STOCK_RECOVERY = "devices/recovery/backups/2026-11-10/recovery.img"
STOCK_RECOVERY_SHA256 = "96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67"  # equal on the phone
KERNEL = "worktrees/str-041-e1s-native-link-image-20261110/artifacts/e1s-native-link/link-001/kernel/kernel.unstripped"
KERNEL_SHA256 = "4c9536d89b6ad61e49e8cc45e82820f00df4343c478d14685009ad504313595f"  # STR-041 evidence
PATCH = PROC / "patches/0001-loader-sboot-dynamic-reservations-and-framebuffer.patch"
PATCH_SHA256 = "dbfb5c3ac316b0b02b501be399cd3cb584699a24a8b58842b6612d7799a2643f"
UI_PATCH = PROC / "patches/0002-loader-ui-pc-relative-string-tables.patch"
UI_PATCH_SHA256 = "31c62fa7443d9b5650e99158bed90b8e3f8f93f26a9db66ef98c0033e5320c40"
# STR-019 postimage that the NAT-006 patches apply to (tools/build/e1s.py expected_postimages).
PATCH_PREIMAGE = {
    "shim/e1s-xnu/loader.c": "5ccbad90459fd90d2ca40b03b0f64bc32919544c2f8b47e90ea6570d0e33cad8",
    "shim/e1s-xnu/ui.c": "ab1537ead796f168e02a7d380aa75ca7907efc12f4dcd4beed7f78746ce5135d",
}
PATCH_POSTIMAGE = {
    "fdt.c": "3d18546d9b30ba3bd89392ae3eef42b448d7cda1cdc4e1fce240f0c4836b7647",
    "fdt.h": "50a8744fba244d405bf0b8323d86535b63a3944ed8def58e03eeae90464ec0a2",
    "loader.c": "961f15a2b5cc92ce0d0fa78fac207b90b37bfdab6e4827d8006fc021f4c9b276",
    "ui.c": "ff78e9d057d6877da5707d1fcc907ac7307cca0ea2257fb41029f514712b067f",
}
# e1s.hold=10 keeps the loader screen up for 10 s before the jump so it can be photographed.
CMDLINE = "e1s.hold=10 debug=0xc serial=3 cpus=1 keepsyms=1 -v"
LOADER_FILES = ["start.S", "loader.c", "ui.c", "adt_patch.c", "gic.c", "fdt.c"]
CFLAGS = ["-O2", "-g0", "-ffreestanding", "-fno-builtin", "-fno-stack-protector", "-fno-pic",
          "-fno-zero-initialized-in-bss", "-mstrict-align", "-mgeneral-regs-only", "-Wall", "-Wextra"]  # = e1s.py
SEANDROID = b"SEANDROIDENFORCE"
V2_HEADER_SIZE = 1660
AVB_FOOTER = 64


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def align(n: int, a: int) -> int:
    return (n + a - 1) // a * a


def v2_fields(img: bytes) -> dict:
    if img[:8] != b"ANDROID!" or struct.unpack_from("<I", img, 40)[0] != 2:
        raise ValueError("not a boot image header v2")
    k, ka, r, ra, s, sa, ta, ps, hv, osv = struct.unpack_from("<10I", img, 8)
    rdtbo_size, = struct.unpack_from("<I", img, 1632)
    rdtbo_off, = struct.unpack_from("<Q", img, 1636)
    hsize, dtb_size = struct.unpack_from("<II", img, 1644)
    return dict(kernel_size=k, ramdisk_size=r, second_size=s, page_size=ps, header_version=hv, os_version=osv,
                recovery_dtbo_size=rdtbo_size, recovery_dtbo_offset=rdtbo_off, header_size=hsize, dtb_size=dtb_size)


def v2_sections(img: bytes) -> dict:
    f = v2_fields(img)
    ps, off, out = f["page_size"], f["page_size"], {}
    for name in ("kernel", "ramdisk", "second", "recovery_dtbo", "dtb"):
        size = f[name + "_size"]
        out[name] = (off, size)
        off += align(size, ps)
    out["end"] = (off, 0)
    return out


def mkbootimg_id(parts) -> bytes:
    """mkbootimg's v2 id: SHA-1 over each section followed by its little-endian u32 size, zero-padded to 32."""
    h = hashlib.sha1()
    for data in parts:
        h.update(data)
        h.update(struct.pack("<I", len(data)))
    return h.digest() + b"\0" * 12


def avb_footer(img: bytes):
    f = img[-AVB_FOOTER:]
    if f[:4] != b"AVBf":
        raise ValueError("no AVB footer")
    major, minor, orig, voff, vsize = struct.unpack(">IIQQQ", f[4:36])
    return dict(major=major, minor=minor, original_image_size=orig, vbmeta_offset=voff, vbmeta_size=vsize)


def vbmeta_hash_descriptor_offset(vbmeta: bytes, partition: bytes) -> int:
    """Offset inside vbmeta of the u64 image_size of the hash descriptor for `partition`."""
    if vbmeta[:4] != b"AVB0":
        raise ValueError("bad vbmeta magic")
    auth, aux = struct.unpack_from(">QQ", vbmeta, 12)
    desc_off, desc_size = struct.unpack_from(">QQ", vbmeta, 96)
    base = 256 + auth
    p = base + desc_off
    while p < base + desc_off + desc_size:
        tag, nbytes = struct.unpack_from(">QQ", vbmeta, p)
        if tag == 2:
            name_len, = struct.unpack_from(">I", vbmeta, p + 16 + 40)
            if vbmeta[p + 16 + 116:p + 16 + 116 + name_len] == partition:
                return p + 16
        p += 16 + nbytes
    raise ValueError("hash descriptor not found")


def build_recovery(stock: bytes, kernel: bytes, ramdisk: bytes, partition_size: int = PARTITION_SIZE):
    """Stock header v2 with kernel/ramdisk replaced; stock recovery_dtbo, DTB and in-partition vbmeta reused."""
    f, sec = v2_fields(stock), v2_sections(stock)
    if f["second_size"]:
        raise ValueError("stock image has a second stage; not handled")
    ps = f["page_size"]
    rdtbo = stock[sec["recovery_dtbo"][0]:sum(sec["recovery_dtbo"])]
    dtb = stock[sec["dtb"][0]:sum(sec["dtb"])]
    header = bytearray(stock[:ps])
    struct.pack_into("<I", header, 8, len(kernel))
    struct.pack_into("<I", header, 16, len(ramdisk))
    rdtbo_off = ps + align(len(kernel), ps) + align(len(ramdisk), ps)
    struct.pack_into("<Q", header, 1636, rdtbo_off if rdtbo else 0)
    header[576:608] = mkbootimg_id([kernel, ramdisk, b"", rdtbo, dtb])
    out = bytearray(header)
    for data in (kernel, ramdisk, rdtbo, dtb):
        out += data + b"\0" * (align(len(data), ps) - len(data))
    out += SEANDROID
    orig = len(out)
    footer = avb_footer(stock)
    vbmeta = bytearray(stock[footer["vbmeta_offset"]:footer["vbmeta_offset"] + footer["vbmeta_size"]])
    struct.pack_into(">Q", vbmeta, vbmeta_hash_descriptor_offset(vbmeta, b"recovery"), orig)
    voff = align(orig, 4096)
    if voff + len(vbmeta) > partition_size - AVB_FOOTER:
        raise ValueError(f"image does not fit: {voff + len(vbmeta)} > {partition_size - AVB_FOOTER}")
    out += b"\0" * (voff - orig) + vbmeta
    out += b"\0" * (partition_size - AVB_FOOTER - len(out))
    out += b"AVBf" + struct.pack(">IIQQQ", footer["major"], footer["minor"], orig, voff, len(vbmeta)) + b"\0" * 28
    assert len(out) == partition_size
    info = dict(content_end=orig, vbmeta_offset=voff, recovery_dtbo_offset=rdtbo_off, page_size=ps,
                free_bytes=partition_size - AVB_FOOTER - voff - len(vbmeta))
    return bytes(out), info


def newc_cpio(files) -> bytes:
    """Deterministic SVR4 newc cpio (mode, uid, gid, mtime fixed)."""
    out, ino = bytearray(), 1
    for name, data in [*files, ("TRAILER!!!", b"")]:
        raw = name.encode() + b"\0"
        mode = 0o100644 if name != "TRAILER!!!" else 0
        fields = [ino if name != "TRAILER!!!" else 0, mode, 0, 0, 1, 0, len(data), 0, 0, 0, 0, len(raw), 0]
        out += b"070701" + b"".join(b"%08X" % v for v in fields) + raw
        out += b"\0" * (-len(out) % 4) + data
        out += b"\0" * (-len(out) % 4)
        ino += 1
    out += b"\0" * (-len(out) % 512)
    return bytes(out)


PLACEHOLDER = ("NAT006", b"NAT-006 placeholder ramdisk. The SWEETXNU payload is appended to the kernel Image; "
                         b"nothing here is executed.\n")


def odin_tar(name: str, data: bytes) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        member = tarfile.TarInfo(name)
        member.size, member.mode, member.mtime, member.uname, member.gname = len(data), 0o644, 0, "", ""
        tar.addfile(member, io.BytesIO(data))
    return buf.getvalue()


def run(argv, cwd, log, check=True):
    result = subprocess.run([str(x) for x in argv], cwd=cwd, capture_output=True, text=True, timeout=300,
                            env={**os.environ, "SOURCE_DATE_EPOCH": "0", "LC_ALL": "C", "TZ": "UTC"})
    log.append(dict(argv=[str(x) for x in argv], cwd=str(cwd), exit_code=result.returncode,
                    stdout=result.stdout[-4000:], stderr=result.stderr[-4000:]))
    if check and result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {argv}\n{result.stderr[-2000:]}")
    return result


def absolute_relocations(objects, log, cwd):
    """R_AARCH64_ABS* relocations in the loader objects; the loader runs wherever S-Boot puts it."""
    found = {}
    for obj in objects:
        text = run(["readelf", "-rW", obj], cwd, log).stdout
        rows = [line.split() for line in text.splitlines() if "R_AARCH64_ABS" in line]
        if rows:
            found[obj.name] = [" ".join(r[2:]) for r in rows]
    return found


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build(root: Path, ident: str, kernel_path: Path) -> int:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,60}", ident):
        raise RuntimeError("use a simple run identifier")
    out = root / "artifacts/nat-006" / ident
    out.mkdir(parents=True, exist_ok=False)
    log = []
    report = dict(schema_version=1, task="NAT-006", kind="host-test", origin="local-host", outcome="fail",
                  recorded_at=datetime.now(timezone.utc).isoformat(timespec="seconds"), commands=log,
                  flashed=False, device_used=False, hardware_execution=False, apple_donor_data=False)
    try:
        # 1. Accepted loader build.
        e1s = load("e1s_build", TOOLS / "build/e1s.py")
        base_id = f"nat006-{ident}-base"
        if e1s.build(root, base_id) != 0:
            raise RuntimeError("tools/build/e1s.py failed")
        base_dir = root / "artifacts/e1s-build" / base_id
        base = json.loads((base_dir / "report.json").read_text())
        report["base_build"] = dict(report=str((base_dir / "report.json").relative_to(root)), outcome=base["outcome"],
                                    patches={k: base[k]["sha256"] for k in ("source_patch", "display_source_patch",
                                                                            "boot_log_source_patch")})
        # 2. NAT-006 patch on a copy of the accepted source.
        src = out / "source"
        shutil.copytree(base_dir / "source", src)
        for rel, want in PATCH_PREIMAGE.items():
            if sha256((src / rel).read_bytes()) != want:
                raise RuntimeError("NAT-006 patch preimage changed: " + rel)
        patch = PATCH.read_bytes()
        if sha256(patch) != PATCH_SHA256:
            raise RuntimeError("NAT-006 patch identity changed")
        (out / PATCH.name).write_bytes(patch)
        run(["git", "--git-dir=/dev/null", "apply", "--check", out / PATCH.name], src, log)
        run(["git", "--git-dir=/dev/null", "apply", out / PATCH.name], src, log)
        ui_patch = UI_PATCH.read_bytes()
        if sha256(ui_patch) != UI_PATCH_SHA256:
            raise RuntimeError("NAT-006 UI patch identity changed")
        (out / UI_PATCH.name).write_bytes(ui_patch)
        run(["git", "--git-dir=/dev/null", "apply", "--check", out / UI_PATCH.name], src, log)
        run(["git", "--git-dir=/dev/null", "apply", out / UI_PATCH.name], src, log)
        postimages = {f: sha256((src / "shim/e1s-xnu" / f).read_bytes()) for f in ("fdt.c", "fdt.h", "loader.c", "ui.c")}
        for fname, want_sha in PATCH_POSTIMAGE.items():
            if postimages[fname] != want_sha:
                raise RuntimeError(f"NAT-006 patch postimage mismatch for {fname}: {postimages[fname]} != {want_sha}")
        report["nat006_patch"] = dict(path=str(PATCH.relative_to(REPO)), sha256=PATCH_SHA256,
                                      ui_patch=dict(path=str(UI_PATCH.relative_to(REPO)), sha256=UI_PATCH_SHA256),
                                      postimages=postimages)
        ldir = out / "loader"
        ldir.mkdir()
        objects = []
        for f in LOADER_FILES:
            obj = ldir / (f + ".o")
            run(["zig", "cc", "-target", "aarch64-freestanding", *CFLAGS, "-c", src / "shim/e1s-xnu" / f, "-o", obj], root, log)
            objects.append(obj)
        elf, image = ldir / "loader.elf", ldir / "Image"
        run(["zig", "cc", "-target", "aarch64-freestanding", "-static", "-nostdlib", "-Wl,--build-id=none",
             "-Wl,-T," + str(src / "shim/e1s-xnu/loader.ld"), *objects, "-o", elf], root, log)
        run(["zig", "objcopy", "-O", "binary", elf, image], root, log)
        run([sys.executable, "-I", src / "tools/e1s/fix_image.py", image], root, log)
        report["loader"] = dict(toolchain=run(["zig", "version"], root, log).stdout.strip(), cflags=CFLAGS,
                                absolute_relocations=absolute_relocations(objects, log, root),
                                image=dict(size=image.stat().st_size, sha256=sha256(image.read_bytes())))
        # 3. ADT, payload, kernel section.
        kernel = (root / kernel_path).read_bytes() if not kernel_path.is_absolute() else kernel_path.read_bytes()
        if sha256(kernel) != KERNEL_SHA256:
            raise RuntimeError("kernel is not the STR-041 image")
        xnu_tools = src / "tools/e1s/xnu"
        donor = xnu_tools / "../../../research/ipsw-x/d22ap.adt"
        if donor.exists():
            raise RuntimeError("Apple donor ADT present in the build tree; refusing to use it")
        adt = out / "e1s.adt"
        adt_run = run([sys.executable, "-I", xnu_tools / "mkadt.py", adt], out, log)
        payload = out / "payload.bin"
        run([sys.executable, "-I", xnu_tools / "mkpayload.py", root / KERNEL if not kernel_path.is_absolute() else kernel_path,
             adt, payload, "--cmdline", CMDLINE], out, log)
        kimage = out / "Image.payload"
        run([sys.executable, "-I", src / "tools/e1s/append_payload.py", "--loader", image, "--payload", payload,
             "--output", kimage], out, log)
        report["payload"] = dict(kernel=dict(path=str(kernel_path), sha256=KERNEL_SHA256, size=len(kernel)),
                                 adt=dict(size=adt.stat().st_size, sha256=sha256(adt.read_bytes()),
                                          donor_warning="no /product node" in adt_run.stderr + adt_run.stdout),
                                 payload=dict(size=payload.stat().st_size, sha256=sha256(payload.read_bytes())),
                                 cmdline=CMDLINE,
                                 kernel_section=dict(size=kimage.stat().st_size, sha256=sha256(kimage.read_bytes())))
        # 4. RECOVERY image.
        stock = (root / STOCK_RECOVERY).read_bytes()
        if sha256(stock) != STOCK_RECOVERY_SHA256:
            raise RuntimeError("stock RECOVERY backup hash differs from the on-device measurement")
        ramdisk = newc_cpio([PLACEHOLDER])
        img, info = build_recovery(stock, kimage.read_bytes(), ramdisk)
        target = out / "recovery-nat006.img"
        target.write_bytes(img)
        report["image"] = dict(path=str(target.relative_to(root)), size=len(img), sha256=sha256(img),
                               ramdisk=dict(size=len(ramdisk), sha256=sha256(ramdisk)), **info)
        # 5. Restore package: the verified stock backup, unchanged.
        rdir = out / "restore"
        rdir.mkdir()
        (rdir / "recovery.img").write_bytes(stock)
        tar = odin_tar("recovery.img", stock)
        (rdir / "recovery-stock-odin.tar").write_bytes(tar)
        (rdir / "SHA256SUMS").write_text(f"{sha256(stock)}  recovery.img\n{sha256(tar)}  recovery-stock-odin.tar\n")
        report["restore"] = dict(image=dict(path=str((rdir / "recovery.img").relative_to(root)), sha256=sha256(stock),
                                            equals_on_device_measurement=sha256(stock) == STOCK_RECOVERY_SHA256),
                                 odin_tar=dict(path=str((rdir / "recovery-stock-odin.tar").relative_to(root)),
                                               sha256=sha256(tar), member="recovery.img"))
        # 6. Independent verification.
        vjson = out / "verify.json"
        v = run([sys.executable, "-I", PROC / "verify_image.py", "--image", target, "--stock", root / STOCK_RECOVERY,
                 "--kernel", root / KERNEL if not kernel_path.is_absolute() else kernel_path,
                 "--restore-dir", rdir, "--dtb", root / "devices/e1s-fdt/2026-11-10/runtime.dtb", "--out", vjson],
                out, log, check=False)
        verdict = json.loads(vjson.read_text()) if vjson.exists() else {}
        report["verify"] = dict(exit_code=v.returncode, report=str(vjson.relative_to(root)), ok=verdict.get("ok"),
                                failed=[c["name"] for c in verdict.get("checks", []) if not c["ok"]])
        report["outcome"] = "pass" if v.returncode == 0 and verdict.get("ok") else "fail"
    except Exception as exc:  # recorded, never hidden
        report["error"] = str(exc)
    finally:
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(dict(outcome=report["outcome"], report=str((out / "report.json").relative_to(root)),
                          image=report.get("image", {}).get("sha256"), error=report.get("error"),
                          failed=report.get("verify", {}).get("failed")), indent=2))
    return 0 if report["outcome"] == "pass" else 1


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", type=Path, default=REPO, help="checkout holding references/, devices/ and artifacts/")
    p.add_argument("--run", required=True)
    p.add_argument("--kernel", type=Path, default=Path(KERNEL))
    a = p.parse_args()
    return build(a.root.resolve(), a.run, a.kernel)


if __name__ == "__main__":
    sys.exit(main())
