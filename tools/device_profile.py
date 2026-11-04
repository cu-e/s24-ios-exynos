#!/usr/bin/env python3
"""Collect engineering metadata via authorized ADB; never su, reboot or flash."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tarfile
import time
import zlib

PROPERTIES = """
ro.product.model ro.product.device ro.product.name ro.product.board ro.product.brand
ro.product.manufacturer ro.product.cpu.abi ro.product.cpu.abilist ro.product.cpu.abilist64
ro.product.cpu.abilist32 ro.soc.manufacturer ro.soc.model ro.board.platform ro.hardware
ro.boot.hardware ro.boot.hardware.platform ro.boot.bootloader ro.bootloader
ro.build.fingerprint ro.vendor.build.fingerprint ro.bootimage.build.fingerprint
ro.build.id ro.build.display.id ro.build.version.incremental ro.build.version.release
ro.build.version.sdk ro.build.version.security_patch ro.vendor.build.security_patch
ro.build.version.oneui ro.build.PDA ro.build.changelist ro.build.type ro.build.tags
ro.build.date.utc ro.vendor.build.date.utc ro.bootimage.build.date.utc
ro.boot.flash.locked ro.boot.vbmeta.device_state ro.boot.verifiedbootstate
ro.boot.veritymode ro.boot.avb_version ro.boot.vbmeta.avb_version ro.boot.warranty_bit
ro.warranty_bit ro.boot.kg ro.boot.kg.bit ro.boot.em.status ro.oem_unlock_supported
sys.oem_unlock_allowed ro.boot.slot_suffix ro.boot.dynamic_partitions
ro.boot.super_partition ro.boot.boot_devices ro.boot.hardware.revision
ro.boot.revision ro.boot.secureboot ro.secure ro.debuggable ro.adb.secure
ro.crypto.state ro.crypto.type ro.crypto.volume.filenames_mode
ro.hardware.egl ro.hardware.vulkan ro.hardware.gralloc ro.hardware.hwcomposer
ro.opengles.version ro.sf.lcd_density ro.surface_flinger.max_frame_buffer_acquired_buffers
ro.product.first_api_level ro.board.first_api_level ro.vendor.api_level
ro.apex.updatable ro.treble.enabled ro.vndk.version ro.boot.hypervisor.version
ro.boot.hypervisor.protected_vm.supported ro.boot.hypervisor.vm.supported
gsm.version.baseband
""".split()

DT_ALLOWED = {
    "compatible", "model", "device_type", "status", "reg", "ranges", "dma-ranges",
    "phandle", "linux,phandle", "interrupts", "interrupts-extended", "interrupt-parent",
    "interrupt-controller", "enable-method", "method", "clock-frequency", "clocks",
    "clock-names", "clock-output-names", "assigned-clocks", "assigned-clock-rates",
    "assigned-clock-parents", "power-domains", "power-domain-names", "memory-region",
    "memory-region-names", "no-map", "reusable", "alignment", "size", "alloc-ranges",
    "capacity-dmips-mhz", "dynamic-power-coefficient", "cpu-idle-states", "cpu-supply",
    "cache-size", "cache-sets", "cache-line-size", "cache-level", "next-level-cache",
    "operating-points", "operating-points-v2", "opp-hz", "opp-microvolt", "opp-level",
    "opp-shared", "max-frequency", "bus-width", "num-lanes", "iommus", "iommu-map",
    "iommu-map-mask", "samsung,model", "samsung,panel-name", "pinctrl-names",
    "pinctrl-0", "pinctrl-1", "pinctrl-2", "gpios", "reset-gpios", "irq-gpios",
    "spi-max-frequency", "spi-cpol", "spi-cpha", "width-mm", "height-mm",
    "dsi-lanes", "display-timings", "native-mode", "hactive", "vactive", "refresh-rate",
    "thermal-sensors", "cooling-device", "temperature", "hysteresis", "type",
    "gpio-controller", "gpio-ranges", "label", "wakeup-source", "big-endian", "little-endian",
}
SENSITIVE_KEY = re.compile(r"serial|uuid|luid|mac.?address|imei|meid|ssid|bdaddr|seed|secret|password|token|unique", re.I)
MAC = re.compile(r"(?<![0-9A-Fa-f])(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}(?![0-9A-Fa-f])")
UUID = re.compile(r"\b[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}\b")


def stamp():
    return datetime.now(timezone.utc).isoformat()


def scrub_text(value, endpoint=""):
    if endpoint:
        value = value.replace(endpoint, "[ADB endpoint redacted]")
    value = MAC.sub("[MAC redacted]", value)
    value = UUID.sub("[UUID redacted]", value)
    lines = []
    for line in value.splitlines():
        if re.search(r"^\s*(?:Serial\s*:|U:\s*Uniq\s*=)|(?:serialno|serial_number|serial-number|\bIMEI\b|\bMEID\b)\s*[:=]", line, re.I):
            continue
        lines.append(line)
    return "\n".join(lines)


def scrub_json(value, endpoint=""):
    if isinstance(value, dict):
        return {k: scrub_json(v, endpoint) for k, v in value.items() if not SENSITIVE_KEY.search(k)}
    if isinstance(value, list):
        return [scrub_json(v, endpoint) for v in value]
    return scrub_text(value, endpoint) if isinstance(value, str) else value


def device_tree(raw):
    """Parse only a property allowlist from an in-memory stream; never extract files."""
    nodes = {}
    skipped = 0
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        for member in archive:
            if not member.isfile():
                continue
            parts = Path(member.name).parts
            if not parts or ".." in parts or member.name.startswith("/"):
                skipped += 1
                continue
            prop = parts[-1]
            if "chosen" in parts or "aliases" in parts or "__symbols__" in parts or SENSITIVE_KEY.search(prop):
                skipped += 1
                continue
            if prop not in DT_ALLOWED and not re.fullmatch(r"#[a-z0-9-]+-cells", prop):
                skipped += 1
                continue
            if member.size > 65536:
                skipped += 1
                continue
            stream = archive.extractfile(member)
            data = stream.read() if stream else b""
            path = "/" + "/".join(parts[:-1])
            entry = {"bytes": len(data), "hex": data.hex()}
            text_property = prop in {"compatible", "model", "device_type", "status", "enable-method", "method",
                "label", "type", "samsung,model", "samsung,panel-name"} or prop.endswith("-names")
            if data and text_property:
                del entry["hex"]  # Don't retain an unsanitized duplicate of printable strings.
                entry["strings"] = [scrub_text(s.decode("utf-8", "replace")) for s in data.rstrip(b"\0").split(b"\0")]
            elif data and len(data) % 4 == 0:
                entry["u32_be"] = [int.from_bytes(data[i:i + 4], "big") for i in range(0, len(data), 4)]
            nodes.setdefault(path, {})[prop] = entry
    if not nodes:
        raise ValueError("No readable allowlisted device-tree properties; directory listing is not a successful DT capture")
    return {"origin": "local-device", "format": "filtered live OF device tree properties",
            "limitations": "Allowlisted static properties only; chosen/identity/seeds excluded. Raw tar not saved. No raw FDT backup.",
            "nodes": nodes, "skipped_properties": skipped}


def files_script(paths):
    names = " ".join(paths)  # All callers supply fixed source-code constants, including intentional globs.
    return f'''for p in {names}; do if [ -f "$p" ] && [ -r "$p" ]; then printf '\\n@@ %s\\n' "$p"; cat "$p"; fi; done'''


QUERIES = {
    "cpu-identity": "cat /proc/cpuinfo",
    "cpu-topology": files_script([
        "/sys/devices/system/cpu/present", "/sys/devices/system/cpu/possible", "/sys/devices/system/cpu/online",
        "/sys/devices/system/cpu/cpu[0-9]*/topology/core_id", "/sys/devices/system/cpu/cpu[0-9]*/topology/cluster_id",
        "/sys/devices/system/cpu/cpu[0-9]*/topology/physical_package_id", "/sys/devices/system/cpu/cpu[0-9]*/cpu_capacity",
        "/sys/devices/system/cpu/cpufreq/policy*/related_cpus", "/sys/devices/system/cpu/cpufreq/policy*/affected_cpus",
        "/sys/devices/system/cpu/cpufreq/policy*/cpuinfo_min_freq", "/sys/devices/system/cpu/cpufreq/policy*/cpuinfo_max_freq",
        "/sys/devices/system/cpu/cpufreq/policy*/scaling_cur_freq", "/sys/devices/system/cpu/cpufreq/policy*/scaling_governor",
        "/sys/devices/system/cpu/cpufreq/policy*/scaling_available_frequencies",
        "/sys/devices/system/cpu/cpufreq/policy*/scaling_available_governors"]),
    "memory": "getconf PAGESIZE; cat /proc/meminfo",
    "kernel-runtime": "uname -r; cat /proc/version; getenforce; " + files_script([
        "/proc/sys/kernel/kexec_load_disabled", "/proc/sys/kernel/modules_disabled", "/proc/sys/kernel/kptr_restrict",
        "/proc/sys/kernel/dmesg_restrict", "/proc/sys/kernel/perf_event_paranoid", "/proc/sys/kernel/unprivileged_bpf_disabled"]),
    "features": "pm list features",
    "vulkan-profiles": "cmd gpu vkprofiles",
    "graphics-egl": "dumpsys SurfaceFlinger",
    "display": "wm size; wm density; dumpsys display",
    "input": "cat /proc/bus/input/devices",
    "partitions": "cat /proc/partitions; ls -l /dev/block/by-name",
    "storage": "df -k /data /system /vendor /product /odm /metadata; " + files_script([
        "/sys/block/sd*/size", "/sys/block/sd*/queue/logical_block_size", "/sys/block/sd*/queue/physical_block_size",
        "/sys/block/sd*/device/vendor", "/sys/block/sd*/device/model", "/sys/block/sd*/device/rev"]),
    "mounts": "cat /proc/mounts",
    "fstab": files_script(["/vendor/etc/fstab.*", "/odm/etc/fstab.*"]),
    "devfreq": files_script(["/sys/class/devfreq/*/name", "/sys/class/devfreq/*/cur_freq", "/sys/class/devfreq/*/min_freq",
        "/sys/class/devfreq/*/max_freq", "/sys/class/devfreq/*/available_frequencies", "/sys/class/devfreq/*/governor"]),
    "gpu-nodes": "ls -ld /dev/dri/* /dev/sgpu* /dev/mali* /sys/class/drm/*; " + files_script([
        "/sys/class/drm/card*/device/vendor", "/sys/class/drm/card*/device/device", "/sys/class/drm/card*/device/revision"]),
    "virtualization-access": '''for p in /dev/kvm /dev/gzvm; do if [ -e "$p" ]; then ls -l "$p"; [ -r "$p" ] && echo readable; [ -w "$p" ] && echo writable; else echo "$p absent"; fi; done''',
    "root-binary-metadata": "command -v su; ls -l /system/bin/su /system/xbin/su /system_ext/bin/su /sbin/su",
    "power": files_script(["/sys/class/power_supply/battery/status", "/sys/class/power_supply/battery/health",
        "/sys/class/power_supply/battery/capacity", "/sys/class/power_supply/battery/temp",
        "/sys/class/power_supply/battery/voltage_now", "/sys/class/power_supply/battery/current_now",
        "/sys/class/power_supply/battery/charge_counter", "/sys/class/power_supply/battery/charge_full_design"]),
    "thermal": files_script(["/sys/class/thermal/thermal_zone*/type", "/sys/class/thermal/thermal_zone*/temp"]),
    "bus-devices": files_script(["/sys/bus/i2c/devices/*/name", "/sys/bus/spi/devices/*/modalias",
        "/sys/class/net/wlan0/device/vendor", "/sys/class/net/wlan0/device/device"]),
    "audio-hardware": "cat /proc/asound/cards; cat /proc/asound/pcm",
    "kernel-modules": "cat /proc/modules; ls /vendor/lib/modules /vendor_dlkm/lib/modules /system_dlkm/lib/modules",
    "memory-map": "cat /proc/iomem",
    "interrupts": "cat /proc/interrupts",
    "battery-service": "dumpsys battery",
    "thermal-service": "dumpsys thermalservice",
    "input-capabilities": "getevent -lp",
    "root-version": "/system_ext/bin/magisk -v",
    "device-tree-paths": "find /sys/firmware/devicetree/base -type d",
    "sensors": "dumpsys sensorservice",
}


def filter_result(name, text):
    if name == "graphics-egl":
        return "\n".join(line for line in text.splitlines() if re.match(r"\s*(?:GLES:|EGL version:|GL_[A-Z0-9_]+|EGL_[A-Z0-9_]+)", line))
    if name == "display":
        # Omit active windows, owners and virtual displays. Keep primary physical-display facts.
        rows = []
        modes_indent = None
        for line in text.splitlines():
            indent = len(line) - len(line.lstrip())
            if modes_indent is not None and line.strip() and indent > modes_indent:
                if not re.search(r"(?i)owner|package|unique|address|virtual|token|binder", line):
                    rows.append(line)
                continue
            modes_indent = None
            if re.match(r"^(Physical|Override) (size|density):", line):
                rows.append(line)
            elif re.search(r"m(DisplayId|Width|Height|ActiveModeId|DefaultModeId|SupportedModes|HdrCapabilities|Density|DisplayState|PowerMode)=", line):
                if not re.search(r"(?i)owner|package|unique|address|virtual|token|binder", line):
                    rows.append(line)
                    if "mSupportedModes=" in line:
                        modes_indent = indent
        return "\n".join(rows)
    if name == "mounts":
        keep = {"/", "/data", "/system", "/system_ext", "/vendor", "/product", "/odm", "/metadata", "/vendor_dlkm", "/system_dlkm"}
        return "\n".join(line for line in text.splitlines() if len(line.split()) >= 2 and line.split()[1] in keep)
    if name in {"input", "input-capabilities"}:
        blocks = re.split(r"(?m)(?=^add device )", text) if name == "input-capabilities" else text.split("\n\n")
        return "\n\n".join(block for block in blocks if re.search(r"(?i)sec_|touch|stm|gpio|pmic|hall|fingerprint|power.?key|volume|jack", block))
    if name == "battery-service":
        prefix = text.split("[EventLogBuffer]", 1)[0]
        keys = r"(?:AC powered|USB powered|Wireless powered|Dock powered|Max charging current|Max charging voltage|Charge counter|status|health|present|level|scale|voltage|temperature|technology|Charging state|Charging policy|current now)"
        return "\n".join(line for line in prefix.splitlines() if re.match(r"\s*" + keys + r":", line))
    if name == "thermal-service":
        return "\n".join(line for line in text.splitlines() if re.match(r"\s*(?:Temperature\{|CoolingDevice\{|Thermal Status:|HAL Ready:)", line))
    if name == "sensors":
        rows = []
        active = False
        for line in text.splitlines():
            if re.match(r"\s*Sensor List:", line):
                active = True
                rows.append(line)
            elif active:
                if line and not line[0].isspace() and not re.match(r"0x[0-9a-fA-F]+\)", line):
                    break
                if not re.search(r"(?i)uid=|package|registration|active sensor|connection|history", line):
                    rows.append(line)
        return "\n".join(rows)
    return text


class Collector:
    def __init__(self, endpoint, directory):
        self.endpoint, self.directory, self.records = endpoint, directory, []

    def collect(self, name, command, transform=None, suffix="txt", binary=False, timeout=25):
        start = time.monotonic()
        record = {"id": name, "command": command, "started_at": stamp()}
        try:
            mode = "exec-out" if binary else "shell"
            result = subprocess.run(["adb", "-s", self.endpoint, mode, command], capture_output=True, timeout=timeout)
            record["exit_code"] = result.returncode
            err = scrub_text(result.stderr.decode("utf-8", "replace"), self.endpoint)
            if err:
                record["diagnostic"] = err[:8000]
            if len(result.stdout) > 32 * 1024 * 1024:
                raise ValueError("Metadata capture exceeded 32 MiB")
            if binary:
                data = transform(result.stdout) if result.stdout else None
            else:
                text = result.stdout.decode("utf-8", "replace")
                data = transform(text) if transform else filter_result(name, text)
            if isinstance(data, (dict, list)):
                output = json.dumps(scrub_json(data, self.endpoint), ensure_ascii=False, indent=2) + "\n"
            else:
                output = scrub_text(data or "", self.endpoint) + "\n"
            if not output.strip():
                output = "No readable metadata returned; this does not imply absent hardware.\n"
            path = self.directory / f"{name}.{suffix}"
            path.write_text(output)
            record.update(file=path.name, bytes=path.stat().st_size,
                          sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                          status="collected" if result.returncode == 0 and data else "partial-or-unavailable")
        except (subprocess.TimeoutExpired, OSError, ValueError, tarfile.TarError, EOFError, zlib.error) as exc:
            record.update(status="unavailable", error=scrub_text(str(exc), self.endpoint)[:1000])
        record["elapsed_seconds"] = round(time.monotonic() - start, 3)
        self.records.append(record)
        print(f"{name}: {record['status']}", flush=True)


def config_decode(raw):
    text = gzip.decompress(raw).decode("utf-8", "replace")
    return "\n".join(line for line in text.splitlines() if not line.startswith(("CONFIG_BUILD_SALT=", "CONFIG_CMDLINE=", "CONFIG_SYSTEM_TRUSTED_KEYS=", "CONFIG_SYSTEM_REVOCATION_KEYS=")))


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--device", help="Authorized endpoint; not saved")
    parser.add_argument("--sections", nargs="+", choices=[*QUERIES, "properties", "vulkan", "kernel", "device-tree"],
                        help="Collect only selected sections into a new directory")
    args = parser.parse_args()
    result = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=15, check=True)
    rows = [line.split() for line in result.stdout.splitlines()[1:] if line.strip()]
    if args.device:
        rows = [row for row in rows if row[0] == args.device]
    if len(rows) != 1 or len(rows[0]) < 2 or rows[0][1] != "device":
        raise RuntimeError("Need exactly one already-authorized ADB device; no connection settings changed")
    endpoint = rows[0][0]
    model = subprocess.check_output(["adb", "-s", endpoint, "shell", "getprop ro.product.model"], text=True, timeout=10).strip()
    device = subprocess.check_output(["adb", "-s", endpoint, "shell", "getprop ro.product.device"], text=True, timeout=10).strip()
    if model != "SM-S921B" or device != "e1s":
        raise RuntimeError("Connected phone does not match this collection plan's SM-S921B/e1s target")
    args.output_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    collector = Collector(endpoint, args.output_dir)
    selected = set(args.sections) if args.sections else None
    prop_command = "\n".join(f"printf '%s\\t' {shlex.quote(key)}; getprop {shlex.quote(key)}" for key in PROPERTIES)
    if selected is None or "properties" in selected:
        collector.collect("properties", prop_command, lambda text: dict(line.split("\t", 1) for line in text.splitlines() if "\t" in line), "json")
    for name, command in QUERIES.items():
        if selected is None or name in selected:
            collector.collect(name, command)
    if selected is None or "vulkan" in selected:
        collector.collect("vulkan", "cmd gpu vkjson", json.loads, "json", timeout=45)
    if selected is None or "kernel" in selected:
        collector.collect("kernel", "cat /proc/config.gz", config_decode, "config", binary=True)
    if selected is None or "device-tree" in selected:
        collector.collect("device-tree", "tar -C /sys/firmware/devicetree/base -cf - .", device_tree, "json", binary=True, timeout=45)
    manifest = {"schema_version": 1, "origin": "local-device", "observed_at": stamp(),
                "model": model, "device": device, "matches_reference_target": True,
                "tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "method": "Read-only Android shell metadata; no root request, settings changes, reboot, installs, partition writes or personal files.",
                "privacy": "Identifiers scrubbed before saving; Vulkan UUIDs removed; live device tree allowlisted; raw dumpsys/tar/getprop not stored.",
                "limitations": ["The collection does not prove native boot, root, KVM ioctl access or recovery.",
                    "Boot properties can be overridden and are not a Download Mode observation.",
                    "A readable node or enabled kernel option is not proof that the capability works.",
                    "These are metadata snapshots, not BOOT/recovery backups."], "captures": collector.records}
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(f"Saved {len(collector.records)} captures in {args.output_dir}")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
        # Don't echo the endpoint embedded in a subprocess command exception.
        raise SystemExit(f"profile: {type(exc).__name__}; collection stopped without device mutations")
