"""Run NAT-130's Unicorn port tests (test_port130.py, unchanged) against the NAT-134 engine directory (its port_aarch64.h gained
usbmon_peek32; the CACHED window code is NAT-130's). Needs the nat-065 venv (unicorn)."""
import importlib.util
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("test_port130_134", os.path.join(HERE, "..", "nat-130", "test_port130.py"))
T = importlib.util.module_from_spec(spec)
sys.modules["test_port130_134"] = T
spec.loader.exec_module(T)
T.ENGINE = os.path.join(HERE, "engine")

if __name__ == "__main__":
    r = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromModule(T))
    sys.exit(0 if r.wasSuccessful() else 1)
