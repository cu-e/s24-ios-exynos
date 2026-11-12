#!/usr/bin/env python3
"""NAT-073: RAM and time budget for delivering the iOS root to the payload kernel.

Reads only local facts that already exist and writes a small JSON with numbers:

  * the runtime device tree facts of this S24 (devices/e1s-fdt/2026-11-10/runtime.facts.json, local only)
  * the loader's own log of the NAT-068 run (artifacts/nat-068/run-001/archive/received.bin, local only)
  * the committed kernel log of the same run (docs/procedures/nat-068/run-001-kernel-log.txt)

Nothing here touches the phone.  Every output number is either copied from one of those inputs, arithmetic on them,
or an explicit scenario (labelled).  Usage:

  python3 -I docs/procedures/nat-073/budget.py OUT.json [--root-bytes N]
"""
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FDT_FACTS = ROOT / "devices/e1s-fdt/2026-11-10/runtime.facts.json"
LOADER_ARCHIVE = ROOT / "artifacts/nat-068/run-001/archive/received.bin"
KERNEL_LOG = ROOT / "docs/procedures/nat-068/run-001-kernel-log.txt"

MIB = 1 << 20
GIB = 1 << 30
TICK_HZ = 25_600_000          # CNTFRQ_EL0 = 25.6 MHz (NAT-005 DT value; VM-051 read it on the S24)
WDT_MAX_S = 83.8848           # counter 0xffff x divider 128 x prescaler 256 at 25.6 MHz (NAT-019)
MIN_WINDOW = 256 * MIB        # references/s24-port/shim/e1s-xnu/loader.c
MAX_WINDOW = 512 * MIB        # same file: the cap the NAT-068 run hit
LOG_BASE, LOG_RESERVE = 0x91200000, 0x200000


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def free_gaps(memory, reserved, min_size=0):
    """Maximal gaps of `memory` ranges not covered by `reserved` ranges.  Ranges are (base, size)."""
    gaps = []
    occ = sorted((b, b + s) for b, s in reserved if s)
    for mb, ms in sorted(memory):
        cursor, end = mb, mb + ms
        for rb, re_ in occ:
            if re_ <= cursor or rb >= end:
                continue
            if rb > cursor:
                gaps.append((cursor, rb))
            cursor = max(cursor, re_)
            if cursor >= end:
                break
        if cursor < end:
            gaps.append((cursor, end))
    return [(a, b - a) for a, b in gaps if b - a >= min_size]


def merge_ranges(ranges):
    """Merge touching or overlapping (base, size) ranges."""
    out = []
    for b, sz in sorted(ranges):
        if out and b <= out[-1][0] + out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][0] + out[-1][1], b + sz) - out[-1][0])
        else:
            out.append((b, sz))
    return out


def loader_choice(memory_in_dt_order, reserved):
    """The loader's choose_window() rule (references/s24-port/shim/e1s-xnu/loader.c), per DT node, first best wins."""
    align = 2 * MIB - 1
    best = [0, 0]

    def consider(start, end):
        base = (start + align) & ~align
        if end <= base:
            return
        size = min(end - base, MAX_WINDOW) & ~align
        if size < MIN_WINDOW or size <= best[1]:
            return
        best[0], best[1] = end - size, size

    occ = sorted((b, s) for b, s in reserved if s)
    for mb, ms in memory_in_dt_order:
        cursor, end = mb, mb + ms
        for rb, rs in occ:
            if rs == 0 or rb >= end or rb + rs <= cursor:
                continue
            if rb > cursor:
                consider(cursor, rb)
            cursor = max(cursor, rb + rs)
            if cursor >= end:
                break
        if cursor < end:
            consider(cursor, end)
    return tuple(best)


def loader_log_rows(blob):
    rows = []
    for line in blob.decode("latin1").splitlines():
        line = line.strip()
        if line.startswith("{") and '"kind":"log"' in line:
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
    return rows


def kv(text, key):
    m = re.search(r"\b" + re.escape(key) + r"=(0x[0-9a-fA-F]+)", text)
    return int(m.group(1), 16) if m else None


def loader_measurements(rows):
    """Window choice, zeroing time and phase ticks from the loader's own text lines."""
    texts = [r["text"] for r in rows]
    out = {}
    for t in texts:
        if t.startswith("window from DTB"):
            out["window_base"] = kv(t, "win")
            out["window_size"] = kv(t, "win size")
        if "zero_begin=" in t:
            out["zero_begin_ticks"] = kv(t, "ticks")
        if t.startswith("zeroed"):
            out["zeroed_seen"] = True
        if "clean_full_window_begin" in t:
            out["clean_begin_ticks"] = kv(t, "ticks")
        if "clean_full_window_end" in t:
            out["clean_end_ticks"] = kv(t, "ticks")
        if "return_entry_to_assembly" in t:
            out["handoff_ticks"] = kv(t, "ticks")
    zero_ticks = [kv(t, "ticks") for t in texts if "zero_bytes=" in t]
    out["zero_steps"] = len(zero_ticks)
    if zero_ticks:
        out["zero_end_ticks"] = zero_ticks[-1]
    seg = [t for t in texts if re.match(r"seg 0x[0-9a-f]+ -> ", t)]
    out["segments"] = len(seg)
    out["segment_bytes"] = sum(int(t.split()[-1], 16) for t in seg)
    return out


def derive_timing(m):
    d = {}
    zt = m["zero_end_ticks"] - m["zero_begin_ticks"]
    d["zero_seconds"] = zt / TICK_HZ
    d["zero_MB_per_s_including_ui_flush"] = m["window_size"] / (zt / TICK_HZ) / 1e6
    d["clean_seconds"] = (m["clean_end_ticks"] - m["clean_begin_ticks"]) / TICK_HZ
    d["clean_GB_per_s"] = m["window_size"] / d["clean_seconds"] / 1e9
    d["copy_phase_seconds_zero_end_to_clean_begin"] = (m["clean_begin_ticks"] - m["zero_end_ticks"]) / TICK_HZ
    d["handoff_counter_seconds"] = m["handoff_ticks"] / TICK_HZ
    d["zero_begin_counter_seconds"] = m["zero_begin_ticks"] / TICK_HZ
    return d


def scenarios(root_bytes, zero_mb_s, windows):
    rates = [("control-OUT pessimistic (assumption)", 2e6), ("control-OUT optimistic (assumption)", 15e6),
             ("bulk-OUT low (assumption)", 25e6), ("bulk-OUT donor figure", 28e6), ("bulk-OUT high (assumption)", 40e6)]
    t = []
    for name, r in rates:
        s = root_bytes / r
        t.append({"rate": name, "MB_per_s": r / 1e6, "transfer_s": round(s, 1),
                  "petted_wdt_periods_of_60s": int(s // 60) + 1})
    z = [{"window_MiB": w // MIB, "zero_seconds_at_measured_rate": round(w / (zero_mb_s * 1e6), 1)} for w in windows]
    return {"transfer": t, "zeroing": z}


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    out_path = Path(argv[0])
    root_bytes = int(argv[argv.index("--root-bytes") + 1]) if "--root-bytes" in argv else 2_475_712_512

    facts = json.loads(FDT_FACTS.read_text())
    memory = [(int(r[0], 16), int(r[1], 16)) for m in facts["memory"] for r in m["reg"]]
    reserved = [(int(r[0], 16), int(r[1], 16)) for x in facts["reserved_memory"] for r in x["reg"]]
    reserved.append((LOG_BASE, LOG_RESERVE))
    merged = merge_ranges(memory)
    high = [(b, s) for b, s in merged if b >= 0x800000000]
    gaps_high = free_gaps(high, reserved, MIN_WINDOW)
    gaps_low = free_gaps([x for x in merged if x[0] < 0x800000000], reserved, MIN_WINDOW)
    biggest = max(gaps_high, key=lambda g: g[1])
    per_node_gaps = free_gaps(memory, reserved, MIN_WINDOW)
    replay = loader_choice(memory, reserved)

    rows = loader_log_rows(LOADER_ARCHIVE.read_bytes())
    lm = loader_measurements(rows)
    timing = derive_timing(lm)

    klog = KERNEL_LOG.read_text(errors="replace")
    m = re.search(r"vm_page_bootstrap: (\d+) free pages, (\d+) wired pages", klog)
    free_pages, wired_pages = int(m.group(1)), int(m.group(2))
    pages = free_pages + wired_pages

    report = {
        "scope": "NAT-073 root delivery budget; host arithmetic on existing local facts; nothing ran on the phone",
        "inputs": {
            "runtime_fdt_facts_sha256": sha256(FDT_FACTS),
            "nat068_loader_stream_sha256": sha256(LOADER_ARCHIVE),
            "nat068_kernel_log_sha256": sha256(KERNEL_LOG),
        },
        "device_tree_memory": {
            "ranges": [{"base": hex(b), "MiB": s // MIB} for b, s in sorted(memory)],
            "ranges_after_merging_touching_nodes": [{"base": hex(b), "MiB": s // MIB} for b, s in merged],
            "loader_rule_replayed_on_these_facts": {"base": hex(replay[0]), "MiB": replay[1] // MIB},
            "largest_gap_when_each_DT_node_is_taken_alone_MiB": max(g[1] for g in per_node_gaps) // MIB,
            "total_MiB": sum(s for _, s in memory) // MIB,
            "reserved_with_address": len(reserved) - 1,
            "free_gaps_ge_256MiB_high_region": [{"base": hex(b), "end": hex(b + s), "MiB": s // MIB} for b, s in gaps_high],
            "free_gaps_ge_256MiB_low_region": [{"base": hex(b), "end": hex(b + s), "MiB": s // MIB} for b, s in gaps_low],
            "largest_gap": {"base": hex(biggest[0]), "end": hex(biggest[0] + biggest[1]), "MiB": biggest[1] // MIB},
        },
        "loader_window_nat068": {
            "base": hex(lm["window_base"]), "size_MiB": lm["window_size"] // MIB,
            "cap_in_loader_source_MiB": MAX_WINDOW // MIB,
            "replay_of_loader_rule_matches_observed": (lm["window_base"], lm["window_size"]) == replay,
            "payload_segments": lm["segments"], "payload_segment_bytes": lm["segment_bytes"],
        },
        "kernel_view_nat068": {
            "vm_page_bootstrap_free_pages": free_pages, "wired_pages": wired_pages,
            "pages_total": pages,
            "bytes_if_4KiB_pages": pages * 4096, "bytes_if_16KiB_pages": pages * 16384,
            "reading": "pages x 4 KiB equals the 512 MiB window exactly; the kernel advertised 4 KiB pages in this run",
        },
        "timing_nat068": {k: (round(v, 3) if isinstance(v, float) else v) for k, v in timing.items()},
        "root": {"bytes": root_bytes, "MiB": round(root_bytes / MIB, 1), "GiB": round(root_bytes / GIB, 3)},
        "window_fit": {},
        "scenarios": scenarios(root_bytes, timing["zero_MB_per_s_including_ui_flush"],
                               [512 * MIB, 2 * GIB, 4 * GIB, biggest[1] // MIB * MIB]),
        "window_proposal": {"base": hex(biggest[0]), "end": hex(biggest[0] + biggest[1]), "MiB": biggest[1] // MIB,
                            "needs": "merge touching DT memory nodes in choose_window and raise MAX_WINDOW"},
    }
    wired_mib = wired_pages * 4096 / MIB
    for w in (2 * GIB, 3 * GIB, 4 * GIB, biggest[1]):
        left = w - root_bytes - 120 * MIB
        report["window_fit"][str(w // MIB) + "MiB"] = {
            "after_root_and_120MiB_kernel_estimate_MiB": round(left / MIB, 0),
            "note": "120 MiB = measured wired pages of the 512 MiB run (%.0f MiB) rounded up; scales with memory, estimate" % wired_mib,
        }
    out_path.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    print("wrote", out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
