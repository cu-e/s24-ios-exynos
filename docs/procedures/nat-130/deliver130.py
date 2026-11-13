#!/usr/bin/env python3
"""NAT-130 delivery companion: docs/procedures/nat-080/deliver_nat080.py, unchanged and loaded from its file, run with the NAT-130
sender (root_send130.py) in place of tools/ios/root_send.py and a metered transport that also passes the NAT-130 requests through.

Command line: everything deliver_nat080.py takes, plus
  --policy auto|plain|fast|cached   (default auto)    --none-chunks N   (default 4)
The defaults of --chunk (8 MiB) and --write-size (here also 8 MiB: one bulk write per chunk) are passed explicitly by the session
driver. The sender's per-chunk records and phase summary end up in delivery.json under "sender" and "phases".
"""
import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import root_send130 as rs130  # noqa: E402

_spec = importlib.util.spec_from_file_location("deliver_nat080", HERE.parent / "nat-080" / "deliver_nat080.py")
d80 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(d80)


class Metered130(d80.MeteredTransport):
    def rx_begin(self, offset, length, flags=0):
        self._check()
        return self.inner.rx_begin(offset, length, flags)

    def get_rxt(self):
        return self.inner.get_rxt()

    def sum_req(self, offset, length, mode):
        return self.inner.sum_req(offset, length, mode)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--policy", default="auto", choices=("auto", "plain", "fast", "cached"))
    ap.add_argument("--none-chunks", type=int, default=4)
    own, rest = ap.parse_known_args(argv)
    send_v2 = rs130.send

    cache = {}

    def send(transport, data, **kw):
        kw.setdefault("policy", own.policy)
        kw.setdefault("none_chunks", own.none_chunks)
        sc = cache.get(id(data))
        if sc is None or sc.chunk != kw.get("chunk"):
            sc = rs130.SumCache(data, kw.get("base", 0), kw["chunk"])
        kw.setdefault("sums", sc)
        return send_v2(transport, data, **kw)

    real_deliver = d80.deliver

    def deliver(rs, data, open_probe, open_send, journal, wait_s, deliver_s, chunk, write_size, progress_bytes, **kw):
        # start the host checksums while the companion still waits for the loader (NAT-127: ~32 s from start to "ready")
        cache[id(data)] = rs130.SumCache(data, 0, chunk)
        journal.emit("sumcache-started", chunk=chunk)
        return real_deliver(rs, data, open_probe, open_send, journal, wait_s, deliver_s, chunk, write_size, progress_bytes, **kw)

    mod = type(sys)("root_send130_bound")
    mod.__dict__.update({k: v for k, v in vars(rs130).items() if not k.startswith("__")})
    mod.send = send
    d80.load_sender = lambda: mod
    d80.MeteredTransport = Metered130
    d80.deliver = deliver
    rc = d80.main(rest)
    out = None
    for i, a in enumerate(rest):
        if a == "--out" and i + 1 < len(rest):
            out = Path(rest[i + 1])
        elif a.startswith("--out="):
            out = Path(a.split("=", 1)[1])
    if out is not None and (out / "delivery.json").exists():
        doc = json.loads((out / "delivery.json").read_text())
        if doc.get("sender"):
            doc["phases"] = rs130.summarize(doc["sender"])
        doc["nat130"] = dict(policy=own.policy, none_chunks=own.none_chunks, sender=str(HERE / "root_send130.py"))
        tmp = out / "delivery.json.tmp"
        tmp.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
        os.replace(tmp, out / "delivery.json")
    return rc


if __name__ == "__main__":
    sys.exit(main())
