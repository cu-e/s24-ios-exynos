"""Invalid build requests must fail before creating or compiling in a run directory."""
from pathlib import Path
import subprocess
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/build/xnu_host_tools.py"


class HostToolAdmissionTests(unittest.TestCase):
    def reject(self, extra, message, run=None):
        name = run or "rejected-" + uuid.uuid4().hex
        argv = ["python3", str(SCRIPT), "--run", name, "--cc", "/usr/bin/cc", "--preprocessor", "/usr/bin/cc", *extra]
        result = subprocess.run(argv, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn(message, result.stderr)
        if run is None:
            self.assertFalse((ROOT / "artifacts/xnu-host-tools" / name).exists())

    def test_run_escape_and_build_resource_limits_precede_compilation(self):
        self.reject([], "Invalid unique run name", run="../escape")
        self.reject(["--jobs", "0"], "Use1..4 build jobs")
        self.reject(["--jobs", "1000"], "Use1..4 build jobs")

    def test_compiler_and_library_paths_cannot_be_shell_fragments(self):
        self.reject(["--cc", "cc"], "explicit installed compiler")
        self.reject(["--cc", "/tmp/not-a-compiler;echo unsafe"], "explicit installed compiler")
        self.reject(["--termcap-library", "-ltermcap"], "expected one argument")
        self.reject(["--termcap-library", "relative.so"], "explicit installed termcap")


if __name__ == "__main__":
    unittest.main()
