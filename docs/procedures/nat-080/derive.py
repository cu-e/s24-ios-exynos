#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-080: derive session_nat078.py (the NAT-078 session driver) from NAT-075's driver (session_nat075.py) by asserted text substitution (host only).

    derive.py             writes docs/procedures/nat-080/session_nat078.py from the NAT-075 driver, artifacts/nat-079/package-002/package.json
                          (and the build record it names) and artifacts/nat-077/padded.json
    derive.py --check     compares the committed session_nat078.py with what the derivation gives (exit 1 on a difference)

The driver is the only launcher of the one native run, so it is not imported or patched at run time: it is a plain file that a reader can open. Every
substitution is counted; a NAT-075 driver that has drifted fails here instead of being half-translated. Same method as NAT-075's derive.py.

What the derived driver adds to NAT-075's sequence (everything else is byte-for-byte NAT-075's):
  * the image, its pinned hashes, the package path, the decision-file glob (`*-nat078-...-single-run-*.md`) and the one-shot marker are NAT-079's / NAT-078's;
  * the registry gate also needs NAT-075, NAT-076, NAT-077, NAT-079 and NAT-080 done;
  * the preflight checks the padded root image (size and SHA-256, streamed), the delivery companion's self-test, and that the companion's send time plus a
    margin fits inside the loader's receive cap recorded in the build record;
  * after the collector is confirmed polling and BEFORE the single `adb reboot recovery`, the delivery companion (deliver_nat080.py) is started detached and
    its `loaded` record (the image verified and in memory) is awaited; a companion that does not report it stops the launch like the watcher and the
    collector do. The companion waits for the device by itself;
  * WATCH_S and COLLECT_S are 600 s: the loader holds until the NAT-044 deadline (360 s in this build) and Download Mode follows about 30 s later."""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent
ROOT = HERE.parents[2]
OLD_IMAGE, NEW_IMAGE = "loader-diag-xnu-bigwin-md1", "loader-diag-xnu-rx-md1"
DELIVER_WAIT_S, DELIVER_S, DELIVER_MARGIN_S = 300, 225, 15
WATCH_S = 600

DOC = '''"""NAT-078 session driver for the NAT-079 image (decision 0019): one fixed RECOVERY write, readback, collector + USB watcher + delivery companion, one reboot; no retries.

    session_nat078.py --image loader-diag-xnu-rx-md1 --out DIR [--execute | --restore]

This is the NAT-075 driver (session_nat075.py, itself NAT-067's, NAT-065's, NAT-062's, NAT-059's, NAT-057's and NAT-049's) with only these changes: the one image and its pinned hashes
come from NAT-079 package-002 (NAT-079's build packaged by NAT-044's package.py); the decision file is the agent-written
`docs/decisions/*-nat078-loader-diag-xnu-rx-md1-single-run-*.md` (exactly one, naming the RECOVERY and Image.payload hashes and decision 0019; this script never creates it);
the registry gate additionally needs NAT-075, NAT-076, NAT-077, NAT-079 and NAT-080 done; the one-shot marker lives under artifacts/nat-078; the preflight also checks the padded
root image (size, SHA-256) and the delivery companion; and the delivery companion (docs/procedures/nat-080/deliver_nat080.py) is started and confirmed BEFORE the single
`adb reboot recovery`, after the watcher and the collector. The companion streams the root image over USB once the loader's engine reports the reserve as its destination.
Everything else (the device checks, the full-hash write and readback of RECOVERY only, the watcher and the collector started and confirmed BEFORE the single
`adb reboot recovery`, the restore of the pinned stock image on any failure before the reboot) is unchanged; test_nat080.py pins that by comparing this file with the
derivation from session_nat075.py.

The default is the read-only preflight (it also runs the watcher for a second, the collector and companion self-tests, which open no device).
--restore writes only the pinned stock image without rebooting. No file is staged on the phone. After the reboot this script exits; the watcher, the collector
and the companion keep running for WATCH_S / COLLECT_S / their own bounds and the analysis is analyze_nat080.py (run separately)."""'''

CONSTANTS = '''ROOT_IMAGE=ROOT/'artifacts/nat-077/system-padded.apfs'   # the padded root image the companion streams into the md1 reserve
ROOT_SIZE=%(size)d
ROOT_SHA='%(sha)s'
DELIVER=ROOT/'docs/procedures/nat-080/deliver_nat080.py'
DELIVER_WAIT_S=%(wait)d     # how long the companion waits for the loader's engine to hand over the reserve (device enumerated +27 s in NAT-068, layout ~13 s after)
DELIVER_S=%(send)d      # and how long it sends at most, counted from the moment the device reported the reserve
DELIVER_MARGIN_S=%(margin)d  # the loader's own receive cap must exceed DELIVER_S by this much
'''

CHECKS = '''    def root_image_check():
        # Host only: the file the companion streams is exactly the padded image the decision names, and the companion stops before the loader gives up.
        h=hashlib.sha256();n=0
        with ROOT_IMAGE.open('rb') as f:
            for b in iter(lambda:f.read(1<<23),b''):h.update(b);n+=len(b)
        report['root_image']=dict(path=str(ROOT_IMAGE),bytes=n,sha256=h.hexdigest());save()
        assert n==ROOT_SIZE and h.hexdigest()==ROOT_SHA,'the padded root image is not the one the decision names'
        assert DELIVER_S+DELIVER_MARGIN_S<=cfg['RX_CAP_S'],'the companion would send past the loader receive cap'
    def deliver_selftest():
        # Host only, opens no device: the pyusb venv python runs the companion's own check.
        assert VENV_PY.exists(),'the pyusb venv python is missing: the delivery companion cannot run'
        r=subprocess.run([str(VENV_PY),'-I',str(DELIVER),'--selftest'],capture_output=True,timeout=60)
        res=json.loads(r.stdout.decode() or '{}')
        report['deliver_selftest']=dict(exit_code=r.returncode,result=res);save()
        assert r.returncode==0 and res.get('ok') is True,'delivery companion self-test failed: %r'%(res,)
'''

START = '''    def deliver_start():
        # After the collector, before the reboot: detached; the `loaded` record proves the image is verified and in memory. The companion then waits for the device by itself.
        out=a.out/'delivery';journal=out/'delivery.jsonl'
        argv=[str(VENV_PY),'-I',str(DELIVER),'--root',str(ROOT_IMAGE),'--size',str(ROOT_SIZE),'--sha256',ROOT_SHA,'--out',str(out),'--wait-s',str(DELIVER_WAIT_S),'--deliver-s',str(DELIVER_S)]
        with (a.out/'delivery.stdout').open('wb') as o,(a.out/'delivery.stderr').open('wb') as err:
            proc=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=o,stderr=err,start_new_session=True)
        started.append(proc)
        report['delivery']=dict(pid=proc.pid,out=str(out),journal=str(journal),wait_s=DELIVER_WAIT_S,deliver_s=DELIVER_S,started_at=now(),loaded_record_seen=False);save()
        for _ in range(1800):
            if any(e['event']=='loaded' for e in read_events(journal)):
                report['delivery']['loaded_record_seen']=True;save();return
            if proc.poll() is not None:break
            time.sleep(0.1)
        if proc.poll() is None:proc.terminate()
        raise RuntimeError('the delivery companion did not report the root image loaded: no reboot')
'''


def sub(text, old, new, count=1):
    assert text.count(old) == count, "expected %d of %r, found %d" % (count, old, text.count(old))
    return text.replace(old, new)


def derive_session(text75, new_sha, payload_sha, payload_len, root_size, root_sha, rx_cap_s):
    m = re.match(r'(#!.*\n(?:#.*\n)*)("""(?:.|\n)*?""")', text75)
    assert m, "no docstring after the header comments"
    old_doc = m.group(2)
    assert "NAT-075 session driver" in old_doc and old_doc.count("\n") == 14, "the NAT-075 docstring has changed shape"
    t = text75.replace(old_doc, DOC, 1)
    t = sub(t, "'%s':dict(" % OLD_IMAGE, "'%s':dict(" % NEW_IMAGE)
    t = sub(t, "NEW_SHA='c76165fbe6457932e5c459b45a63a8510bf802e72b4278e0f9cb1186edbdbd14'", "NEW_SHA='%s'" % new_sha)
    t = sub(t, "CANARY_SHA='5f39495505fd413671c6007a61ae7dab64b313014fa82a31e3302dcb89d1e25f'", "CANARY_SHA='%s'" % payload_sha)
    t = sub(t, "CANARY_LEN=21878752),", "CANARY_LEN=%d,\n        RX_CAP_S=%d)," % (payload_len, rx_cap_s))
    t = sub(t, "artifacts/nat-075/package-001", "artifacts/nat-079/package-002")
    t = sub(t, "*-nat075-%s-single-run-*.md", "*-nat078-%s-single-run-*.md")
    t = sub(t, "artifacts/nat-075/native-attempt-%s-used.json", "artifacts/nat-078/native-attempt-%s-used.json")
    t = sub(t, "WATCH_S=360", "WATCH_S=%d" % WATCH_S)
    t = sub(t, "COLLECT_S=360", "COLLECT_S=%d" % WATCH_S)
    # the constants of the delivery, after the pyusb venv line
    anchor = "VENV_PY=ROOT/'artifacts/recovery-rescue-20261110-01/venv/bin/python'"
    i = t.index(anchor)
    j = t.index("\n", i) + 1
    t = t[:j] + CONSTANTS % dict(size=root_size, sha=root_sha, wait=DELIVER_WAIT_S, send=DELIVER_S, margin=DELIVER_MARGIN_S) + t[j:]
    # the registry gate
    old_req = "'NAT-068','NAT-074')"
    new_req = "'NAT-068','NAT-074','NAT-075','NAT-076','NAT-077','NAT-079','NAT-080')"
    i = t.index("REQUIRED_DONE=")
    j = t.index("\n", i)
    line = t[i:j]
    assert line.count(old_req) == 1
    line = line.replace(old_req, new_req)
    cut = line.index("   # ")
    line = line[:cut] + "   # NAT-068: the md0 probe PID 1 ran; NAT-074/075: the big window ran; NAT-076/077/079/080: the delivery path, probe, loader and driver exist"
    t = t[:i] + line + t[j:]
    # the checks and the companion, as inner functions of main()
    t = sub(t, "    def watcher_start():\n", CHECKS + "    def watcher_start():\n")
    t = sub(t, "        raise RuntimeError('the collector did not log a poll of the USB bus: no reboot')\n",
            "        raise RuntimeError('the collector did not log a poll of the USB bus: no reboot')\n" + START)
    # the flow: preflight checks, then the companion after the collector
    t = sub(t, "                host_access();collector_selftest()\n", "                host_access();collector_selftest();deliver_selftest();root_image_check()\n")
    t = sub(t, "            watcher_start()\n            collector_start()\n", "            watcher_start()\n            collector_start()\n            deliver_start()\n")
    t = sub(t, "archive=report['collector']['archive'])));return 0", "archive=report['collector']['archive'],delivery=report['delivery']['out'])));return 0")
    assert OLD_IMAGE not in t, "a NAT-075 image name is left in the derived driver"
    code = t.replace(DOC, "")
    for left in ("nat075", "artifacts/nat-075", "analyze_nat075"):
        assert left not in code, "a NAT-075 path or glob (%s) is left in the derived driver" % left
    return t


def package_values():
    pkg = json.loads((ROOT / "artifacts/nat-079/package-002/package.json").read_text())
    img = pkg["images"][NEW_IMAGE]
    build = json.loads((ROOT / pkg["build"] / "build.json").read_text())
    padded = json.loads((ROOT / "artifacts/nat-077/padded.json").read_text())
    return (img["recovery_sha256"], img["payload_sha256"], img["payload_bytes"], padded["padded_bytes"], padded["padded_sha256"],
            build["nat079_params"]["rx_cap_s"])


def main(argv):
    text75 = (PROC / "nat-075" / "session_nat075.py").read_text()
    new = derive_session(text75, *package_values())
    out = HERE / "session_nat078.py"
    if "--check" in argv:
        return 0 if out.read_text() == new else 1
    out.write_text(new)
    out.chmod((PROC / "nat-075" / "session_nat075.py").stat().st_mode & 0o777)
    print("wrote", out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
