"""Execute the source-derived watchdog register fixtures under sanitizers."""
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[1]
class WatchdogTests(unittest.TestCase):
    def test_register_protocol(self):
        with tempfile.TemporaryDirectory() as d:
            exe = str(Path(d)/'wdt')
            subprocess.run(['clang','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                '-I'+str(ROOT/'src/native/watchdog'),str(ROOT/'src/native/watchdog/s5e9945.c'),
                str(ROOT/'docs/procedures/nat-007/test.c'),'-o',exe],check=True)
            subprocess.run([exe],check=True)
