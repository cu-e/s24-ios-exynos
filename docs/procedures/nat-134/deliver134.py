#!/usr/bin/env python3
"""NAT-134 delivery companion: docs/procedures/nat-130/deliver130.py, unchanged and loaded from its file, with the read-only
register probe (peek134.run) done on the delivery connection BEFORE the first RX_BEGIN.

Command line: everything deliver130.py takes, plus
  --no-peek        deliver exactly as NAT-130 (no PEEK request is sent)
The probe journal is OUT/peek.jsonl (one line per request/value/skip/error, fsync'd before the next request). A probe that ends
with an error stops the run: no delivery is attempted on a device whose last register read did not answer. The probe result
and its duration are added to delivery.json under "nat134"; delivery seconds include the probe, sender.seconds do not.
"""
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import peek134 as P  # noqa: E402

_spec = importlib.util.spec_from_file_location("deliver130", HERE.parent / "nat-130" / "deliver130.py")
d130 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(d130)
rs130 = d130.rs130


def _peek_usb(self, index):
    return bytes(self._wrap(self.dev.ctrl_transfer, rs130.VENDOR_IN, P.PEEK_REQ, index, P.PEEK_KEY, P.PEEK_SIZE, self.timeout_ms))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    no_peek = "--no-peek" in argv
    argv = [a for a in argv if a != "--no-peek"]
    out = None
    for i, a in enumerate(argv):
        if a == "--out" and i + 1 < len(argv):
            out = Path(argv[i + 1])
        elif a.startswith("--out="):
            out = Path(a.split("=", 1)[1])
    state = dict(done=False, result=None, seconds=None, journal=None)
    real_send = rs130.send

    def send(transport, data, **kw):
        if not no_peek and not state["done"]:
            state["done"] = True
            out.mkdir(parents=True, exist_ok=True)
            state["journal"] = str(out / "peek.jsonl")
            log = kw.get("log") or print
            t0 = time.monotonic()
            res = P.run(transport.peek, state["journal"], log=log)
            state["seconds"] = round(time.monotonic() - t0, 6)
            state["result"] = res
            if res["error"] is not None:
                raise rs130.TransportError("register probe stopped at PEEK %d (%#x %s): %s; no delivery on this device"
                                           % (res["error"]["index"], res["error"]["addr"], res["error"]["name"], res["error"]["error"]))
        return real_send(transport, data, **kw)

    rs130.PyUsbTransport130.peek = _peek_usb
    d130.Metered130.peek = lambda self, index: self.inner.peek(index)
    rs130.send = send
    try:
        rc = d130.main(argv)
    finally:
        rs130.send = real_send
    if out is not None and (out / "delivery.json").exists():
        doc = json.loads((out / "delivery.json").read_text())
        doc["nat134"] = dict(peek=not no_peek, probe_seconds=state["seconds"], journal=state["journal"], result=state["result"],
                             table_len=len(P.TABLE), sender=str(HERE / "deliver134.py"))
        tmp = out / "delivery.json.tmp"
        tmp.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
        os.replace(tmp, out / "delivery.json")
    return rc


if __name__ == "__main__":
    sys.exit(main())
