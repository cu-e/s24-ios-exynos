"""Run the NAT-076 engine suite (docs/procedures/nat-076/test_rx.py, unchanged) against the NAT-130 engine and model.

The suite is loaded from its own file with its module globals pointed at this directory's engine/ and model/; nothing in
nat-076 is modified. Expected differences (tests whose subject NAT-130 changed on purpose) are listed in EXPECTED_DIFF with
the reason; any other failure is a regression.
"""
import importlib.util
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
N76 = os.path.join(HERE, "..", "nat-076")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def load_suite_module():
    sys.path.insert(0, N76)
    _load("cdefs", os.path.join(N76, "cdefs.py"))
    M = _load("modelhost", os.path.join(N76, "modelhost.py"))
    M.ENGINE = os.path.join(HERE, "engine")
    M.MODEL = os.path.join(HERE, "model")
    rx = _load("test_rx76", os.path.join(N76, "test_rx.py"))
    rx.ENGINE_C = os.path.join(HERE, "engine", "usbmon.c")
    rx.ENGINE_H = os.path.join(HERE, "engine", "usbmon.h")
    rx.REGS_H = os.path.join(HERE, "engine", "dwc3_regs.h")
    rx.HERE = HERE         # build_mutant() puts HERE/engine first on the include path
    return rx, M


_FLAGS = "RX_BEGIN flags = 1 is checksum mode FAST in NAT-130 (direct mode), so it is accepted; other flag values still stall (test_nat130 FlagTests)"
_TEXT = ("the defect's source text is no longer unique or present in the NAT-130 engine (the SUM request repeats the length checks, the "
         "flags check now masks the mode bits); test_nat130 SeededDefectTests re-seeds the same defect against the new text")
EXPECTED_DIFF = {
    "test_rx76.DirectProtocolTests.test_every_byte_of_the_flags_counts (flags='0x1')": _FLAGS,
    "test_rx76.DirectProtocolTests.test_every_byte_of_the_flags_counts": _FLAGS,
    "test_rx76.DirectProtocolTests.test_refusals_leave_the_state_alone [flags set]": _FLAGS,
    "test_rx76.DirectProtocolTests.test_refusals_leave_the_state_alone": _FLAGS,
    "test_rx76.ScenarioHealthTests.test_every_scenario_is_clean_on_the_real_engine (scenario='sc_refusals', direct=True)": _FLAGS,
    "test_rx76.SeededDefectTests.test_chunk_limit_ignored": _TEXT,
    "test_rx76.SeededDefectTests.test_flags_ignored": _TEXT,
    "test_rx76.SeededDefectTests.test_length_not_a_packet_multiple_accepted": _TEXT,
}


def main():
    rx, _ = load_suite_module()
    suite = unittest.defaultTestLoader.loadTestsFromModule(rx)
    res = unittest.TextTestRunner(verbosity=1).run(suite)
    bad = [t.id() for t, _ in res.failures + res.errors]
    unexpected = [b for b in bad if b not in EXPECTED_DIFF]
    print("ran %d, failed %d, unexpected %d" % (res.testsRun, len(bad), len(unexpected)))
    missing = [k for k in EXPECTED_DIFF if k not in bad]
    if missing:
        print("expected differences that did not occur (the list is stale): %s" % missing)
        return 1
    for b in bad:
        print(("EXPECTED " if b not in unexpected else "REGRESSION ") + b)
    return 1 if unexpected else 0


if __name__ == "__main__":
    sys.exit(main())
