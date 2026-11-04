"""Privacy and failure-boundary checks; all device data here is synthetic."""
import importlib.util
import io
import json
from pathlib import Path
import re
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import subprocess

SCRIPT = Path(__file__).resolve().parents[1] / "tools/device_profile.py"
spec = importlib.util.spec_from_file_location("profile", SCRIPT)
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)


class ProfileTests(unittest.TestCase):
    def test_vulkan_identifiers_removed_but_gpu_model_ids_retained(self):
        raw = {"devices": [{"properties": {"deviceName": "Xclipse 940", "vendorID": 123, "deviceID": 456,
               "pipelineCacheUUID": [1, 2, 3]}, "pNext": [{"deviceUUID": "private", "deviceLUID": [9]}]}]}
        result = profile.scrub_json(raw)
        self.assertNotIn("UUID", json.dumps(result))
        self.assertNotIn("LUID", json.dumps(result))
        self.assertEqual(result["devices"][0]["properties"]["deviceID"], 456)

    def test_device_tree_excludes_bootargs_seeds_identifiers_and_unsafe_paths(self):
        buf = io.BytesIO()
        values = {"./model": b"Samsung Galaxy S24\0", "./cpus/cpu@0/reg": b"\0\0\0\0",
                  "./chosen/bootargs": b"androidboot.serialno=SECRET", "./serial-number": b"SECRET",
                  "./rng-seed": b"SECRET", "../../model": b"SECRET", "./soc/mac-address": b"SECRET"}
        with tarfile.open(fileobj=buf, mode="w") as archive:
            for name, data in values.items():
                info = tarfile.TarInfo(name); info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
        result = profile.device_tree(buf.getvalue())
        self.assertNotIn("SECRET", json.dumps(result))
        self.assertEqual(result["nodes"]["/"]["model"]["strings"], ["Samsung Galaxy S24"])
        self.assertEqual(result["nodes"]["/cpus/cpu@0"]["reg"]["u32_be"], [0])
        self.assertEqual(result["skipped_properties"], 5)

    def test_no_printable_identifier_copy_in_device_tree_hex(self):
        buf = io.BytesIO(); data = b"00:11:22:33:44:55\0"
        with tarfile.open(fileobj=buf, mode="w") as archive:
            info = tarfile.TarInfo("./soc/label"); info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        entry = profile.device_tree(buf.getvalue())["nodes"]["/soc"]["label"]
        self.assertNotIn("hex", entry)
        self.assertEqual(entry["strings"], ["[MAC redacted]"])

    def test_empty_device_tree_is_not_a_success(self):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as archive:
            info = tarfile.TarInfo("."); info.type = tarfile.DIRTYPE
            archive.addfile(info)
        with self.assertRaises(ValueError):
            profile.device_tree(buf.getvalue())

    def test_battery_service_omits_usage_history(self):
        text = "level: 80\ntemperature: 286\nbattery FirstUseDate: private\n[EventLogBuffer]\nlevel: 7\n"
        result = profile.filter_result("battery-service", text)
        self.assertIn("level: 80", result)
        self.assertNotIn("private", result)
        self.assertNotIn("level: 7", result)

    def test_selected_display_and_mount_metadata_excludes_app_context(self):
        display = "Physical size: 1080x2340\nmOwnerPackageName=com.private.app\nmActiveModeId=2\nmDisplayId=1 owner=private\n"
        result = profile.filter_result("display", display)
        self.assertIn("1080x2340", result)
        self.assertNotIn("private", result)
        mounts = "/dev/block/dm-1 /data f2fs rw 0 0\n/private /data/app/com.private ext4 rw 0 0"
        self.assertNotIn("private", profile.filter_result("mounts", mounts))

    def test_input_devices_are_filtered_independently_without_blank_lines(self):
        text = 'add device 1: /dev/input/event0\n name: "sec_touchscreen"\nadd device 2: /dev/input/event9\n name: "Private Bluetooth Keyboard"\n'
        result = profile.filter_result("input-capabilities", text)
        self.assertIn("sec_touchscreen", result)
        self.assertNotIn("Private", result)

    def test_no_remote_mutation_commands_in_collection_plan(self):
        forbidden = re.compile(r"(?:^|[;\n])\s*(?:reboot|setprop|dd|mount|umount|insmod|rmmod|su|input|settings|am|svc|rm|chmod|chown)\b")
        for name, command in profile.QUERIES.items():
            self.assertIsNone(forbidden.search(command), name)
        self.assertFalse(any(re.search(r"serial|imei|meid|macaddr", key, re.I) for key in profile.PROPERTIES))

    def test_timeout_is_recorded_without_inventing_data(self):
        with tempfile.TemporaryDirectory() as directory:
            collector = profile.Collector("PRIVATE_ENDPOINT", Path(directory))
            with patch.object(profile.subprocess, "run", side_effect=subprocess.TimeoutExpired(["adb", "PRIVATE_ENDPOINT"], 1)):
                collector.collect("test", "cat /proc/meminfo")
            self.assertEqual(collector.records[0]["status"], "unavailable")
            self.assertNotIn("PRIVATE_ENDPOINT", json.dumps(collector.records))
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
