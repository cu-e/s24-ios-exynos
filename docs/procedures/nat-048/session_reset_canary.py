#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-048 / NAT-046 session driver (decision 0019): one fixed reset-canary RECOVERY write, readback, USB watcher, one reboot; no retries.

    session_reset_canary.py --image {loader-diag-reset,loader-diag-reset-bl} --out DIR [--execute | --restore]

The image is a NAT-044 package-002 RECOVERY candidate. This is the NAT-037 driver (session_xnu_ckpt3.py) with three changes: the
pinned names come from NAT-044 package-002 (one table entry per image); the decision gate looks for the agent-written decision
file `docs/decisions/*-nat046-<image>-single-run-*.md` (exactly one, naming the RECOVERY and Image.payload hashes and decision 0019;
this script never creates it); and, after the write and its full readback and before the single `adb reboot recovery`, it starts
usb_watch.py detached and waits for its `start` record, so the host log covers the whole window from the reboot request on.
Every preflight and launch path stops before touching the phone unless the gate is open.

The default is the read-only preflight (it also runs the watcher for a second to prove it works before anything is written).
--restore writes only the pinned stock image without rebooting. No file is staged on the phone. A failed write, a failed readback
or a watcher that did not start restores the stock image and never reboots. After the reboot this script exits; the watcher keeps
running for WATCH_S seconds and the analysis is analyze_reset.py (run separately).
"""
from pathlib import Path
import argparse,datetime,fcntl,hashlib,json,os,subprocess,sys,time

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
SIZE=100663296
PAYLOAD_OFFSET=2048
IMAGES={
    'loader-diag-reset':dict(
        NEW_SHA='a3189ca7914b48b0b5d3a575c2936b6425bccdafde16e66c34fedf1f3d1ea34e',
        CANARY_SHA='b79aeecc689c02c7a95ee487fb4a4b808ef8915292e0888122de9be983acaa14',  # Image.payload (loader + XNU payload + ADT)
        CANARY_LEN=21771872),
    'loader-diag-reset-bl':dict(
        NEW_SHA='d4e1454c198379328c91fc63a5aaf26e58c1747e2b696ca1b92719211bedfebd',
        CANARY_SHA='b05349eb5bc048c3b78694c3f14b3e58def30a7f74b45bd0f3b6d229fb6ef936',
        CANARY_LEN=21771872),
}
PACKAGE=ROOT/'artifacts/nat-044/package-002'
STOCK=ROOT/'devices/recovery/backups/2026-11-10/recovery.img'
STOCK_SHA='96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67'
TARGET='/dev/block/sda18'
WRITE="su -c 'test -b /dev/block/sda18 && dd of=/dev/block/sda18 bs=1048576 count=100663296 iflag=count_bytes conv=notrunc,fsync'"
WATCH_S=240      # the watcher outlives the reboot by about this long: SEC_UPLOAD came at about +95 s and left at about +118 s in runs 001-009
WATCHER=HERE/'usb_watch.py'

def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def digest(b):return hashlib.sha256(b).hexdigest()

def gate(image,cfg):
    """The agent-written decision file of this image: exactly one, naming both hashes and decision 0019. Never created here."""
    found=sorted((ROOT/'docs/decisions').glob('*-nat046-%s-single-run-*.md'%image))
    assert len(found)==1,'decision file for %s is missing or ambiguous (%d found): no device access'%(image,len(found))
    text=found[0].read_text()
    for need in (cfg['NEW_SHA'],cfg['CANARY_SHA'],'decision 0019'):
        assert need in text,'decision file %s does not name %s'%(found[0].name,need)
    return found[0]

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);p.add_argument('--image',required=True,choices=sorted(IMAGES))
    mode=p.add_mutually_exclusive_group();mode.add_argument('--execute',action='store_true');mode.add_argument('--restore',action='store_true')
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    cfg=IMAGES[a.image];NEW_SHA=cfg['NEW_SHA'];CANARY_SHA=cfg['CANARY_SHA'];CANARY_LEN=cfg['CANARY_LEN']
    CANDIDATE=PACKAGE/a.image/'recovery.img'
    report=dict(at=now(),image=a.image,mode='restore' if a.restore else 'launch' if a.execute else 'preflight',
                outcome='preflight',target=TARGET,device_write_started=False,reboot_sent=False,commands=[])
    def save():
        with (a.out/'report.json').open('w') as f:
            json.dump(report,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    def run(argv,data=None,timeout=30):
        row=dict(argv=argv,started_at=now(),input_bytes=len(data) if data is not None else 0)
        report['commands'].append(row);save()
        try:
            r=subprocess.run(argv,input=data,capture_output=True,timeout=timeout)
            row.update(exit_code=r.returncode,stdout=r.stdout.decode(errors='replace'),stderr=r.stderr.decode(errors='replace'),finished_at=now());save()
        except Exception as exc:
            row.update(error=str(exc),finished_at=now());save();raise
        if r.returncode:raise RuntimeError(f'command failed: {argv}; exit {r.returncode}')
        return r.stdout.decode().strip()
    def shell(cmd,timeout=30):return run(['adb','shell','-T',cmd],timeout=timeout)
    def device_hash():return shell("su -c 'sha256sum /dev/block/sda18'",120).split()[0]
    def dd_idle():
        # No restoration is launched alongside an unconfirmed remote writer.
        result=shell("su -c 'if pidof dd >/dev/null; then echo busy; else echo idle; fi'")
        return result=='idle'
    def write(data,expected):
        assert len(data)==SIZE and digest(data)==expected
        assert dd_idle(), 'a remote dd process is still running'
        report['device_write_started']=True;save()
        run(['adb','shell','-T',WRITE],data=data,timeout=120)
        measured=device_hash();report['readback_sha256']=measured;save()
        assert measured==expected,'full RECOVERY readback mismatch'
    def watcher_argv(out,seconds):return [sys.executable,'-I',str(WATCHER),'--out',str(out),'--seconds',str(seconds)]
    def read_events(path):
        try:return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
        except (OSError,ValueError):return []
    def watcher_selftest():
        # Before anything is written: the watcher must start, log its start record and stop cleanly.
        log=a.out/'usb-selftest.jsonl'
        r=subprocess.run(watcher_argv(log,1),capture_output=True,timeout=30)
        ev=[e['event'] for e in read_events(log)]
        report['watcher_selftest']=dict(exit_code=r.returncode,events=ev);save()
        assert r.returncode==0 and ev[:1]==['start'] and ev[-1:]==['stop'],'usb_watch.py self-test failed: %r'%(ev,)
    def watcher_start():
        # After the readback, before the reboot: detached, so it outlives this script, and its start record is awaited.
        log=a.out/'usb-events.jsonl'
        with (a.out/'usb-watch.stderr').open('wb') as err:
            proc=subprocess.Popen(watcher_argv(log,WATCH_S),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=err,start_new_session=True)
        report['watcher']=dict(pid=proc.pid,log=str(log),seconds=WATCH_S,started_at=now(),start_record_seen=False);save()
        for _ in range(100):
            if any(e['event']=='start' for e in read_events(log)):
                report['watcher']['start_record_seen']=True;save();return
            if proc.poll() is not None:break
            time.sleep(0.1)
        if proc.poll() is None:proc.terminate()
        raise RuntimeError('the USB watcher did not log its start record: no reboot')
    lockpath=ROOT/'artifacts/nat-022/recovery-write.lock';lockpath.parent.mkdir(parents=True,exist_ok=True)
    with lockpath.open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            stock=STOCK.read_bytes();candidate=CANDIDATE.read_bytes()
            assert len(stock)==len(candidate)==SIZE and digest(stock)==STOCK_SHA and digest(candidate)==NEW_SHA
            pkg=json.loads((PACKAGE/'package.json').read_text())
            img=pkg['images'][a.image]
            assert img['recovery_sha256']==NEW_SHA and img['payload_sha256']==CANARY_SHA and img['payload_bytes']==CANARY_LEN and img['payload_offset']==PAYLOAD_OFFSET
            assert pkg['stock_sha256']==STOCK_SHA and pkg['flashed'] is False
            report['decision_file']=gate(a.image,cfg).name;save()
            assert digest(candidate[PAYLOAD_OFFSET:PAYLOAD_OFFSET+CANARY_LEN])==CANARY_SHA,'loader Image.payload not at its expected offset'
            assert run(['adb','get-state'])=='device'
            assert shell('getprop ro.product.model')=='SM-S921B'
            assert shell('getprop ro.product.device')=='e1s'
            assert shell('getprop ro.build.PDA')=='S921BXXS9BYH3'
            assert shell('getprop sys.boot_completed')=='1'
            identity=shell("su -c 'readlink -f /dev/block/by-name/recovery; blockdev --getsize64 /dev/block/sda18; test -b /dev/block/sda18 && echo block_device'")
            assert identity.splitlines()==[TARGET,str(SIZE),'block_device'],identity
            assert dd_idle()
            initial=device_hash();report['initial_recovery_sha256']=initial;save()
            if not a.restore: assert initial==STOCK_SHA, 'launch requires unchanged stock RECOVERY'
            battery=shell("dumpsys battery | toybox sed -n 's/^  level: /level=/p;s/^  temperature: /temperature=/p'")
            report['battery']=battery;save()
            values=dict(line.split('=',1) for line in battery.splitlines())
            assert int(values['level'])>=50 and int(values['temperature'])<420
            processes=subprocess.check_output(['ps','-eo','comm'],text=True).splitlines()
            assert not any(s.strip().lower() in ['odin4','heimdall'] for s in processes),'another flasher is active'
            if not a.restore:watcher_selftest()
            if not (a.execute or a.restore):
                report['outcome']='ready-read-only';save();print(report['outcome']);return 0
            if a.restore:
                write(stock,STOCK_SHA);report['outcome']='stock-written-readback-confirmed';save();print(report['outcome']);return 0
            marker=ROOT/('artifacts/nat-048/native-attempt-%s-used.json'%a.image)
            marker.parent.mkdir(parents=True,exist_ok=True)
            with marker.open('x') as f:
                json.dump(dict(at=now(),image=a.image,image_sha256=NEW_SHA,attempt=str(a.out)),f);f.write('\n');f.flush();os.fsync(f.fileno())
            write(candidate,NEW_SHA)
            report['outcome']='candidate-written-readback-confirmed';save()
            watcher_start()
            # The sole native reboot in this session. No later reboot or retry.
            report['reboot_sent']=True;report['reboot_requested_at']=now();save()
            run(['adb','reboot','recovery'])
            report['outcome']='native-attempt-started';save();print(json.dumps(dict(outcome=report['outcome'],image=a.image,image_sha256=NEW_SHA,reboot_requested_at=report['reboot_requested_at'],usb_log=report['watcher']['log'])));return 0
        except Exception as exc:
            report['outcome']='stopped';report['error']=str(exc);save()
            if report['device_write_started'] and not report['reboot_sent'] and not a.restore:
                try:
                    if dd_idle():
                        write(stock,STOCK_SHA);report['outcome']='launch-aborted-stock-restored';save()
                except Exception as restore_exc:
                    report['restore_error']=str(restore_exc);save()
            print(json.dumps(dict(outcome=report['outcome'],error=report.get('error'),restore_error=report.get('restore_error'))));return 2

if __name__=='__main__':sys.exit(main())
