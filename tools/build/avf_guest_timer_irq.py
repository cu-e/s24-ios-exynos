#!/usr/bin/env python3
"""Inspect pinned guest timer/IRQ prerequisites without compiling or starting QEMU."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import signal
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures/public/avf-guest-timer-irq/inputs.json"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def memory():
    values = {}
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith(("VmRSS:", "VmHWM:")):
            key, value, _unit = line.split()
            values[key[:-1] + "_bytes"] = int(value) * 1024
    return values


def require(condition, message):
    if not condition:
        raise ValueError(message)


def code(text):
    return re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.S)


def define(text, name):
    match = re.search(r"^#define\s+" + re.escape(name) + r"\s+(0x[0-9a-fA-F]+|[0-9]+)\b", text, re.M)
    require(match is not None, "missing numeric definition: " + name)
    return int(match[1], 0)


def ordered(text, tokens, label):
    offset = 0
    for token in tokens:
        found = text.find(token, offset)
        require(found >= 0, label + ": missing ordered token " + token)
        offset = found + len(token)


def validate_launch(launch, facts):
    expected = {"machine": "virt,gic-version=3", "accel": "tcg", "cpu": "cortex-a76",
                "smp": 1, "memory_mib": 256, "dt_format": "shim-converted-Apple-DT",
                "virtual_timer_intid": facts["virtual_timer_intid"],
                "gicd": facts["gicd"], "gicr": facts["gicr"]}
    require(set(launch) == set(expected) | {"required_spi_intids"}, "launch keys must match the narrow qualified contract")
    for key, value in expected.items():
        require(type(launch[key]) is type(value) and launch[key] == value, "launch constraint mismatch: " + key)
    spis = launch["required_spi_intids"]
    require(isinstance(spis, list), "required_spi_intids must be a list")
    require(len(spis) == len(set(spis)), "duplicate SPI")
    for intid in spis:
        require(type(intid) is int and facts["spi_min"] <= intid <= facts["qemu_spi_max"],
                "SPI outside actual QEMU controller range: " + str(intid))
    require(len(spis) <= facts["guest_spi_slots"], "too many guest SPI attachment slots")


def inspect(main, pin, records):
    texts = {}
    for name, item in pin["files"].items():
        path = main / item["path"]
        require(not path.is_symlink(), "input symlink rejected: " + name)
        actual = {"path": str(path), "size": path.stat().st_size, "sha256": digest(path)}
        records[name] = actual
        require(actual["sha256"] == item["sha256"] and actual["size"] == item["size"], "input identity mismatch: " + name)
        if item.get("text"):
            require(actual["size"] < 1024 * 1024, "text input exceeds bound")
            texts[name] = code(path.read_text())
    gic, board, qemu, bsa = (texts[x] for x in ("guest_gic", "guest_board", "qemu_virt", "qemu_bsa"))
    require(define(board, "GENERIC_GIC_V3_IRQ") == 1, "generic GIC path disabled")
    require("#define ARM_ARCH_TIMER" in board, "architected timer not selected")
    require("#include <pexpert/arm64/BCM2837.h>" in texts["guest_board_selector"], "board header selection missing")
    require("#define HAS_GIC_V3" not in board, "Apple GIC FIQ branch requires new review")
    facts = {"virtual_timer_intid": define(gic, "GIC_INTID_VTIMER"),
             "qemu_virtual_timer_intid": define(bsa, "ARCH_TIMER_VIRT_IRQ"),
             "spi_min": define(gic, "GIC_INTID_SPI_MIN"),
             "guest_spi_max": define(gic, "GIC_INTID_SPURIOUS_MIN") - 1,
             "guest_spi_slots": define(gic, "GIC_SPI_MOST"),
             "qemu_spi_max": define(qemu, "NUM_IRQS") + 31,
             "redistributor_frame_size": define(gic, "GICR_FRAME_SIZE")}
    require(facts["virtual_timer_intid"] == facts["qemu_virtual_timer_intid"] == 27, "timer PPI differs")
    for name, symbol in (("gicd", "VIRT_GIC_DIST"), ("gicr", "VIRT_GIC_REDIST")):
        match = re.search(r"\[" + symbol + r"\]\s*=\s*\{\s*(0x[0-9a-fA-F]+),\s*(0x[0-9a-fA-F]+)\s*\}", qemu)
        require(match is not None, "missing QEMU MMIO mapping: " + symbol)
        facts[name] = [int(match[1], 0), int(match[2], 0)]
    require(facts["gicr"][1] >= facts["redistributor_frame_size"], "redistributor range too small")
    ordered(qemu, ["[GTIMER_VIRT] = ARCH_TIMER_VIRT_IRQ", "intidbase + timer_irq[irq]"], "QEMU timer wiring")
    ordered(gic[gic.index("gic_v3_irq_cpu_init(void)\n{"):],
            ['"/arm-io/gic"', "soc_base + reg[0]", '"ICC_SRE_EL1"', "gic_find_redistributor()",
             "GICR_WAKER_CHILDASLEEP", "GICR_IGROUPR0", "GICR_ISENABLER0", "GICD_CTLR_ENABLE_G1NS",
             '"ICC_PMR_EL1"', '"ICC_IGRPEN1_EL1"', "ml_install_interrupt_handler"], "guest GIC initialization")
    ordered(gic, ['"ICC_IAR1_EL1"', "intid == GIC_INTID_VTIMER", "rtclock_intr(TRUE)", '"ICC_EOIR1_EL1"'], "IRQ acknowledge/dispatch/EOI")
    require("virtual-timer-intid" not in gic, "timer DT consumption changed; review hardcoded INTID constraint")
    ordered(texts["guest_fiq"], ["#elif defined(GENERIC_GIC_V3_IRQ)", "gic_v3_irq_cpu_init();"], "generic PE hook")
    ordered(texts["guest_arm_init"], ["PE_init_cpu();", "fiq_context_init(TRUE);"], "GIC setup before timer enable")
    ordered(texts["guest_machine"], ["_enable_virtual_timer(void)", "CNTV_CTL_EL0_ENABLE", '"CNTV_CTL_EL0"', "fiq_context_init("], "virtual timer enable")
    require('"CNTV_TVAL_EL0"' in texts["guest_machine"] and '"CNTVCT_EL0"' in texts["guest_machine"], "virtual deadline/counter path missing")
    shim = texts["shim"]
    ordered(shim, ['"arm,gic-v3"', "m.vtimer_intid = 27", "m.vtimer_intid = 16 + num"], "shim FDT timer conversion")
    ordered(shim, ['uint64_t cntfrq = rsr("cntfrq_el0")', '"timebase-frequency", cntfrq',
                   '"ranges", ranges', "m.gicd - io_base", '"virtual-timer-intid", m.vtimer_intid'], "shim Apple DT conversion")
    require('"timebase-frequency"' in texts["guest_identify"], "guest frequency property consumption missing")
    ordered(texts["host_launcher"], ['"-machine", "virt,gic-version=3"', '"-accel", "tcg"',
            '"-cpu", "cortex-a76"', '"-smp", "1"', '"-m", str(args.memory_mib)'], "existing host launcher flags")
    ordered(texts["guest_rtclock"], ['rtclock_init(void)', 'clock_timebase_init();',
            'timer_resync_deadlines();'], "clock initialization")
    manifest_path = main / pin["files"]["object_manifest"]["path"]
    rows = json.loads(manifest_path.read_text())
    for object_id in ("osfmk/gic_v3_irq.o", "osfmk/machine_routines.o", "osfmk/arm_init.o", "osfmk/rtclock.o"):
        selected = [row for row in rows if row["id"] == object_id]
        require(len(selected) == 1, "missing or duplicate genuine recipe: " + object_id)
        row = selected[0]
        require("-DARM64_BOARD_CONFIG_BCM2837" in row["next_owned_compile_argv_template"], "wrong recipe board")
        source = Path(row["bound_source"])
        require(digest(source) == row["bound_source_sha256"], "recipe bound source mismatch")
        require(digest(Path(row["configuration"])) == row["configuration_sha256"], "recipe config mismatch")
        facts.setdefault("selected_recipes", []).append({"id": object_id, "source": str(source),
                 "source_sha256": row["bound_source_sha256"], "configuration_sha256": row["configuration_sha256"]})
    return facts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--launch", type=Path, default=FIXTURE.with_name("launch.json"))
    parser.add_argument("--inputs", type=Path, default=FIXTURE)
    parser.add_argument("--controls", action="store_true")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    report = {"task": "VM-029", "evidence_kind": "source-review/host-test", "outcome": "fail",
              "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "argv": sys.argv,
              "inputs": {}, "memory_start": memory(), "pid": os.getpid(),
              "compiler_started": False, "qemu_started": False, "guest_executed": False,
              "timer_irq_observed": False, "phone_accessed": False, "controls": []}
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024**2, 256 * 1024**2))
    signal.signal(signal.SIGALRM, lambda *_args: (_ for _ in ()).throw(TimeoutError("30-second inspection deadline")))
    signal.alarm(30)
    try:
        pin = json.loads(args.inputs.read_text())
        report["input_descriptor_sha256"] = digest(args.inputs)
        report["tool"] = {"path": str(Path(__file__).resolve()), "sha256": digest(Path(__file__))}
        python = Path(sys.executable).resolve()
        report["python"] = {"path": str(python), "sha256": digest(python), "version": sys.version}
        facts = inspect(args.main.resolve(strict=True), pin, report["inputs"])
        report["facts"] = facts
        launch = json.loads(args.launch.read_text())
        validate_launch(launch, facts)
        report["launch"] = {"path": str(args.launch), "sha256": digest(args.launch), "constraints": launch}
        if args.controls:
            for key, value in (("machine", "virt,gic-version=2"), ("cpu", "max"), ("accel", "kvm"),
                               ("smp", 2), ("virtual_timer_intid", 30), ("required_spi_intids", [288]),
                               ("gicr", [0x080A0000, 0x10000]), ("dt_format", "raw-FDT")):
                changed = dict(launch) | {key: value}
                try:
                    validate_launch(changed, facts)
                except ValueError as error:
                    report["controls"].append({"field": key, "mutated_value": value, "outcome": "rejected", "error": str(error)})
                else:
                    raise ValueError("negative launch control unexpectedly accepted: " + key)
        report["limitations"] = ["Exact pinned source witnesses, not C preprocessing, compiled code or runtime proof.",
          "Guest accepts SPIs 32..1019 but this QEMU config provides only 32..287; require the intersection.",
          "Shim emits virtual-timer-intid but this guest hardcodes 27; any other timer INTID requires a source change/review.",
          "Redistributor wake and distributor RWP waits have no source timeout; future guest requires external finite supervisor.",
          "Counter frequency, IRQ delivery, deadline rearm, monotonicity and EOI behavior remain unmeasured.",
          "VM008 namespace acceptance, independent review and root resource/guest leases remain separate gates."]
        report["outcome"] = "pass"
    except (OSError, ValueError, KeyError, TypeError, MemoryError, TimeoutError) as error:
        report["error"] = str(error)
    finally:
        signal.alarm(0)
        report["exit_code"] = 0 if report["outcome"] == "pass" else 2
        report["elapsed_seconds"] = time.monotonic() - start
        report["memory_end"] = memory()
        (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: report.get(key) for key in ("outcome", "exit_code", "error", "elapsed_seconds", "memory_end")}))
    return report["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
