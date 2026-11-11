#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-066: write the committable copies of one run's analysis and kernel log (same rules as NAT-063's errata-free copy).

    sanitize_run.py RUN_DIR OUT_DIR

Reads RUN_DIR/{kernel-log.txt,analysis.json,usb-events.jsonl} and writes OUT_DIR/run-001-{kernel-log.txt,analysis.json,usb-events.jsonl}.
The kernel log: the builder account inside the kernel version string becomes <builder>:<tree>, the ECID and the two UUIDs of the panic header become
placeholders, and the binary stackshot data (kcd) that ends the panic buffer is cut. The analysis: the dump texts are removed. Each replacement is asserted
to happen the expected number of times; the raw files stay in the gitignored artifacts directory."""
import json
import re
import sys
from pathlib import Path


def sanitize_log(raw: bytes) -> str:
    mark = raw.find(b"PMOC")
    assert mark > 0 and raw.count(b"PMOC") == 1, "no single binary stackshot marker: the text part cannot be separated"
    cut = raw.rfind(b"\n", 0, mark) + 1      # the start of the line that carries the marker
    text = raw[:cut].decode("utf-8").replace("\r", "")
    tail = len(raw) - cut
    text, n = re.subn(r"(; )[A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+(/STR\d+VERSION)", r"\1<builder>:<tree>\2", text)
    assert n == 2, n
    text, n = re.subn(r"^ECID: [0-9A-Fa-f]+$", "ECID: <redacted>", text, flags=re.M)
    assert n == 1, n
    text, n = re.subn(r"^(Kernel UUID|Boot session UUID): [0-9A-Fa-f-]{36}$", r"\1: <redacted>", text, flags=re.M)
    assert n == 2, n
    text = text.rstrip("\n") + "\n--- end of the text part; the rest of the panic buffer (%d bytes of the reconstructed file) is the kernel's binary stackshot data (kcd) and is kept only in the gitignored artifacts ---\n" % tail
    return text


def main(argv):
    run, out = Path(argv[1]), Path(argv[2])
    out.mkdir(parents=True, exist_ok=True)
    text = sanitize_log((run / "kernel-log.txt").read_bytes())
    raw_text = (run / "kernel-log.txt").read_bytes().decode("utf-8", "replace")
    secrets = re.findall(r"^ECID: ([0-9A-Fa-f]+)$", raw_text, flags=re.M) + re.findall(r"UUID: ([0-9A-Fa-f-]{36})$", raw_text, flags=re.M)
    assert len(secrets) == 3, secrets
    for bad in secrets + ["egor", "/home/"]:
        assert bad not in text, "the sanitized text still contains a value that was to be removed"
    assert not re.search(r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-", text), "a UUID is left"
    (out / "run-001-kernel-log.txt").write_text(text, newline="")
    a = json.loads((run / "analysis.json").read_text())
    a["kernel_log"]["texts"] = "removed from this copy: the dump texts contain the owner's account name, an ECID and UUIDs; the sanitized text is run-001-kernel-log.txt, the full text is in the gitignored artifacts"
    (out / "run-001-analysis.json").write_text(json.dumps(a, indent=1, default=str) + "\n")
    (out / "run-001-usb-events.jsonl").write_bytes((run / "usb-events.jsonl").read_bytes())
    print("wrote", out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
