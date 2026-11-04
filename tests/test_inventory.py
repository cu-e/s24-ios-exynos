"""Exercise inventory against an in-memory ADB double, never a connected phone."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "tools/device_inventory.py"
spec = importlib.util.spec_from_file_location("inventory", SCRIPT)
inventory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inventory)


class InventoryTests(unittest.TestCase):
    def test_only_readonly_commands_and_no_serial_in_output(self):
        commands = []

        def fake_run(argv):
            commands.append(argv)
            if argv == ["adb", "devices"]:
                return "List of devices attached\nPRIVATE_SERIAL\tdevice"
            self.assertEqual(argv[:4], ["adb", "-s", "PRIVATE_SERIAL", "shell"])
            tail = argv[4:]
            if tail[:1] == ["getprop"]:
                self.assertIn(tail[1], inventory.PROPERTIES)
                return {"ro.product.model": "SM-S921B", "ro.product.device": "e1s"}.get(tail[1], "fixture")
            allowed = {("id",): "uid=2000(shell)", ("uname", "-r"): "test-kernel", ("wm", "size"): "1080x2340", ("wm", "density"): "420"}
            self.assertIn(tuple(tail), allowed)
            return allowed[tuple(tail)]

        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "inventory.json"
            captured = io.StringIO()
            with patch.object(inventory, "run", side_effect=fake_run), patch("sys.argv", ["inventory", "--output", str(out)]), contextlib.redirect_stdout(captured):
                inventory.main()
            doc = json.loads(out.read_text())
            self.assertTrue(doc["matches_reference_target"])
            self.assertNotIn("PRIVATE_SERIAL", out.read_text() + captured.getvalue())
            self.assertEqual(out.stat().st_mode & 0o777, 0o600)
            self.assertEqual(len(commands), 1 + len(inventory.PROPERTIES) + 4)

    def test_multiple_devices_are_not_implicitly_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "inventory.json"
            with patch.object(inventory, "run", return_value="List of devices attached\na\tdevice\nb\tdevice"), patch("sys.argv", ["inventory", "--output", str(out)]):
                with self.assertRaises(RuntimeError):
                    inventory.main()
            self.assertFalse(out.exists())

    def test_old_inventory_is_not_overwritten_or_reread_from_phone(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "inventory.json"
            out.write_text("original")
            with patch.object(inventory, "run") as mocked, patch("sys.argv", ["inventory", "--output", str(out)]):
                with self.assertRaises(FileExistsError):
                    inventory.main()
                mocked.assert_not_called()
            self.assertEqual(out.read_text(), "original")

    def test_unauthorized_device_is_not_paired_automatically(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "inventory.json"
            with patch.object(inventory, "run", return_value="List of devices attached\na\tunauthorized") as mocked, patch("sys.argv", ["inventory", "--output", str(out)]):
                with self.assertRaises(RuntimeError):
                    inventory.main()
                self.assertEqual(mocked.call_count, 1)
            self.assertFalse(out.exists())
