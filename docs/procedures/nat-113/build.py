#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-113 host build: `loader-diag-xnu-sc3-md1` (Stage C3: NAT-110's image + pixel evidence at the kernel's return).

Drives NAT-106's chain (as NAT-110 does) without opening a phone or modifying earlier procedures:
  1. `--ramdisk` pins NAT-110's `pid1-sc2-hb/root.apfs` unchanged (396 files: etc/quiet, 377 LaunchDaemons);
  2. `glue62_impl.h` keeps NAT-106's rules (BURST=4096u, TAIL_RETURN=524288u, 10x settle waits) plus two NAT-113 rules that include
     src/glue113.h and call nat113_pixels() at the kernel's own return, before the KL dump: a PX report of the panel memory the
     display DMA scans (summary + 108x234 RGB332 thumbnail) and a PR report of the kernel's screen recording (per-frame stats);
  3. kernel command line relative to NAT-110: `keepsyms=1` dropped from NAT-020's base line, `fb_diff=1` not added,
     `rec_secs=30 rec_mb=64` added (MiniIOMobileFramebuffer recording, RWREC003, 375x812 RGB frames, about 73 fit);
     `loader_return_after=63` unchanged; checked < 256 B;
  4. `--deadline-s 390` (rx_cap 240 + return_after 63 + 60 + 25 for the pixel report).

Watchdog: this loader arms the S5E9945 watchdog for 83 s (guard.c) and pets it for the last time before the jump
(nat074_final_pet); nothing feeds it while the kernel runs (no S5E9945 code in the kernel tree; hv_wdt_pet is a Qualcomm hypervisor
call). A kernel window longer than 63 s ends in the watchdog's SEC_UPLOAD before loader_return, losing the log: hence 63, not 120.
"""
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent

NAME = "loader-diag-xnu-sc3-md1"
NEW_TAG = "nat_attempt=NAT113-sc3"
MD0_BYTES = 4194304
MD0_SHA256 = "6e9bdcef4ed6d4cd592ae004f1ec84013326242472be6f27074d5364a495583c"
BURST_NEW = 4096
TAIL_RETURN_NEW = 524288
RETURN_SETTLE_WAITS = 10
RETURN_AFTER_NEW = 63      # NAT-079 rule [8, 63]: the S5E9945 watchdog (83 s) is NOT fed after the jump on this loader
DEADLINE_NEW = 390         # >= rx_cap 240 + return_after 63 + work 60 + pixel report 25 = 388
REC_TOKENS = ("rec_secs=30", "rec_mb=64")
DROP_BASE_TOKENS = ("keepsyms=1",)   # serial=3 stays: kprintf reaches loader_log through serial_putc_crlf (redwood.patch)
# NAT-067's APPEND plus the recording tokens; ` loader_return_after=8` stays as NAT-079's placeholder.
APPEND_NEW = (" loader_return_after=8 launchdsuffix=release cs_enforcement_disable=1 e1stouch=0 e1sbattery=0 "
              + " ".join(REC_TOKENS))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


b106 = _load("nat113_nat106_build", PROC / "nat-106" / "build.py")
b104 = b106.b104
b79 = b104.b102.b87.b85.b79
b67 = b79.b67
b65 = b79.b65  # the instance the NAT-074..087 chain patches (b67.b65 is a separate copy)
sha = b106.sha
argv_value = b106.argv_value


def drop_base_tokens(cmdline):
    """Remove each of DROP_BASE_TOKENS exactly once from NAT-020's base command line."""
    tokens = cmdline.split(" ")
    for t in DROP_BASE_TOKENS:
        if tokens.count(t) != 1:
            raise SystemExit("expected %s exactly once in the base command line: %r" % (t, cmdline))
        tokens.remove(t)
    return " ".join(tokens)


def drop_base_tokens_field(field):
    """The NUL-padded NAT-020 command-line field with DROP_BASE_TOKENS removed, padded back to its length."""
    text = field.rstrip(b"\0").decode("ascii")
    new = drop_base_tokens(text).encode("ascii")
    return new + b"\0" * (len(field) - len(new))


def check_cmdline(cmdline):
    """The final line carries the NAT-113 tokens once, none of the dropped ones, and fits BOOT_LINE_LENGTH."""
    tokens = cmdline.split()
    need = [NEW_TAG, "loader_return_after=%d" % RETURN_AFTER_NEW, "cpus=1", "rd=md1", "xrd=md0"] + list(REC_TOKENS)
    for t in need:
        if tokens.count(t) != 1:
            raise SystemExit("cmdline must contain %s exactly once: %r" % (t, cmdline))
    for t in DROP_BASE_TOKENS + ("fb_diff=1",):
        if t in tokens:
            raise SystemExit("cmdline must not contain %s: %r" % (t, cmdline))
    if len(cmdline.encode()) >= 256:
        raise SystemExit("cmdline exceeds 255 bytes (%d): %r" % (len(cmdline.encode()), cmdline))


def with_default_timings(argv):
    out = list(argv)
    if "--return-after-s" not in out:
        out += ["--return-after-s", str(RETURN_AFTER_NEW)]
    if "--deadline-s" not in out:
        out += ["--deadline-s", str(DEADLINE_NEW)]
    return out


FIELDS = ("NAME", "NEW_TAG", "MD0_BYTES", "MD0_SHA256", "BURST_NEW", "TAIL_RETURN_NEW", "RETURN_SETTLE_WAITS")
VALUES = (NAME, NEW_TAG, MD0_BYTES, MD0_SHA256, BURST_NEW, TAIL_RETURN_NEW, RETURN_SETTLE_WAITS)
GLUE113 = HERE / "src" / "glue113.h"
# Extra exact-match rules over the derived tree's glue62_impl.h (applied after NAT-104/106's three, each must match once):
# the pixel report is sent at the kernel's own return, after the settle waits and before the KL begin record.
PATCH_RULES_113 = (
    ("include113",
     "void nat062_dump_log(uint64_t x0, uint64_t x1, uint64_t pa_minus_va, uint32_t why)\n{",
     "#include \"glue113.h\"\n\nvoid nat062_dump_log(uint64_t x0, uint64_t x1, uint64_t pa_minus_va, uint32_t why)\n{"),
    ("pixels113",
     "\t\tfor (uint32_t w = 0; w < 10u; w++)\n\t\t\tN62_WAIT();\n\t}\n\tN62_EMIT(b, p);",
     "\t\tfor (uint32_t w = 0; w < 10u; w++)\n\t\t\tN62_WAIT();\n\t\tnat113_pixels(pa_minus_va);\n\t}\n\tN62_EMIT(b, p);"),
)
STATE = {}


def main():
    argv_saved = list(sys.argv)
    sys.argv = with_default_timings(argv_saved)
    saved = tuple(getattr(b106, f) for f in FIELDS)
    saved_append, saved_make = b67.APPEND, b65.make_cmdline
    saved_rules, saved_patch = b106.PATCH_RULES, b104.patch_glue104

    def patch_glue113(path):
        dst = Path(path).parent / "glue113.h"
        dst.write_bytes(GLUE113.read_bytes())
        STATE["glue113_sha256"] = sha(GLUE113.read_bytes())
        return saved_patch(path)

    for f, v in zip(FIELDS, VALUES):
        setattr(b106, f, v)
    b67.APPEND = APPEND_NEW
    b65.make_cmdline = lambda field: saved_make(drop_base_tokens_field(field))
    b106.PATCH_RULES = tuple(saved_rules) + PATCH_RULES_113
    b104.patch_glue104 = patch_glue113
    try:
        b106.main()
    finally:
        sys.argv = argv_saved
        for f, v in zip(FIELDS, saved):
            setattr(b106, f, v)
        b67.APPEND, b65.make_cmdline = saved_append, saved_make
        b106.PATCH_RULES, b104.patch_glue104 = saved_rules, saved_patch

    if "--check-only" in argv_saved:
        return
    out = argv_value(argv_saved, "--out")
    if out is None:
        return
    rec = Path(out) / "build.json"
    d = json.loads(rec.read_text())
    d.pop("nat106_sources", None)
    changes = d.pop("nat106_changes", {})
    d.pop("nat106_note", None)
    cmdline = changes.get("cmdline") or ""
    check_cmdline(cmdline)
    if "glue113_sha256" not in STATE:
        raise SystemExit("the glue113 hook never ran during prepare_tree")
    d["nat113_sources"] = {"build.py": sha((HERE / "build.py").read_bytes()), "src/glue113.h": STATE["glue113_sha256"]}
    d["nat113_changes"] = {
        "image_name": NAME, "cmdline_tag": NEW_TAG,
        "md0_sha256": changes.get("md0_sha256"), "md0_bytes": changes.get("md0_bytes"),
        "cmdline": cmdline, "cmdline_bytes": len(cmdline.encode()),
        "rec_secs": 30, "rec_mb": 64, "rec_ring": 0,
        "return_after_s": RETURN_AFTER_NEW, "deadline_s": DEADLINE_NEW,
        "dropped_base_tokens": list(DROP_BASE_TOKENS), "fb_diff": 0,
        "glue62_impl_sha256": changes.get("glue62_impl_sha256"),
        "burst_bytes": BURST_NEW, "tail_return_bytes": TAIL_RETURN_NEW, "return_settle_waits": RETURN_SETTLE_WAITS,
    }
    d["nat113_note"] = ("NAT-110's image with screen recording (rec_secs=30 rec_mb=64) and the loader's PX/PR pixel report at the kernel's "
                        "return; loader_return_after=63, deadline_s=390, keepsyms=1/fb_diff=1 dropped; nothing ran on a phone")
    rec.write_text(json.dumps(d, indent=1))


if __name__ == "__main__":
    main()
