"""DRV-007: run the read-only UFS host and GPT contract checks from make check (host only).

- The source-qualified UFS host check (src/platform/storage/ufs/check.py) runs in full: pinned
  Samsung sources, donor builder differential, sanitizer controls and ARM64 compile.
- The GPT admission tests (gpt_test.c) build and run under ASan/UBSan. The slower 72-mutant run
  stays an explicit command: python3 src/platform/storage/ufs/gpt_check.py --run NAME.
- An exact-status program pins the DRV-002 boundaries (DMA, LUN, extent, timeouts, writes). Its
  expected values come from the public enum in host.h and the scenario numbers, not from host.c.

No phone, MMIO or storage access.
"""
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UFS = ROOT / "src/platform/storage/ufs"
CLANG = Path(os.environ.get("S24_HOST_CLANG", "/home/egor/.local/bin/clang"))
SAN = ["-std=c11", "-Wall", "-Wextra", "-Werror", "-Wpedantic", "-O1", "-g", "-fno-omit-frame-pointer",
       "-fsanitize=address,undefined", "-fno-sanitize-recover=all"]
SAN_ENV = {**os.environ, "ASAN_OPTIONS": "detect_leaks=1:halt_on_error=1",
           "UBSAN_OPTIONS": "halt_on_error=1:print_stacktrace=1"}

# Public API of host.h, written out here so the program below is checked against the header text.
ENUM = ["UFS_OK", "UFS_ARGUMENT", "UFS_LENGTH", "UFS_WRITE_REJECTED", "UFS_COMMAND", "UFS_EXTENT",
        "UFS_DMA_RANGE", "UFS_BUSY", "UFS_STALE", "UFS_FORMAT", "UFS_STATUS", "UFS_TIMEOUT", "UFS_CLOCK",
        "UFS_EXHAUSTED", "UFS_OWNERSHIP"]

EXACT = r"""
#include "host.h"
#include <stdio.h>
#include <string.h>
static int fails;
#define EQ(got, want) do { unsigned g_ = (unsigned)(got), w_ = (unsigned)(want); \
    if (g_ != w_) { printf("FAIL line %d: got %u want %u\n", __LINE__, g_, w_); fails++; } } while (0)
/* Scenario: LUN of 1,000,000 4 KiB blocks, extent [100, 900100), UCD at a 128-aligned address,
   data buffer after it. */
static struct ufs_policy base(void)
{
    struct ufs_policy p;
    memset(&p, 0, sizeof p);
    p.lun_blocks = 1000000; p.first_block = 100; p.extent_blocks = 900000;
    p.ucd_dma = 0x10000000; p.ucd_bytes = 1088; p.data_dma = 0x20000000; p.data_bytes = 1048576;
    p.block_bytes = 4096; p.lun = 0; p.sqid = 0; p.epoch = 7;
    return p;
}
static void read10(uint8_t *c, uint32_t lba, uint16_t blocks)
{
    memset(c, 0, 10); c[0] = 0x28;
    c[2] = (uint8_t)(lba >> 24); c[3] = (uint8_t)(lba >> 16); c[4] = (uint8_t)(lba >> 8); c[5] = (uint8_t)lba;
    c[7] = (uint8_t)(blocks >> 8); c[8] = (uint8_t)blocks;
}
static unsigned init_with(struct ufs_policy p)
{
    struct ufs_host h;
    memset(&h, 0xA5, sizeof h);
    unsigned r = ufs_host_init(&h, &p);
    if (r) { /* a refused policy leaves no state behind */
        EQ(h.phase, UFS_IDLE); EQ(h.policy.lun_blocks, 0); EQ(h.token.epoch, 0);
    }
    return r;
}
int main(void)
{
    struct ufs_host h;
    struct ufs_policy p;
    uint8_t c[10];

    /* LUN and extent boundaries */
    EQ(init_with(base()), UFS_OK);
    p = base(); p.lun = 127; EQ(init_with(p), UFS_OK);
    p = base(); p.lun = 128; EQ(init_with(p), UFS_ARGUMENT);
    p = base(); p.sqid = 31; EQ(init_with(p), UFS_OK);
    p = base(); p.sqid = 32; EQ(init_with(p), UFS_ARGUMENT);
    p = base(); p.epoch = 0; EQ(init_with(p), UFS_ARGUMENT);
    p = base(); p.block_bytes = 512; EQ(init_with(p), UFS_OK);
    p = base(); p.block_bytes = 1024; EQ(init_with(p), UFS_ARGUMENT);
    p = base(); p.first_block = 1000000; EQ(init_with(p), UFS_ARGUMENT);
    p = base(); p.extent_blocks = 999900; EQ(init_with(p), UFS_OK);      /* ends on the last block */
    p = base(); p.extent_blocks = 999901; EQ(init_with(p), UFS_ARGUMENT); /* one past the LUN */

    /* DMA boundaries */
    p = base(); p.ucd_dma += 64; EQ(init_with(p), UFS_DMA_RANGE);         /* not 128-aligned */
    p = base(); p.data_dma += 2; EQ(init_with(p), UFS_DMA_RANGE);         /* not 4-aligned */
    p = base(); p.ucd_bytes = 1087; EQ(init_with(p), UFS_DMA_RANGE);
    p = base(); p.data_bytes = 1048575; EQ(init_with(p), UFS_DMA_RANGE);
    p = base(); p.data_dma = p.ucd_dma + 1084; EQ(init_with(p), UFS_DMA_RANGE); /* 4-byte overlap */
    p = base(); p.data_dma = p.ucd_dma + 1088; EQ(init_with(p), UFS_OK);        /* adjacent, disjoint */
    p = base(); p.ucd_dma = UINT64_C(0xFFFFFFFFFFFFFF80); EQ(init_with(p), UFS_DMA_RANGE); /* wraps */
    p = base(); p.data_bytes = UINT64_MAX; EQ(init_with(p), UFS_DMA_RANGE);
    p = base(); p.ucd_dma = 0; EQ(init_with(p), UFS_DMA_RANGE);

    /* READ(10) admission against the extent */
    p = base(); EQ(ufs_host_init(&h, &p), UFS_OK);
    read10(c, 99, 1); EQ(ufs_host_prepare(&h, c, 10, UFS_FROM_DEVICE, 4096), UFS_EXTENT);       /* before */
    read10(c, 900100, 1); EQ(ufs_host_prepare(&h, c, 10, UFS_FROM_DEVICE, 4096), UFS_EXTENT);   /* after */
    read10(c, 900099, 2); EQ(ufs_host_prepare(&h, c, 10, UFS_FROM_DEVICE, 8192), UFS_EXTENT);   /* crosses */
    read10(c, 100, 1); EQ(ufs_host_prepare(&h, c, 10, UFS_FROM_DEVICE, 4095), UFS_EXTENT);      /* size */
    EQ(h.phase, UFS_IDLE);

    /* Writes are refused before anything else is looked at */
    memset(c, 0, 10); c[0] = 0x2A; c[5] = 100; c[8] = 1;                                       /* WRITE(10) */
    EQ(ufs_host_prepare(&h, c, 10, UFS_TO_DEVICE, 4096), UFS_WRITE_REJECTED);
    EQ(ufs_host_prepare(&h, c, 10, 0, 4096), UFS_WRITE_REJECTED);
    EQ(ufs_host_prepare(&h, c, 10, UFS_FROM_DEVICE, 4096), UFS_COMMAND);
    read10(c, 100, 1); EQ(ufs_host_prepare(&h, c, 10, UFS_TO_DEVICE, 4096), UFS_WRITE_REJECTED);
    EQ(h.phase, UFS_IDLE);

    /* Last block of the extent is admitted; then the timeout lifecycle */
    read10(c, 900099, 1); EQ(ufs_host_prepare(&h, c, 10, UFS_FROM_DEVICE, 4096), UFS_OK);
    EQ(h.phase, UFS_PREPARED);
    {
        struct ufs_token t = h.token;
        EQ(ufs_host_reserve_device(&h, &t, 1000, 0), UFS_CLOCK);                     /* no timeout */
        EQ(ufs_host_reserve_device(&h, &t, 1000, UFS_TIMEOUT_MAX_NS + 1), UFS_CLOCK);  /* > 5 s */
        EQ(ufs_host_reserve_device(&h, &t, 0, 100), UFS_CLOCK);                       /* no clock */
        EQ(h.phase, UFS_PREPARED);
        EQ(ufs_host_reserve_device(&h, &t, 1000, UFS_TIMEOUT_MAX_NS), UFS_OK);
        EQ(h.phase, UFS_DEVICE_OWNED);
        EQ(ufs_host_poll_timeout(&h, 1000 + UFS_TIMEOUT_MAX_NS - 1), UFS_OK);
        EQ(ufs_host_poll_timeout(&h, 1000 + UFS_TIMEOUT_MAX_NS), UFS_TIMEOUT);
        EQ(h.phase, UFS_QUARANTINED);
        EQ(ufs_host_reclaim(&h, &t), UFS_OWNERSHIP);  /* a timed-out request is never reclaimed */
        read10(c, 100, 1); EQ(ufs_host_prepare(&h, c, 10, UFS_FROM_DEVICE, 4096), UFS_BUSY);
    }
    printf("{\"outcome\":\"%s\",\"failures\":%d}\n", fails ? "fail" : "pass", fails);
    return fails != 0;
}
"""


def have_clang():
    return CLANG.exists()


class UfsContractTests(unittest.TestCase):
    def test_header_enum_matches_this_test(self):
        header = (UFS / "host.h").read_text()
        body = header.split("enum ufs_result {", 1)[1].split("};", 1)[0]
        names = [n.split("=")[0].strip() for n in body.replace("\n", " ").split(",") if n.strip()]
        self.assertEqual(names, ENUM)
        self.assertIn("UFS_OK=0", body.replace(" ", ""))

    @unittest.skipUnless(have_clang(), "host clang with sanitizers required")
    def test_exact_boundary_statuses_under_sanitizers(self):
        with tempfile.TemporaryDirectory(prefix="s24-drv007-") as tmp:
            src = Path(tmp) / "exact.c"
            src.write_text(EXACT)
            exe = Path(tmp) / "exact"
            subprocess.run([str(CLANG), *SAN, "-I", str(UFS), str(UFS / "host.c"), str(src), "-o", str(exe)],
                           check=True, capture_output=True, text=True, timeout=120)
            r = subprocess.run([str(exe)], capture_output=True, text=True, env=SAN_ENV, timeout=60)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr[-3000:])
            self.assertEqual(json.loads(r.stdout.splitlines()[-1]), {"outcome": "pass", "failures": 0})

    @unittest.skipUnless(have_clang(), "host clang with sanitizers required")
    def test_gpt_admission_suite_under_sanitizers(self):
        with tempfile.TemporaryDirectory(prefix="s24-drv007-gpt-") as tmp:
            exe = Path(tmp) / "gpt-asan"
            subprocess.run([str(CLANG), *SAN, str(UFS / "gpt.c"), str(UFS / "host.c"), str(UFS / "gpt_test.c"),
                            "-I", str(UFS), "-o", str(exe)], check=True, capture_output=True, text=True, timeout=120)
            r = subprocess.run([str(exe)], capture_output=True, text=True, env=SAN_ENV, timeout=60)
            self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-3000:])
            result = json.loads(r.stdout.splitlines()[-1])
            self.assertEqual(result["outcome"], "pass")
            self.assertEqual(result["tests"], 14)

    def test_source_qualified_ufs_host_check(self):
        needed = [ROOT / "references/s24-linux/.git", ROOT / "references/s24-port/.git"]
        if not all(p.exists() for p in needed) or not have_clang():
            self.skipTest("pinned s24-linux/s24-port references and host clang required (primary checkout)")
        run = f"ut-{os.getpid()}-{int(time.time() * 1000)}"
        out = ROOT / "artifacts/ufs-host" / run
        try:
            r = subprocess.run(["python3", str(UFS / "check.py"), "--run", run], cwd=ROOT,
                               capture_output=True, text=True, timeout=300)
            evidence = json.loads((out / "evidence.json").read_text())
            self.assertEqual(r.returncode, 0, json.dumps(evidence.get("error")))
            self.assertEqual(evidence["outcome"], "pass")
            self.assertEqual(len(evidence["checks"]), 22)
            self.assertTrue(all(c["pass_check"] for c in evidence["checks"]))
            res = evidence["result"]
            self.assertEqual((res["donor_cases"], res["mcq_tag_cases"], res["guard_lengths"],
                              res["random_completions"], res["hardware_io"]), (56, 2048, 94, 100000, False))
            self.assertFalse(evidence["device_executed"] or evidence["native_qualified"]
                             or evidence["userdata_decryption_qualified"])
        finally:
            shutil.rmtree(out, ignore_errors=True)  # created by this test only


if __name__ == "__main__":
    unittest.main()
