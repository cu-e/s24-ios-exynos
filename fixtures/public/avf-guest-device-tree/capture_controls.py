#!/usr/bin/env python3
"""No-guest controls for dynamic capture bounds, QMP framing and lease guards."""
import argparse
import importlib.util
import json
from pathlib import Path
import resource
import tempfile
import time

spec = importlib.util.spec_from_file_location("capture", Path(__file__).with_name("capture.py"))
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024**2, 256 * 1024**2))
    args.out.mkdir(parents=True, exist_ok=False)
    started, records = time.monotonic(), []

    def check(name, fn, reject=False):
        try:
            fn()
        except ValueError as error:
            records.append({"name": name, "pass": reject, "error": str(error)})
        else:
            records.append({"name": name, "pass": not reject})

    line = b"avfboot: device tree 0x4300c000+0x30fc boot_args 0x4301c000"
    check("actual-historical-console-extent", lambda: capture.console_extent(line))
    check("input-FDT-address-not-an-Apple-tree", lambda: capture.console_extent(b"avfboot: image 0x40200000 fdt 0x48200000+0x100000"), True)
    check("duplicate-extent", lambda: capture.console_extent(line + b"\n" + line), True)
    for name, base, size in (("lower-bound", 0x3fffffff, 1), ("upper-bound", 0x50000000, 1),
                              ("extent-crosses-RAM-end", 0x4fffffff, 2), ("zero-length", 0x43000000, 0),
                              ("oversize", 0x43000000, 0x100001), ("integer-wrap", 2**64-1, 2)):
        check(name, lambda base=base, size=size: capture.bounds(base, size), True)
    check("last-byte-in-RAM", lambda: capture.bounds(0x4fffffff, 1))
    check("maximum-admitted-length", lambda: capture.bounds(0x43000000, 0x100000))
    check("outside-owned-output", lambda: capture.owned_output("/tmp/vm027-tree.adt"), True)
    check("noncanonical-output", lambda: capture.owned_output(capture.ROOT / "artifacts/avf-guest-device-tree/a/../escape"), True)
    with tempfile.TemporaryDirectory(dir=args.out) as tmp:
        queue = Path(tmp) / "queue.json"
        for name, grant in (("no-lease", None), ("other-owner", {"id": "test", "task": "VM-027", "owner": "other"}),
                            ("other-task", {"id": "test", "task": "VM-028", "owner": capture.OWNER}),
                            ("wrong-id", {"id": "wrong", "task": "VM-027", "owner": capture.OWNER})):
            queue.write_text(json.dumps({"qemu": grant}))
            check(name, lambda: capture.check_lease(queue, "test"), True)
        queue.write_text(json.dumps({"qemu": {"id": "test", "task": "VM-027", "owner": capture.OWNER}}))
        check("exact-own-lease", lambda: capture.check_lease(queue, "test"))

    class FakeSocket:
        def __init__(self, messages):
            self.messages, self.sent = list(messages), []
        def settimeout(self, value):
            pass
        def recv(self, size):
            return self.messages.pop(0) if self.messages else b""
        def sendall(self, data):
            self.sent.append(json.loads(data))

    sock = FakeSocket([b'{"event":"STOP"}\n{"return":{"running":false,"status":"paused"},"id":1}\n'])
    transcript = []
    qmp = capture.QMP(sock, lambda: None, transcript)
    reply = qmp.command("query-status")
    records.append({"name": "QMP-event-before-matched-reply", "pass": reply == {"running": False, "status": "paused"} and sock.sent == [{"execute": "query-status", "id": 1}]})
    sock = FakeSocket([b'{"error":{"class":"GenericError"},"id":1}\n'])
    check("QMP-error-rejected", lambda: capture.QMP(sock, lambda: None, []).command("pmemsave"), True)
    check("QMP-early-close-rejected", lambda: capture.QMP(FakeSocket([]), lambda: None, []).receive(), True)
    check("QMP-oversize-reply", lambda: capture.QMP(FakeSocket([b"x" * (capture.MAX_DUMP + 1)]), lambda: None, []).receive(), True)
    report = {"outcome": "pass" if all(row["pass"] for row in records) else "fail", "controls": records,
              "elapsed_seconds": time.monotonic() - started, "capture_script_sha256": capture.digest(capture.__file__),
              "controls_sha256": capture.digest(__file__), "compiler_executed": False, "guest_executed": False}
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"outcome": report["outcome"], "controls": len(records)}))
    return 0 if report["outcome"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
