"""Run the NAT-076 engine suite (through NAT-130's regress76.py) and the NAT-130 suite (test_nat130.py) unchanged against the
NAT-134 engine and model (NAT-130's engine plus the PEEK request and the usbmon_peek32 port hook).

Both are loaded from their own files with their paths pointed at this directory; nothing in nat-076 or nat-130 is modified.
NAT-130's EXPECTED_DIFF still applies; NAT134_DIFF lists what NAT-134 changed on purpose. Any other failure is a regression.
"""
import importlib.util
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
N130 = os.path.join(HERE, "..", "nat-130")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


R76 = _load("regress76", os.path.join(N130, "regress76.py"))
R76.HERE = HERE		# load_suite_module() points the NAT-076 suite at HERE/engine and HERE/model

NAT134_DIFF = {}


def load_suites():
    rx, M = R76.load_suite_module()
    t130 = _load("test_nat130_134", os.path.join(N130, "test_nat130.py"))
    t130.ENGINE_C = os.path.join(HERE, "engine", "usbmon.c")
    t130.ENGINE_H = os.path.join(HERE, "engine", "usbmon.h")
    t130.HERE = HERE		# its build_mutant() puts HERE/engine first on the include path
    return rx, M, t130


def main():
    rx, _, t130 = load_suites()
    suite = unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromModule(rx),
                                unittest.defaultTestLoader.loadTestsFromModule(t130)])
    res = unittest.TextTestRunner(verbosity=1).run(suite)
    bad = [t.id() for t, _ in res.failures + res.errors]
    expected = dict(R76.EXPECTED_DIFF, **NAT134_DIFF)
    unexpected = [b for b in bad if b not in expected]
    print("ran %d, failed %d, unexpected %d" % (res.testsRun, len(bad), len(unexpected)))
    missing = [k for k in expected if k not in bad]
    if missing:
        print("expected differences that did not occur (the list is stale): %s" % missing)
        return 1
    for b in bad:
        print(("EXPECTED " if b not in unexpected else "REGRESSION ") + b)
    return 1 if unexpected else 0


if __name__ == "__main__":
    sys.exit(main())
