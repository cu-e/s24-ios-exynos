#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-081: which boot of a collector archive is judged when the archive holds more than one boot of the same device.

Observed in NAT-078 (artifacts/nat-078/run-001/archive): the loader's USB engine restarts after the receive phase, the collector's first read session ends
`unresponsive` with one `start-failed` capture error, and ~15 s later a second session starts. The loader announces it with an explicit producer boot marker, and its
ring is REPLAYED from device sequence 0: boot 2's first 187 records are byte-for-byte boot 1's, followed by 173 new ones (the kernel's text). The shipped chain
(analyze_usblog -> analyze_nat059 -> analyze_nat065 -> analyze_nat080) takes `mine[0]`, the first boot, so it judged 187 records without the kernel text.

The rule written here, and nothing else:

  * boots are grouped by device id (the part of the directory name after the second dash: the producer nonce is the middle part and differs between sessions);
  * a group with more than one boot is a REPLAY CHAIN when, for every consecutive pair (earlier, later): the later boot's ring records start at device sequence 0 and are
    contiguous, they begin with exactly the earlier boot's records (same device sequence, kind, text, stage, exception words), the later one has at least as many, and the
    later boot's first frame arrived no earlier than the earlier boot's last frame. The judged boot is the last one of the chain; the earlier ones are *superseded* (their records
    are all in it, so nothing they held is lost);
  * a group that is not a replay chain (a boot of a different run, records that differ, an overlap in time, a gap in the sequence) is left alone: the shipped chain judges it
    as before (and reports `N boots of this image`);
  * `start-failed` capture errors are accepted only when they lie between the last frame of the first superseded boot and the first frame of the judged boot (the read that
    failed was the one that was ending the superseded session), and only when the manifest's error count equals the number of accepted ones; the manifest is then shown to the
    analysis as `complete-received-stream` with zero errors, and the original outcome and errors are returned in `info`. Any other capture error stays as the shipped chain reports it.

What it cannot show: that the replay is the whole ring (the later boot's own `dev_seq_contiguous` and the chain rules of NAT-059/NAT-062 decide that) or that the loader did
not lose bytes between the sessions (the replay starts at sequence 0, so a loss would show as a difference in the shared prefix, which is refused)."""
from pathlib import Path

RING_KINDS = ("log", "stage", "fault")
ACCEPTED_ERROR = "start-failed"
LAST = {}            # the decision of the latest load_archive() call, for the analyser that wants to print it


def record_keys(a49, root, name):
    """The ring records of one boot as comparable tuples, read from the boot's own frames.jsonl."""
    rows, _ = a49.load_boot(Path(root) / "boots" / name)
    out = []
    for r in rows:
        f = r["frame"]
        if f["kind"] in RING_KINDS and "dev_seq" in f:
            out.append((f["dev_seq"], f["kind"], f.get("text"), f.get("stage"), f.get("esr"), f.get("elr"), f.get("far")))
    return out


def replay_chain(a49, root, group):
    """`group`: the boots (summaries from analyze_usblog.summarize_boot) of one device id, in archive order.
    -> (judged boot, [superseded boots], None) or (None, [], reason)."""
    boots = sorted(group, key=lambda b: b["index"] if b["index"] is not None else 0)
    keys = {b["name"]: record_keys(a49, root, b["name"]) for b in boots}
    for earlier, later in zip(boots, boots[1:]):
        e, l = keys[earlier["name"]], keys[later["name"]]
        if not e or not l:
            return None, [], "boot %s or %s has no ring records" % (earlier["name"][:6], later["name"][:6])
        if later["first_dev_seq"] != 0 or not later["dev_seq_contiguous"]:
            return None, [], "boot %s does not start at device sequence 0 or is not contiguous: it is not a replay" % later["name"][:6]
        if len(l) < len(e) or l[:len(e)] != e:
            return None, [], "boot %s does not begin with all of boot %s's records: it is not a replay of it" % (later["name"][:6], earlier["name"][:6])
        if later["first_received_unix"] < earlier["last_received_unix"]:
            return None, [], "boot %s began before boot %s ended: the two overlap in time" % (later["name"][:6], earlier["name"][:6])
    return boots[-1], boots[:-1], None


def install(a49):
    """Wrap `a49.load_archive` so that the archive it returns shows the judged boot of each replay chain and not the superseded ones. -> a function that undoes it.
    Every decision is recorded in arch["nat081"]."""
    original = a49.load_archive

    def load_archive(root):
        arch, err = original(root)
        if arch is None:
            return arch, err
        info = dict(applied=False, groups=[], accepted_errors=[], note=None)
        arch["nat081"] = info
        LAST["info"] = info
        groups = {}
        for b in arch["boots"]:
            groups.setdefault(b["device_id"], []).append(b)
        drop = []
        for dev, group in groups.items():
            if len(group) < 2:
                continue
            judged, superseded, why = replay_chain(a49, root, group)
            info["groups"].append(dict(device_id_tail=(dev or "")[-8:], boots=[b["name"][:6] for b in group], replay=judged is not None, why_not=why,
                                       judged=judged["name"][:6] if judged else None, superseded=[b["name"][:6] for b in superseded]))
            drop += superseded
        if not drop:
            return arch, err
        lo = min(b["last_received_unix"] for b in drop)
        hi = min(b["first_received_unix"] for b in arch["boots"] if b not in drop and b["device_id"] == drop[0]["device_id"])
        events = arch["events"]
        errs = [e for e in events if e.get("kind") == "capture-error"]
        accepted = [e for e in errs if e.get("reason") == ACCEPTED_ERROR and lo - 1.0 <= a49.ts(e["utc"]) <= hi]
        m = arch["manifest"]
        if m is not None and m.get("outcome") == "incomplete" and m.get("errors") == len(accepted) and len(accepted) == len(errs):
            info["manifest_original"] = dict(outcome=m.get("outcome"), errors=m.get("errors"))
            arch["manifest"] = dict(m, outcome="complete-received-stream", errors=0, nat081_adjusted=True)
            arch["capture_errors"] = []
            info["accepted_errors"] = [dict(reason=e["reason"], utc=e["utc"], detail=e.get("detail")) for e in accepted]
        info["applied"] = True
        info["note"] = "boots %s are replays and were superseded by the last boot of their chain" % ",".join(b["name"][:6] for b in drop)
        arch["boots"] = [b for b in arch["boots"] if b not in drop]
        return arch, err

    a49.load_archive = load_archive
    return lambda: setattr(a49, "load_archive", original)
