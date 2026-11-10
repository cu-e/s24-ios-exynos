#!/usr/bin/env python3
"""NAT-006 independent verifier for the RECOVERY-format E1S XNU test image (host only).

Shares no code with tools/build/e1s_recovery.py. Every structure is re-parsed from bytes and compared
with the stock RECOVERY backup, the phone's measured runtime FDT, and the STR-041 kernel Mach-O.
Writes a JSON report; exits 0 only if every check passes.

  verify_image.py --image IMG --stock STOCK --kernel MACHO --restore-dir DIR --dtb DTB --out REPORT.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tarfile

HERE = Path(__file__).resolve().parent
PARTITION = 100663296
STOCK_SHA256 = "96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67"
STOCK_DTB_SHA256 = "9b77987a324b1cdb93c82de8864b88446e1509459a0731c144d521c647ed17c1"
STOCK_RDTBO_SHA256 = "d46ff41eaf10ceaafac06ba24f0ec167c94cb5f74710778debaa8406eb73bcf9"
KERNEL_SHA256 = "4c9536d89b6ad61e49e8cc45e82820f00df4343c478d14685009ad504313595f"
RUNTIME_DTB_SHA256 = "95fa811abca3f5f8889705add485f94c4490c57a853bded10539d4631bef46c3"
CMDLINE = b"e1s.hold=10 debug=0xc serial=3 cpus=1 keepsyms=1 -v"
KERNEL_VIRT_BASE = 0xFFFFFFF004000000
KERNEL_ENTRY_VA = 0xFFFFFFF00743B4A8
WINDOW = 0x20000000  # NAT-006 harness: the loader's 512 MiB window on the runtime FDT
LC_SEGMENT_64 = 0x19
LC_UNIXTHREAD = 0x5
LC_DYLD_CHAINED_FIXUPS = 0x80000034


def h(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def up(n: int, a: int) -> int:
    return -(-n // a) * a if a else n


def header(img: bytes) -> dict:
    u = lambda o: struct.unpack_from("<I", img, o)[0]
    q = lambda o: struct.unpack_from("<Q", img, o)[0]
    return dict(
        magic=img[:8],
        kernel_size=u(8),
        kernel_addr=u(12),
        ramdisk_size=u(16),
        ramdisk_addr=u(20),
        second_size=u(24),
        second_addr=u(28),
        tags_addr=u(32),
        page_size=u(36),
        version=u(40),
        os_version=u(44),
        name=img[48:64],
        cmdline=img[64:576],
        id=img[576:608],
        extra=img[608:1632],
        rdtbo_size=u(1632),
        rdtbo_off=q(1636),
        header_size=u(1644),
        dtb_size=u(1648),
        dtb_addr=q(1652),
    )


def sections(hd: dict) -> dict:
    ps = hd["page_size"]
    off = ps
    out = {}
    for name, key in (
        ("kernel", "kernel_size"),
        ("ramdisk", "ramdisk_size"),
        ("second", "second_size"),
        ("recovery_dtbo", "rdtbo_size"),
        ("dtb", "dtb_size"),
    ):
        sz = hd[key]
        out[name] = (off, sz, up(sz, ps))
        off += up(sz, ps)
    out["end"] = (off, 0, 0)
    return out


def expected_v2_id(parts: list[bytes]) -> bytes:
    sha = hashlib.sha1()
    for part in parts:
        sha.update(part)
        sha.update(struct.pack("<I", len(part)))
    return sha.digest() + b"\0" * 12


def parse_avb_footer(img: bytes) -> dict | None:
    tail = img[-64:]
    if tail[:4] != b"AVBf":
        return None
    major, minor, orig_size, vbmeta_off, vbmeta_size = struct.unpack_from(">IIQQQ", tail, 4)
    return dict(
        major=major,
        minor=minor,
        original_image_size=orig_size,
        vbmeta_offset=vbmeta_off,
        vbmeta_size=vbmeta_size,
        reserved_zero=not any(tail[36:]),
    )


def parse_vbmeta_recovery_desc(vbmeta: bytes) -> dict | None:
    if len(vbmeta) < 256 or vbmeta[:4] != b"AVB0":
        return None
    auth_size, aux_size = struct.unpack_from(">QQ", vbmeta, 12)
    desc_off, desc_size = struct.unpack_from(">QQ", vbmeta, 96)
    base = 256 + auth_size
    if base + aux_size > len(vbmeta):
        return None
    p = base + desc_off
    end = p + desc_size
    while p + 16 <= end:
        tag, nbytes = struct.unpack_from(">QQ", vbmeta, p)
        body = p + 16
        if tag == 2 and body + 116 <= end:
            image_size = struct.unpack_from(">Q", vbmeta, body)[0]
            hash_alg = vbmeta[body + 8 : body + 40].split(b"\0", 1)[0].decode("ascii", "replace")
            name_len, salt_len, dig_len, flags = struct.unpack_from(">IIII", vbmeta, body + 40)
            nstart = body + 116
            part_name = vbmeta[nstart : nstart + name_len]
            salt = vbmeta[nstart + name_len : nstart + name_len + salt_len]
            digest = vbmeta[nstart + name_len + salt_len : nstart + name_len + salt_len + dig_len]
            if part_name == b"recovery":
                return dict(
                    image_size_offset=body,
                    image_size=image_size,
                    hash_algorithm=hash_alg,
                    flags=flags,
                    salt=salt.hex(),
                    digest=digest.hex(),
                )
        p += 16 + nbytes
    return None


def parse_cpio_newc(blob: bytes) -> list[tuple[str, bytes]]:
    entries = []
    p = 0
    while p + 110 <= len(blob):
        if blob[p : p + 6] != b"070701":
            raise ValueError(f"bad cpio magic at {p}")
        filesize = int(blob[p + 54 : p + 62], 16)
        namesize = int(blob[p + 94 : p + 102], 16)
        nstart = p + 110
        nend = nstart + namesize
        name = blob[nstart : nend - 1].decode("utf-8", "replace")
        dstart = up(nend, 4)
        dend = dstart + filesize
        if dend > len(blob):
            raise ValueError("cpio entry exceeds archive")
        data = blob[dstart:dend]
        p = up(dend, 4)
        if name == "TRAILER!!!":
            return entries
        entries.append((name, data))
    raise ValueError("missing cpio TRAILER!!!")


def parse_macho_and_rebase(raw: bytes) -> dict:
    buf = bytearray(raw)
    if len(buf) < 32:
        raise ValueError("Mach-O too small")
    magic, cputype, cpusub, ftype, ncmds, sizeofcmds, flags, _ = struct.unpack_from("<8I", buf, 0)
    if magic != 0xFEEDFACF or cputype != 0x0100000C or ftype != 2:
        raise ValueError("not an ARM64 MH_EXECUTE Mach-O")
    segs, entry, fixups = [], None, None
    off = 32
    for _ in range(ncmds):
        cmd, sz = struct.unpack_from("<II", buf, off)
        if cmd == LC_SEGMENT_64:
            name = buf[off + 8 : off + 24].split(b"\0", 1)[0].decode("ascii", "replace")
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from("<4Q", buf, off + 24)
            segs.append(dict(name=name, vmaddr=vmaddr, vmsize=vmsize, fileoff=fileoff, filesize=filesize))
        elif cmd == LC_UNIXTHREAD:
            flavor, count = struct.unpack_from("<II", buf, off + 8)
            if flavor != 6 or count != 68:
                raise ValueError("unexpected LC_UNIXTHREAD state")
            entry = struct.unpack_from("<Q", buf, off + 16 + 32 * 8)[0]
        elif cmd == LC_DYLD_CHAINED_FIXUPS:
            fixups = struct.unpack_from("<II", buf, off + 8)
        off += sz
    nfix = 0
    if fixups:
        data_off, _ = fixups
        _, starts_off, _, _, imports_count, _, _ = struct.unpack_from("<7I", buf, data_off)
        if imports_count != 0:
            raise ValueError("kernel has dynamic imports")
        image_base = segs[0]["vmaddr"]
        seg_count = struct.unpack_from("<I", buf, data_off + starts_off)[0]
        for i in range(seg_count):
            seg_info = struct.unpack_from("<I", buf, data_off + starts_off + 4 + 4 * i)[0]
            if not seg_info:
                continue
            base = data_off + starts_off + seg_info
            _, page_size, fmt, _, _, page_count = struct.unpack_from("<IHHQIH", buf, base)
            starts = struct.unpack_from(f"<{page_count}H", buf, base + 22)
            seg = segs[i]
            for page_idx, start in enumerate(starts):
                if start == 0xFFFF:
                    continue
                loc = seg["fileoff"] + page_idx * page_size + start
                while True:
                    val = struct.unpack_from("<Q", buf, loc)[0]
                    if fmt in (2, 6):
                        target = val & ((1 << 36) - 1)
                        high8 = (val >> 36) & 0xFF
                        nxt = (val >> 51) & 0xFFF
                        if fmt == 6:
                            target += image_base
                        target |= high8 << 56
                        stride = 4
                    elif fmt == 8:
                        target = image_base + (val & ((1 << 30) - 1))
                        nxt = (val >> 51) & 0xFFF
                        stride = 4
                    elif fmt in (1, 7, 9, 12):
                        auth = val >> 63
                        nxt = (val >> 51) & 0x7FF
                        stride = 4 if fmt in (7, 12) else 8
                        if auth:
                            target = val & 0xFFFFFFFF
                        else:
                            target = (val & ((1 << 43) - 1)) | (((val >> 43) & 0xFF) << 56)
                        if fmt in (7, 9, 12) or auth:
                            target += image_base
                    else:
                        raise ValueError(f"unsupported fixup format {fmt}")
                    struct.pack_into("<Q", buf, loc, target)
                    nfix += 1
                    if not nxt:
                        break
                    loc += nxt * stride
    mapped_segs = []
    for s in segs:
        if s["vmsize"] > 0:
            data = bytes(buf[s["fileoff"] : s["fileoff"] + s["filesize"]])
            mapped_segs.append({**s, "rebased_sha256": h(data), "rebased_len": len(data)})
    return dict(entry=entry, flags=flags, fixups_applied=nfix, segments=mapped_segs)


def parse_adt_nodes(blob: bytes) -> dict:
    def walk(off: int, path: str, out: dict) -> int:
        nprops, nchildren = struct.unpack_from("<II", blob, off)
        off += 8
        props = {}
        for _ in range(nprops):
            raw_name = blob[off : off + 32].split(b"\0", 1)[0].decode("ascii", "replace")
            plen = struct.unpack_from("<I", blob, off + 32)[0] & 0x7FFFFFFF
            off += 36
            val = blob[off : off + plen]
            off = up(off + plen, 4)
            props[raw_name] = val
        node_name = props.get("name", b"").split(b"\0", 1)[0].decode("ascii", "replace")
        cur_path = "/" if not path else (f"/{node_name}" if path == "/" else f"{path}/{node_name}")
        out[cur_path] = props
        for _ in range(nchildren):
            off = walk(off, cur_path, out)
        return off

    nodes: dict = {}
    end_off = walk(0, "", nodes)
    return dict(end_offset=end_off, nodes=nodes)


def verify_all(
    image_path: Path,
    stock_path: Path,
    kernel_path: Path,
    restore_dir: Path,
    dtb_path: Path,
    out_path: Path,
) -> int:
    checks: list[dict] = []

    def check(name: str, ok: bool, **detail):
        checks.append(dict(name=name, ok=bool(ok), **detail))
        return bool(ok)

    img = image_path.read_bytes()
    stock = stock_path.read_bytes()
    kernel_raw = kernel_path.read_bytes()
    runtime_dtb = dtb_path.read_bytes()

    check("stock_recovery_sha256", h(stock) == STOCK_SHA256, actual=h(stock), expected=STOCK_SHA256, size=len(stock))
    check("str041_kernel_sha256", h(kernel_raw) == KERNEL_SHA256, actual=h(kernel_raw), expected=KERNEL_SHA256, size=len(kernel_raw))
    check("runtime_dtb_sha256", h(runtime_dtb) == RUNTIME_DTB_SHA256, actual=h(runtime_dtb), expected=RUNTIME_DTB_SHA256, size=len(runtime_dtb))
    check("partition_size_exact", len(img) == PARTITION and len(stock) == PARTITION, image_size=len(img), partition_size=PARTITION)

    hd = header(img)
    shd = header(stock)
    sec = sections(hd)
    ssec = sections(shd)

    # 1. Boot image v2 header checks
    same_keys = (
        "magic",
        "kernel_addr",
        "ramdisk_addr",
        "second_size",
        "second_addr",
        "tags_addr",
        "page_size",
        "version",
        "os_version",
        "name",
        "cmdline",
        "extra",
        "rdtbo_size",
        "header_size",
        "dtb_size",
        "dtb_addr",
    )
    mismatched_keys = [k for k in same_keys if hd[k] != shd[k]]
    check(
        "header_v2_matches_stock_invariants",
        hd["magic"] == b"ANDROID!" and hd["version"] == 2 and hd["header_size"] == 1660 and not mismatched_keys,
        mismatched=mismatched_keys,
        page_size=hd["page_size"],
        os_version=hex(hd["os_version"]),
        kernel_addr=hex(hd["kernel_addr"]),
        ramdisk_addr=hex(hd["ramdisk_addr"]),
        tags_addr=hex(hd["tags_addr"]),
        dtb_addr=hex(hd["dtb_addr"]),
    )

    ps = hd["page_size"]
    expected_rdtbo_off = ps + sec["kernel"][2] + sec["ramdisk"][2]
    check(
        "header_rdtbo_offset_and_zero_tail",
        hd["rdtbo_off"] == expected_rdtbo_off and not any(img[1660:ps]),
        rdtbo_off=hd["rdtbo_off"],
        expected_rdtbo_off=expected_rdtbo_off,
        header_page_tail_zero=not any(img[1660:ps]),
    )

    k_bytes = img[sec["kernel"][0] : sec["kernel"][0] + sec["kernel"][1]]
    r_bytes = img[sec["ramdisk"][0] : sec["ramdisk"][0] + sec["ramdisk"][1]]
    rdtbo_bytes = img[sec["recovery_dtbo"][0] : sec["recovery_dtbo"][0] + sec["recovery_dtbo"][1]]
    dtb_bytes = img[sec["dtb"][0] : sec["dtb"][0] + sec["dtb"][1]]

    s_rdtbo_bytes = stock[ssec["recovery_dtbo"][0] : ssec["recovery_dtbo"][0] + ssec["recovery_dtbo"][1]]
    s_dtb_bytes = stock[ssec["dtb"][0] : ssec["dtb"][0] + ssec["dtb"][1]]

    calc_id = expected_v2_id([k_bytes, r_bytes, b"", rdtbo_bytes, dtb_bytes])
    check("header_id_sha1_valid", hd["id"] == calc_id and hd["id"] != shd["id"], id_hex=hd["id"].hex())

    # 2. Section padding, stock DTB/DTBO identity, SEANDROIDENFORCE, and AVB footer
    pad_ok = True
    for sname in ("kernel", "ramdisk", "recovery_dtbo", "dtb"):
        soff, ssz, saligned = sec[sname]
        if any(img[soff + ssz : soff + saligned]):
            pad_ok = False
    check("section_page_padding_zero", pad_ok)
    check(
        "recovery_dtbo_matches_stock",
        rdtbo_bytes == s_rdtbo_bytes and h(rdtbo_bytes) == STOCK_RDTBO_SHA256,
        sha256=h(rdtbo_bytes),
        size=len(rdtbo_bytes),
    )
    check(
        "dtb_matches_stock",
        dtb_bytes == s_dtb_bytes and h(dtb_bytes) == STOCK_DTB_SHA256,
        sha256=h(dtb_bytes),
        size=len(dtb_bytes),
    )

    end_off = sec["end"][0]
    seandroid = img[end_off : end_off + 16]
    content_end = end_off + 16
    check("seandroidenforce_trailer", seandroid == b"SEANDROIDENFORCE", offset=end_off)

    avb = parse_avb_footer(img)
    savb = parse_avb_footer(stock)
    check(
        "avb_footer_valid",
        avb is not None
        and savb is not None
        and avb["major"] == savb["major"]
        and avb["minor"] == savb["minor"]
        and avb["original_image_size"] == content_end
        and avb["vbmeta_offset"] == up(content_end, 4096)
        and avb["vbmeta_size"] == savb["vbmeta_size"]
        and avb["reserved_zero"],
        footer=avb,
    )

    if avb and savb:
        voff = avb["vbmeta_offset"]
        vsz = avb["vbmeta_size"]
        vbmeta = img[voff : voff + vsz]
        svbmeta = stock[savb["vbmeta_offset"] : savb["vbmeta_offset"] + savb["vbmeta_size"]]
        desc = parse_vbmeta_recovery_desc(vbmeta)
        sdesc = parse_vbmeta_recovery_desc(svbmeta)
        patched_svbmeta = bytearray(svbmeta)
        if sdesc:
            struct.pack_into(">Q", patched_svbmeta, sdesc["image_size_offset"], content_end)
        free_gap_zero = not any(img[content_end:voff]) and not any(img[voff + vsz : PARTITION - 64])
        check(
            "in_partition_vbmeta_and_free_space",
            desc is not None
            and desc["image_size"] == content_end
            and vbmeta == bytes(patched_svbmeta)
            and free_gap_zero
            and (voff + vsz <= PARTITION - 64),
            vbmeta_offset=voff,
            vbmeta_size=vsz,
            descriptor_image_size=desc["image_size"] if desc else None,
            free_bytes=PARTITION - 64 - (voff + vsz),
        )

    # 3. Ramdisk cpio check
    try:
        cpio_files = parse_cpio_newc(r_bytes)
        check(
            "ramdisk_newc_cpio_valid",
            len(cpio_files) == 1 and cpio_files[0][0] == "NAT006" and b"SWEETXNU" in cpio_files[0][1],
            entries=[name for name, _ in cpio_files],
            ramdisk_size=len(r_bytes),
        )
    except Exception as exc:
        check("ramdisk_newc_cpio_valid", False, error=str(exc))

    # 4. ARM64 Linux Image header & loader binary checks
    if len(k_bytes) >= 64:
        code0, code1, text_off, image_size, flags = struct.unpack_from("<IIQQQ", k_bytes, 0)
        arm64_magic = k_bytes[56:60]
        aligned_offs = [off for off in range(4096, len(k_bytes) - 16, 4096) if k_bytes[off : off + 8] == b"SWEETXNU"]
        payload_off = aligned_offs[0] if len(aligned_offs) == 1 else -1
        loader_part = k_bytes[:payload_off] if payload_off > 0 else b""
        check(
            "arm64_linux_image_header_and_loader",
            arm64_magic == b"ARM\x64"
            and text_off == 0x80000
            and image_size == len(k_bytes)
            and flags == 0xA
            and payload_off >= 4096
            and payload_off % 4096 == 0
            and b"E1SXNU01" in loader_part
            and b"s3cfb.bootloaderfb=" in loader_part,
            code0=hex(code0),
            code1=hex(code1),
            text_offset=hex(text_off),
            image_size=image_size,
            flags=hex(flags),
            payload_offset=payload_off,
            loader_sha256=h(loader_part),
        )
    else:
        payload_off = -1
        check("arm64_linux_image_header_and_loader", False, error="kernel section smaller than 64 bytes")

    # 5. SWEETXNU payload, STR-041 Mach-O segments, and synthesized ADT checks
    if payload_off >= 4096:
        pay = k_bytes[payload_off:]
        pmagic, pver, pnsegs = struct.unpack_from("<8sII", pay, 0)
        virt_base, entry_va, adt_off, adt_size, kernel_end_va, phys_base, mem_size = struct.unpack_from("<7Q", pay, 0x10)
        pcmdline = pay[0x48 : 0x48 + 608].split(b"\0", 1)[0]
        macho = parse_macho_and_rebase(kernel_raw)
        m_segs = macho["segments"]

        seg_checks_ok = pnsegs == len(m_segs)
        seg_details = []
        prev_va_end = virt_base
        for i in range(min(pnsegs, len(m_segs))):
            vmaddr, vmsize, foff, fsz = struct.unpack_from("<4Q", pay, 0x2A8 + 32 * i)
            ms = m_segs[i]
            seg_data = pay[foff : foff + fsz]
            seg_match = (
                vmaddr == ms["vmaddr"]
                and vmsize == ms["vmsize"]
                and fsz == ms["rebased_len"]
                and foff + fsz <= adt_off
                and foff % 8 == 0
                and (i == 0 or foff % 16 == 0)
                and h(seg_data) == ms["rebased_sha256"]
                and vmaddr >= prev_va_end
                and vmaddr + vmsize <= kernel_end_va
            )
            prev_va_end = vmaddr + vmsize
            if not seg_match:
                seg_checks_ok = False
            seg_details.append(
                dict(
                    name=ms["name"],
                    vmaddr=hex(vmaddr),
                    vmsize=hex(vmsize),
                    file_off=foff,
                    file_size=fsz,
                    sha256_matches_rebased=h(seg_data) == ms["rebased_sha256"],
                )
            )

        kernel_span = kernel_end_va - virt_base
        check(
            "sweetxnu_payload_and_macho_segments",
            pmagic == b"SWEETXNU"
            and pver == 1
            and virt_base == KERNEL_VIRT_BASE
            and entry_va == KERNEL_ENTRY_VA
            and entry_va == macho["entry"]
            and pcmdline == CMDLINE
            and seg_checks_ok
            and 0 < kernel_span < WINDOW,
            version=pver,
            nsegs=pnsegs,
            virt_base=hex(virt_base),
            entry_va=hex(entry_va),
            kernel_end_va=hex(kernel_end_va),
            kernel_span_bytes=kernel_span,
            window_bytes=WINDOW,
            phys_base_template=hex(phys_base),
            mem_size_template=hex(mem_size),
            fixups_verified=macho["fixups_applied"],
            cmdline=pcmdline.decode("ascii", "replace"),
            segments_ok=seg_checks_ok,
        )

        adt_blob = pay[adt_off : adt_off + adt_size]
        try:
            adt_info = parse_adt_nodes(adt_blob)
            nodes = adt_info["nodes"]
            has_required = all(
                k in nodes
                for k in (
                    "/",
                    "/chosen",
                    "/chosen/memory-map",
                    "/cpus/cpu0",
                    "/arm-io",
                    "/arm-io/gic",
                    "/arm-io/wdt",
                    "/arm-io/disp0",
                    "/sweet-fbcon",
                )
            )
            no_apple_donor = "/product" not in nodes and "/device-tree/product" not in nodes
            check(
                "adt_synthesized_and_donor_free",
                adt_off + adt_size <= len(pay)
                and adt_info["end_offset"] == adt_size
                and has_required
                and no_apple_donor,
                adt_size=adt_size,
                adt_sha256=h(adt_blob),
                node_count=len(nodes),
                has_product_node=not no_apple_donor,
            )
        except Exception as exc:
            check("adt_synthesized_and_donor_free", False, error=str(exc))
    else:
        check("sweetxnu_payload_and_macho_segments", False, error="no SWEETXNU payload found")
        check("adt_synthesized_and_donor_free", False, error="no SWEETXNU payload found")

    # 6. Loader memory-window, framebuffer, and C object relocation checks
    loader_obj_dir = out_path.parent / "loader"
    c_objs = ["loader.c.o", "ui.c.o", "adt_patch.c.o", "gic.c.o", "fdt.c.o"]
    if loader_obj_dir.is_dir() and all((loader_obj_dir / o).is_file() for o in c_objs):
        c_abs_relocs = {}
        for o in c_objs:
            r_out = subprocess.run(["readelf", "-rW", str(loader_obj_dir / o)], capture_output=True, text=True, timeout=30).stdout
            abs_lines = [line.strip() for line in r_out.splitlines() if "R_AARCH64_ABS" in line]
            if abs_lines:
                c_abs_relocs[o] = abs_lines
        check("loader_no_c_abs64_relocations", not c_abs_relocs, c_objects=c_objs, abs_relocations=c_abs_relocs)
    else:
        check("loader_no_c_abs64_relocations", False, error=f"missing C object files in {loader_obj_dir}")

    loader_src = out_path.parent / "source/shim/e1s-xnu"
    harness_dir = out_path.parent / "window-check"
    if loader_src.is_dir():
        if harness_dir.exists():
            import shutil

            shutil.rmtree(harness_dir)
        proc = subprocess.run(
            [
                sys.executable,
                "-I",
                str(HERE / "check_loader.py"),
                "--loader-source",
                str(loader_src),
                "--dtb",
                str(dtb_path),
                "--out",
                str(harness_dir),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        wreport_path = harness_dir / "report.json"
        wreport = json.loads(wreport_path.read_text()) if wreport_path.exists() else {}
        scenarios = wreport.get("scenarios", {})
        all_scenarios_ok = (
            proc.returncode == 0
            and len(scenarios) == 3
            and all(
                s.get("exit_code") == 0
                and s.get("judgement", {}).get("ok") is True
                and s.get("result", {}).get("window", {}).get("base") == "0x9de400000"
                and s.get("result", {}).get("window", {}).get("size") == "0x20000000"
                and s.get("result", {}).get("framebuffer", {}).get("base") == "0xfa200000"
                and s.get("result", {}).get("framebuffer", {}).get("source") == 2
                for s in scenarios.values()
            )
        )
        check(
            "runtime_fdt_loader_window_and_framebuffer",
            all_scenarios_ok,
            report=str(wreport_path),
            scenarios={
                k: dict(
                    ok=v.get("judgement", {}).get("ok"),
                    window=v.get("result", {}).get("window"),
                    framebuffer=v.get("result", {}).get("framebuffer"),
                )
                for k, v in scenarios.items()
            },
        )
    else:
        check("runtime_fdt_loader_window_and_framebuffer", False, error=f"missing loader source dir {loader_src}")

    # 7. Restore package verification
    restore_img_path = restore_dir / "recovery.img"
    restore_tar_path = restore_dir / "recovery-stock-odin.tar"
    restore_sums_path = restore_dir / "SHA256SUMS"
    if restore_img_path.is_file() and restore_tar_path.is_file() and restore_sums_path.is_file():
        r_img = restore_img_path.read_bytes()
        r_tar = restore_tar_path.read_bytes()
        sums_text = restore_sums_path.read_text()
        with tarfile.open(restore_tar_path, "r") as tf:
            members = tf.getmembers()
            tar_member_bytes = tf.extractfile(members[0]).read() if len(members) == 1 and members[0].isfile() else b""
        expected_sums = f"{STOCK_SHA256}  recovery.img\n{h(r_tar)}  recovery-stock-odin.tar\n"
        check(
            "restore_package_exact_stock_match",
            r_img == stock
            and h(r_img) == STOCK_SHA256
            and len(members) == 1
            and members[0].name == "recovery.img"
            and tar_member_bytes == stock
            and sums_text == expected_sums,
            restore_image_sha256=h(r_img),
            odin_tar_sha256=h(r_tar),
            tar_member=members[0].name if members else None,
        )
    else:
        check("restore_package_exact_stock_match", False, error="missing files in restore directory")

    overall_ok = all(c["ok"] for c in checks)
    report = dict(
        schema_version=1,
        task="NAT-006",
        kind="host-test",
        ok=overall_ok,
        image=dict(path=str(image_path), size=len(img), sha256=h(img)),
        stock=dict(path=str(stock_path), size=len(stock), sha256=h(stock)),
        checks=checks,
        verified_vs_assumed=dict(
            verified_on_host=[
                "Header v2 fields (page_size=2048, os_version=0x1c000198, load addresses, cmdline, DTB, recovery_dtbo) match stock recovery.img",
                "Total image size is exactly 100,663,296 bytes (96 MiB RECOVERY partition) with SEANDROIDENFORCE trailer and AVB footer",
                "Patched E1S loader skips dynamic size-only /reserved-memory nodes and selects 0x9de400000+0x20000000 on the measured runtime FDT without overlapping any static reservation, 0xfa200000 framebuffer, or sec_debug_next",
                "SWEETXNU payload embeds all 10 non-empty STR-041 MH_EXECUTE segments (entry 0xfffffff00743b4a8) and a donor-free synthesized ADT",
                "Restore package (restore/recovery.img and restore/recovery-stock-odin.tar) reproduces the exact 100,663,296 stock RECOVERY bytes (SHA-256 96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67)",
            ],
            unverified_or_assumed=[
                "Whether S-Boot on SM-S921B/BYH3 accepts a modified RECOVERY image with an un-re-signed in-partition AVB0 hash descriptor when unlocked/orange",
                "Where S-Boot places the kernel, ramdisk, and DTB in physical RAM during a RECOVERY boot (only normal-boot placement was measured in NAT-005)",
                "Whether DECON/panel remains scanned out from 0xfa200000 in packed 32bpp (stride 4320) during RECOVERY entry without DPU power/clock teardown",
                "Whether XNU (STR-041) boots natively on Exynos S5E9945 hardware without faulting on unimplemented platform MMIO/interrupts",
            ],
        ),
    )
    out_path.write_text(json.dumps(report, indent=2) + "\n")
    return 0 if overall_ok else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--image", type=Path, required=True)
    p.add_argument("--stock", type=Path, required=True)
    p.add_argument("--kernel", type=Path, required=True)
    p.add_argument("--restore-dir", type=Path, required=True)
    p.add_argument("--dtb", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    return verify_all(a.image, a.stock, a.kernel, a.restore_dir, a.dtb, a.out)


if __name__ == "__main__":
    raise SystemExit(main())
