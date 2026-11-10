"""UI-007: read-only s5e9945 DECON0 boot-window reader on a simulated register file.

Register images are encoded by evaluating Samsung's own macro bodies (src/native/display/
register_facts.json, each checked here against the pinned source line it cites), never with the C
reader's constants. Expected results are written from the scenario, e.g. 1080 px * 4 B = 4320 B.
The harness maps every block read-only between guard pages, so a write or an out-of-range read by
the reader faults. ASan/UBSan are on. No device I/O.
"""
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src/native/display"
sys.path.insert(0, str(SRC))
import regfacts  # noqa: E402

FACTS = regfacts.load()
M = regfacts.Macros(FACTS)
DT_FACTS = json.loads((ROOT / "docs/procedures/ui-007/dpu-dt-facts.json").read_text())
HOST_CLANG = Path(os.environ.get("S24_HOST_CLANG", "/home/egor/.local/bin/clang"))
NDK_BIN = Path("/home/egor/Android/Sdk/ndk/28.2.13676358/toolchains/llvm/prebuilt/linux-x86_64/bin")

# Public API encoding of e1s_boot_window.h (status codes and result flags).
OK, ARGS, NO_WINDOW, MULTIPLE, UNSTABLE, NO_CHANNEL, LAYOUT, FORMAT, GEOMETRY = 0, 1, 2, 3, 4, 5, 6, 7, 8
DECON_OFF, TRANSLATED, UNKNOWN_TRANSLATION, BASE, SIZE, MODE, PIXEL = 20, 21, 22, 23, 24, 25, 26
F_ENABLED, F_RUNNING, F_CMD, F_EXPLICIT, F_BLOCK, F_COLORMAP, F_RSC, F_MMU_CHECKED, F_MMU_ON = (1 << i for i in range(9))
ALLOW_UNKNOWN_TRANSLATION = 1

FB_BASE, FB_SIZE, W, H = 0xFA200000, 0x9A4000, 1080, 2340  # NAT-005: bootarg base, 1080x2340 modes
GLOBAL_ON = M("GLOBAL_CON_DECON_EN") | M("GLOBAL_CON_DECON_EN_F") | M("GLOBAL_CON_OPERATION_MODE_CMD_F") | M("GLOBAL_CON_RUN_STATUS")


def rsc(owners: dict) -> tuple:
    """Two 32-bit RSC words: 4-bit owner per index, RSC_STATUS_IDLE elsewhere."""
    idle = M("RSC_STATUS_IDLE")
    value = 0
    for i in range(16):
        value |= owners.get(i, idle) << (4 * i)
    return value & 0xFFFFFFFF, value >> 32


def sboot(win=0, ch=0, fmt=None, **dma):
    """The expected S-Boot state: one full-panel ARGB8888 window at the bootarg base, MMU off."""
    regs = regfacts.RegisterFile(M).decon(GLOBAL_ON, rsc_ch=rsc({ch: 0}), rsc_win=rsc({win: 0}))
    regs.window(win, ch, 0, 0, W - 1, H - 1)
    args = dict(fmt=M("IDMA_IMG_FORMAT_ARGB8888") if fmt is None else fmt, base=FB_BASE,
                src_w=W, src_h=H, img_w=W, img_h=H)
    args.update(dma)
    regs.dma(ch, **args)
    regs.sysmmu(set())
    return regs


class BootWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not HOST_CLANG.exists():
            raise unittest.SkipTest("host clang with sanitizers required")
        cls.tmp = tempfile.TemporaryDirectory(prefix="s24-ui007-")
        cls.harness = Path(cls.tmp.name) / "harness"
        subprocess.run([str(HOST_CLANG), "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wpedantic", "-O1", "-g",
                        "-fno-omit-frame-pointer", "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                        str(SRC / "e1s_boot_window.c"), str(SRC / "sim_harness.c"), "-o", str(cls.harness)],
                       check=True, capture_output=True, text=True, timeout=60)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def harness_run(self, lines, expect_fault=False):
        env = {**os.environ, "ASAN_OPTIONS": "detect_leaks=1:halt_on_error=1",
               "UBSAN_OPTIONS": "halt_on_error=1:print_stacktrace=1"}
        r = subprocess.run([str(self.harness)], input="\n".join(lines) + "\n", capture_output=True,
                           text=True, env=env, timeout=120)
        if expect_fault:
            return r
        self.assertEqual(r.returncode, 0, r.stderr[-4000:])
        self.assertNotIn("runtime error", r.stderr)
        return [json.loads(x) for x in r.stdout.splitlines() if x.strip()]

    def one(self, regs, expect=None, vmid=3):
        lines = regs.script() + [f"vmid {vmid:#x}"]
        if expect:
            lines.append("expect {:#x} {:#x} {} {} {:#x}".format(*expect))
        return self.harness_run(lines + ["run case"])[0]

    # -- provenance ------------------------------------------------------------------------------
    def test_facts_match_pinned_s24_linux_source(self):
        repo = regfacts.find_reference(ROOT, "s24-linux")
        if repo is None:
            self.skipTest("references/s24-linux not checked out")
        rev = FACTS["sources"]["s24-linux"]["revision"]
        problems, checked = regfacts.verify(FACTS, repo, rev)
        if any("unavailable" in p for p in problems):
            self.skipTest("pinned blobs not fetched locally")
        self.assertEqual(problems, [])
        self.assertEqual(checked, len(FACTS["macros"]) + len(FACTS["statements"]))

    def test_dpu_facts_identical_in_bsp_reference(self):
        repo = regfacts.find_reference(ROOT, "s24-bsp-reference")
        if repo is None:
            self.skipTest("references/s24-bsp-reference not checked out")
        src = FACTS["sources"]["s24-bsp-reference"]
        problems, checked = regfacts.verify(FACTS, repo, src["revision"], src["line_overrides"], skip_unavailable=True)
        self.assertEqual(problems, [])
        dpu = sum(1 for k in ("macros", "statements") for e in FACTS[k] if "/samsung/dpu/" in e["file"])
        if checked < dpu:
            self.skipTest("DPU blobs of the BSP revision not fetched locally")

    def test_evaluator_reproduces_samsung_examples(self):
        # Hand-computed from the cited bodies, independent of the evaluator.
        self.assertEqual(M("WIN_START_POSITION", 3), 0x300C)
        self.assertEqual(M("DECON_CON_WIN", 15), 0xF000)
        self.assertEqual(M("WIN_CHMAP_F", 0x1F), 0xF0)
        self.assertEqual(M("WIN_ENDPTR_Y_F", 2339) | M("WIN_ENDPTR_X_F", 1079), (2339 << 16) | 1079)
        self.assertEqual(M("MMU_VM_ADDR", M("REG_MMU_CTRL_VM"), 1), 0x9000)
        self.assertEqual(M("CTRL_MMU_ENABLE"), 1)
        self.assertEqual(M("DMA_STRIDE_SEL"), 0x80000000)

    # -- the S-Boot case --------------------------------------------------------------------------
    def test_sboot_like_window_decodes_and_validates(self):
        r = self.one(sboot(), (FB_BASE, FB_SIZE, W, H, 0))
        self.assertEqual((r["status"], r["ret"], r["enabled"], r["window"], r["channel"]), (OK, OK, 1, 0, 0))
        self.assertEqual((r["base"], r["stride"], r["format"], r["bpp"]), (FB_BASE, 4320, 0, 4))
        self.assertEqual((r["width"], r["height"], r["src_width"], r["src_height"], r["src_x"], r["src_y"]), (W, H, W, H, 0, 0))
        self.assertEqual(r["win"], [0, 0, 1079, 2339])
        self.assertEqual(r["flags"], F_ENABLED | F_RUNNING | F_CMD | F_MMU_CHECKED)
        self.assertEqual((r["enabled_mask"], r["colormap_mask"], r["validate"]), (1, 0, OK))
        self.assertEqual(r["global_con"], GLOBAL_ON)

    def test_every_window_channel_pair_reads_the_mapped_dpp(self):
        lines = []
        for win in range(16):
            for ch in range(16):
                regs = sboot(win, ch, base=0x80000000 + (win << 20) + (ch << 12))
                lines += regs.script() + ["vmid 0x3", f"run w{win}c{ch}"]
        out = self.harness_run(lines)
        self.assertEqual(len(out), 256)
        for r in out:
            win, ch = map(int, r["label"][1:].split("c"))
            with self.subTest(win=win, ch=ch):
                self.assertEqual((r["status"], r["window"], r["channel"], r["enabled_mask"]), (OK, win, ch, 1 << win))
                self.assertEqual(r["base"], 0x80000000 + (win << 20) + (ch << 12))
                self.assertFalse(r["flags"] & F_RSC)

    def test_window_on_unmapped_channel_is_refused(self):
        regs = sboot(0, 3)
        del regs.regions["dma3"]
        self.assertEqual(self.one(regs)["status"], NO_CHANNEL)

    # -- formats, pitch and layout ----------------------------------------------------------------
    def test_xrgb_with_explicit_padded_stride(self):
        regs = sboot(fmt=M("IDMA_IMG_FORMAT_XRGB8888"), stride=4352)
        r = self.one(regs, (FB_BASE, FB_SIZE, W, H, 0))
        self.assertEqual((r["status"], r["stride"], r["format"], r["flags"] & F_EXPLICIT), (OK, 4352, 4, F_EXPLICIT))
        self.assertEqual(r["validate"], SIZE)  # 4352 * 2340 = 10183680 > 0x9A4000
        r = self.one(regs, (FB_BASE, 4352 * 2340, W, H, 0))
        self.assertEqual(r["validate"], OK)

    def test_explicit_stride_shorter_than_a_row_is_geometry_error(self):
        self.assertEqual(self.one(sboot(stride=4316))["status"], GEOMETRY)

    def test_byte_order_and_bpp_are_reported_not_assumed(self):
        r = self.one(sboot(fmt=M("IDMA_IMG_FORMAT_ABGR8888")), (FB_BASE, FB_SIZE, W, H, 0))
        self.assertEqual((r["status"], r["format"], r["bpp"], r["validate"]), (OK, 1, 4, PIXEL))
        r = self.one(sboot(fmt=M("IDMA_IMG_FORMAT_XBGR8888")), (FB_BASE, FB_SIZE, W, H, 0))
        self.assertEqual((r["format"], r["validate"]), (5, PIXEL))
        r = self.one(sboot(fmt=M("IDMA_IMG_FORMAT_RGB565")), (FB_BASE, FB_SIZE, W, H, 0))
        self.assertEqual((r["status"], r["bpp"], r["stride"], r["validate"]), (OK, 2, 2160, PIXEL))
        self.assertEqual(self.one(sboot(fmt=M("IDMA_IMG_FORMAT_NV12")))["status"], FORMAT)

    def test_compressed_rotated_or_cset_layouts_are_refused(self):
        for name in ("IDMA_SBWC_EN", "IDMA_AFBC_EN", "IDMA_CSET_EN", "IDMA_ROT_90", "IDMA_SBWC_LOSSY"):
            with self.subTest(bit=name):
                r = self.one(sboot(ctrl_extra=M(name)))
                self.assertEqual(r["status"], LAYOUT)
                self.assertEqual(r["in_ctrl"], M("IDMA_IMG_FORMAT", 0) | M(name))
        r = self.one(sboot(ctrl_extra=M("IDMA_BLOCK_EN")), (FB_BASE, FB_SIZE, W, H, 0))
        self.assertEqual((r["status"], r["flags"] & F_BLOCK, r["validate"]), (OK, F_BLOCK, OK))

    # -- window selection -------------------------------------------------------------------------
    def test_window_selection_rules(self):
        regs = regfacts.RegisterFile(M).decon(GLOBAL_ON)
        self.assertEqual(self.one(regs)["status"], NO_WINDOW)
        regs = sboot(2, 5)
        regs.window(7, 9, 0, 0, W - 1, H - 1)
        r = self.one(regs)
        self.assertEqual((r["status"], r["enabled_mask"]), (MULTIPLE, (1 << 2) | (1 << 7)))
        regs = sboot(4, 1)
        regs.window(0, 0, 0, 0, W - 1, H - 1, colormap=True)
        r = self.one(regs, (FB_BASE, FB_SIZE, W, H, 0))
        self.assertEqual((r["status"], r["window"], r["colormap_mask"], r["flags"] & F_COLORMAP, r["validate"]),
                         (OK, 4, 1, F_COLORMAP, OK))
        regs = regfacts.RegisterFile(M).decon(GLOBAL_ON).window(0, 0, 0, 0, W - 1, H - 1, colormap=True)
        self.assertEqual(self.one(regs)["status"], NO_WINDOW)
        regs = sboot(6, 2)
        regs.window(3, 3, 0, 0, W - 1, H - 1, enable=False)  # configured but WIN_EN clear
        self.assertEqual(self.one(regs)["enabled_mask"], 1 << 6)

    def test_register_and_shadow_disagreement_is_unstable(self):
        shadow_dma, shadow_decon = M("DMA_SHD_OFFSET"), M("SHADOW_OFFSET")
        cases = [("wincon", M("DECON_CON_WIN", 0) + shadow_decon),
                 ("win", M("WIN_START_POSITION", 0) + shadow_decon),
                 ("win", M("WIN_END_POSITION", 0) + shadow_decon)]
        cases += [("dma0", M(reg) + shadow_dma) for reg in ("RDMA_IN_CTRL_0", "RDMA_SRC_WIDTH", "RDMA_SRC_HEIGHT",
                                                           "RDMA_SRC_OFFSET", "RDMA_IMG_SIZE", "DMA_BASEADDR_P0",
                                                           "DMA_SRC_STRIDE_0")]
        for region, offset in cases:
            with self.subTest(region=region, offset=hex(offset)):
                regs = sboot()
                regs.put(region, offset, regs.regions[region][1].get(offset, 0) ^ 0x10)
                self.assertEqual(self.one(regs)["status"], UNSTABLE)

    def test_rsc_owner_mismatch_is_reported_only(self):
        regs = sboot(1, 4)
        regs.decon(GLOBAL_ON, rsc_ch=rsc({4: 1}), rsc_win=rsc({1: 0}))
        r = self.one(regs, (FB_BASE, FB_SIZE, W, H, 0))
        self.assertEqual((r["status"], r["flags"] & F_RSC, r["validate"]), (OK, F_RSC, OK))
        regs.decon(GLOBAL_ON, rsc_ch=rsc({4: 0}), rsc_win=rsc({}))  # window owner idle
        self.assertTrue(self.one(regs)["flags"] & F_RSC)

    # -- validation -------------------------------------------------------------------------------
    def test_sysmmu_translation_state(self):
        for vms, mask, want in [({0}, 3, TRANSLATED), ({1}, 3, TRANSLATED), ({1}, 1, OK), (set(), 3, OK)]:
            with self.subTest(vms=vms, mask=mask):
                regs = sboot()
                regs.sysmmu(vms)  # overwrites both VM control words
                r = self.one(regs, (FB_BASE, FB_SIZE, W, H, 0), vmid=mask)
                self.assertEqual(r["validate"], want)
                self.assertEqual(bool(r["flags"] & F_MMU_ON), want == TRANSLATED)
        regs = sboot()
        del regs.regions["sysmmu"]
        r = self.one(regs, (FB_BASE, FB_SIZE, W, H, 0))
        self.assertEqual((r["status"], r["flags"] & F_MMU_CHECKED, r["validate"]), (OK, 0, UNKNOWN_TRANSLATION))
        r = self.one(regs, (FB_BASE, FB_SIZE, W, H, ALLOW_UNKNOWN_TRANSLATION))
        self.assertEqual(r["validate"], OK)

    def test_validation_rejections(self):
        r = self.one(sboot().decon(0), (FB_BASE, FB_SIZE, W, H, 0))
        self.assertEqual((r["status"], r["flags"] & F_ENABLED, r["validate"]), (OK, 0, DECON_OFF))
        self.assertEqual(self.one(sboot(), (FB_BASE + 0x1000, FB_SIZE, W, H, 0))["validate"], BASE)
        self.assertEqual(self.one(sboot(), (FB_BASE, FB_SIZE - 4, W, H, 0))["validate"], SIZE)
        self.assertEqual(self.one(sboot(), (FB_BASE, 0, W, H, 0))["validate"], SIZE)
        self.assertEqual(self.one(sboot(), (FB_BASE, FB_SIZE, 1440, 3120, 0))["validate"], MODE)
        crop = sboot(img_w=W - 8, x=8)
        self.assertEqual(self.one(crop, (FB_BASE, FB_SIZE, W, H, 0))["validate"], MODE)
        small = sboot()
        small.window(0, 0, 0, 0, W - 1, H - 2)
        self.assertEqual(self.one(small, (FB_BASE, FB_SIZE, W, H, 0))["validate"], MODE)
        r = self.one(sboot(), (FB_BASE, FB_SIZE, 0, H, 0))
        self.assertEqual(r["validate"], ARGS)

    def test_geometry_errors(self):
        for kw in (dict(img_w=0), dict(img_h=0), dict(src_w=0), dict(img_w=W, x=1), dict(img_h=H, y=1),
                   dict(src_h=H - 1)):
            with self.subTest(**kw):
                self.assertEqual(self.one(sboot(**kw))["status"], GEOMETRY)
        inverted = sboot()
        inverted.window(0, 0, 100, 0, 99, H - 1)
        self.assertEqual(self.one(inverted)["status"], GEOMETRY)

    def test_missing_decon_bases_are_argument_errors(self):
        for name in ("main", "win", "wincon"):
            with self.subTest(missing=name):
                regs = sboot()
                del regs.regions[name]
                self.assertEqual(self.one(regs)["status"], ARGS)

    def test_randomised_dma_decode_against_cited_masks(self):
        rng = random.Random(0x19100000)
        bpp = format_bpp_from_source()
        lines, want = [], {}
        layout_bits = [M(n) for n in ("IDMA_SBWC_EN", "IDMA_AFBC_EN", "IDMA_CSET_EN", "IDMA_ROT_90", "IDMA_SBWC_LOSSY")]
        for i in range(400):
            fmt = rng.choice(sorted(bpp) + [rng.randrange(64)])
            extra = rng.choice([0, 0, 0, rng.choice(layout_bits), M("IDMA_BLOCK_EN")])
            sw, sh = rng.randrange(1, 4097), rng.randrange(1, 4097)
            x, y = rng.randrange(0, 64), rng.randrange(0, 64)
            iw, ih = rng.randrange(0, sw + 2), rng.randrange(0, sh + 2)
            stride = rng.choice([0, 0, rng.randrange(1, 1 << 20)])
            base = rng.getrandbits(32)
            regs = sboot(fmt=fmt, base=base, src_w=sw, src_h=sh, img_w=iw, img_h=ih, x=x, y=y, stride=stride,
                         ctrl_extra=extra)
            lines += regs.script() + ["vmid 0x3", f"run r{i}"]
            b = bpp.get(fmt, 0)
            if extra and extra != M("IDMA_BLOCK_EN"):
                want[i] = (LAYOUT,)
            elif not b:
                want[i] = (FORMAT,)
            elif not iw or not ih or x + iw > sw or y + ih > sh:
                want[i] = (GEOMETRY,)
            elif stride and stride < sw * b:
                want[i] = (GEOMETRY,)
            else:
                want[i] = (OK, base, stride or sw * b, b, iw, ih, x, y)
        for r in self.harness_run(lines):
            i = int(r["label"][1:])
            got = (r["status"],) if want[i][0] != OK else (r["status"], r["base"], r["stride"], r["bpp"],
                                                           r["width"], r["height"], r["src_x"], r["src_y"])
            self.assertEqual(got, want[i], f"case {i}")

    # -- read-only proof and target build ---------------------------------------------------------
    def test_harness_faults_on_write_and_out_of_range_read(self):
        # Shows that the guard used by every case above would catch a write or overrun.
        for cmd in ("poke main 0x20", "peek-past dma0"):
            with self.subTest(cmd=cmd):
                r = self.harness_run(sboot().script() + [cmd], expect_fault=True)
                self.assertNotEqual(r.returncode, 0)
                self.assertNotIn("not-faulted", r.stdout)
                self.assertTrue(r.returncode < 0 or "SEGV" in r.stderr, r.stderr[-2000:])

    def test_freestanding_aarch64_build_with_loader_flags(self):
        # Flags of references/s24-port shim/e1s-xnu/build.sh plus -Werror.
        with tempfile.TemporaryDirectory() as tmp:
            obj = Path(tmp) / "bw.o"
            subprocess.run([str(HOST_CLANG), "--target=aarch64-none-elf", "-std=c11", "-O2", "-ffreestanding",
                            "-nostdlib", "-fno-pic", "-mgeneral-regs-only", "-mstrict-align", "-fno-stack-protector",
                            "-Wall", "-Wextra", "-Werror", "-Wpedantic", "-c", str(SRC / "e1s_boot_window.c"),
                            "-o", str(obj)], check=True, capture_output=True, text=True, timeout=60)
            nm = NDK_BIN / "llvm-nm"
            if not nm.exists():
                self.skipTest("llvm-nm unavailable for the undefined-symbol check")
            undefined = subprocess.run([str(nm), "-u", str(obj)], check=True, capture_output=True, text=True).stdout
            self.assertEqual(undefined.strip(), "", "module must not call libc (memset/memcpy) or anything else")
            defined = subprocess.run([str(nm), "--defined-only", str(obj)], check=True, capture_output=True, text=True).stdout
            for sym in ("e1s_boot_window_read", "e1s_boot_window_validate", "e1s_dpu_mmio_default"):
                self.assertIn(sym, defined)

    # -- MMIO bases come from the runtime FDT -----------------------------------------------------
    def test_default_layout_matches_runtime_fdt_facts(self):
        layout = self.harness_run(["layout"])[0]
        decon0 = next(d for d in DT_FACTS["decon"] if d["decon,id"] == 0)
        regs = {r["name"]: int(r["base"], 16) for r in decon0["reg"]}
        self.assertEqual((layout["decon_main"], layout["decon_win"], layout["decon_wincon"]),
                         (regs["main"], regs["win"], regs["wincon"]))
        self.assertEqual(decon0["op_mode"], 1)
        chans = DT_FACTS["dpp_dma_by_channel"]
        self.assertEqual(layout["dpp_dma"], [int(chans[str(i)], 16) for i in range(16)])
        mmu_paths = {p for d in DT_FACTS["dpp"] if d.get("dpp,id", 99) < 16 for p in d.get("iommus", [])}
        self.assertEqual(len(mmu_paths), 1)
        mmu = next(s for s in DT_FACTS["sysmmu"] if s["path"] in mmu_paths)
        self.assertEqual((layout["sysmmu"], layout["sysmmu_vmid_mask"]), (int(mmu["reg"][0]["base"], 16), mmu["vmid_mask"]))
        self.assertGreaterEqual(int(mmu["reg"][0]["size"], 16), M("MMU_VM_ADDR", M("REG_MMU_CTRL_VM"), 1) + 4)
        dsim0 = next(d for d in DT_FACTS["dsim"] if d["dsim,id"] == 0)
        self.assertFalse(dsim0["has_memory_region"] or dsim0["has_lk_fb_win_id"])  # no Linux FB handover in DT
        self.assertEqual([c["kind"] for c in DT_FACTS["boot_framebuffer"]["covered_by"]], ["memory"])

    def test_committed_dt_facts_regenerate_from_local_blob(self):
        primary = regfacts.find_reference(ROOT, "s24-linux")
        candidates = [ROOT / "devices/e1s-fdt/2026-11-10/runtime.dtb"]
        if primary is not None:
            candidates.append(primary.parents[1] / "devices/e1s-fdt/2026-11-10/runtime.dtb")
        blob = next((p for p in candidates if p.exists()), None)
        if blob is None:
            self.skipTest("private runtime FDT not present on this host")
        data = blob.read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), DT_FACTS["fdt_sha256"])
        import dpu_dt_facts
        self.assertEqual(dpu_dt_facts.facts(data, FB_BASE), DT_FACTS)


def format_bpp_from_source():
    """Bytes per pixel by IDMA_IMG_FORMAT name in the pinned regs-dpp.h (fallback: cited subset)."""
    names = {}
    repo = regfacts.find_reference(ROOT, "s24-linux")
    text = regfacts.source_text(repo, FACTS["sources"]["s24-linux"]["revision"],
                                "drivers/gpu/drm/samsung/dpu/cal_rt/regs-dpp.h") if repo else None
    if text:
        for name, code in re.findall(r"#define\s+IDMA_IMG_FORMAT_(\w+)\s+\((\d+)\)", text):
            names[name] = int(code)
    else:
        names = {m["name"][len("IDMA_IMG_FORMAT_"):]: M(m["name"]) for m in FACTS["macros"]
                 if m["name"].startswith("IDMA_IMG_FORMAT_") and m["name"] != "IDMA_IMG_FORMAT_MASK"}
    out = {}
    for name, code in names.items():
        if re.fullmatch(r"[ARGBX]{4}8888", name):
            out[code] = 4
        elif re.fullmatch(r"(RGB|BGR)565", name):
            out[code] = 2
        elif re.fullmatch(r"[ARGB]{4}(2101010|1010102)", name):
            out[code] = 4
        elif re.fullmatch(r"[ARGB]{4}_FP16(_HDR)?", name):
            out[code] = 8
    return out


if __name__ == "__main__":
    unittest.main()
