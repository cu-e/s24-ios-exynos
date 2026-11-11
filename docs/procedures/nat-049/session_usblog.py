#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-049 / NAT-043 session driver (decision 0019): one fixed USB-log RECOVERY write, readback, collector + USB watcher, one reboot; no retries.

    session_usblog.py --image {loader-diag-usbmon,loader-diag-usbmon-fault} --out DIR [--execute | --restore]

The image is a NAT-047 package-001 RECOVERY candidate. This is the NAT-048 driver (session_reset_canary.py) with these changes: the
pinned names come from NAT-047 package-001; the decision gate looks for the agent-written file
`docs/decisions/*-nat043-<image>-single-run-*.md` (exactly one, naming the RECOVERY and Image.payload hashes and decision 0019; this
script never creates it); the launch additionally needs the registry gate (`native` permission set by lab.py citing that very decision
file, and the tasks the decision template names as preconditions done), a udev rule that lets this user open USB 1209:0001
(host_access.py), and a collector self-test with the pyusb venv python. After the write and its full readback and BEFORE the single
`adb reboot recovery`, it starts usb_watch.py (NAT-048) and the NAT-041 collector (via collector_launch.py), both detached, and waits for
the watcher's `start` record and for the collector's first `poll` of the bus, so the host log and the collector cover the whole
window from the reboot request on. Every preflight and launch path stops before touching the phone unless the gates are open.

The default is the read-only preflight (it also runs the watcher for a second and the collector self-test, which opens no device).
--restore writes only the pinned stock image without rebooting. No file is staged on the phone. A failed write, a failed readback, a
watcher or a collector that did not start restores the stock image and never reboots. After the reboot this script exits; the watcher
and the collector keep running for WATCH_S / COLLECT_S seconds and the analysis is analyze_usblog.py (run separately)."""
from pathlib import Path
import argparse,datetime,fcntl,hashlib,json,os,subprocess,sys,time

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
SIZE=100663296
PAYLOAD_OFFSET=2048
IMAGES={
    'loader-diag-usbmon':dict(
        NEW_SHA='c6802dea4682a4bc993885bf525e2907e42e4eeebb964310da82ed79fef7212d',
        CANARY_SHA='a90a93d77ea56d22b8af555d34bc91bf8871db8f12ed071bd534d16940d08b73',  # Image.payload (loader + XNU payload + ADT)
        CANARY_LEN=21853792),
    'loader-diag-usbmon-fault':dict(
        NEW_SHA='f1a193dcac776dde004a3d1a379c26a4a365a150318bbc0a6501506ad7dfa103',
        CANARY_SHA='06281749f38bb6c8e944c3c82b4e77297b5749757e57b4d3c4d9f623b5025d77',
        CANARY_LEN=21853792),
}
PACKAGE=ROOT/'artifacts/nat-047/package-001'
STOCK=ROOT/'devices/recovery/backups/2026-11-10/recovery.img'
STOCK_SHA='96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67'
TARGET='/dev/block/sda18'
WRITE="su -c 'test -b /dev/block/sda18 && dd of=/dev/block/sda18 bs=1048576 count=100663296 iflag=count_bytes conv=notrunc,fsync'"
WATCH_S=360      # both outlive the reboot: the analyzer accepts a first record up to 300 s after it and needs the USB log to reach 120 s
COLLECT_S=360
WATCHER=ROOT/'docs/procedures/nat-048/usb_watch.py'
LAUNCHER=HERE/'collector_launch.py'
HOST_ACCESS=HERE/'host_access.py'
VENV_PY=ROOT/'artifacts/recovery-rescue-20261110-01/venv/bin/python'   # the only python with pyusb; the system python has none
REQUIRED_DONE=('NAT-039','NAT-046')   # the preconditions of nat-047/decision-template.md that the registry can show

def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def digest(b):return hashlib.sha256(b).hexdigest()

def gate(image,cfg):
    """The agent-written decision file of this image: exactly one, naming both hashes and decision 0019. Never created here."""
    found=sorted((ROOT/'docs/decisions').glob('*-nat043-%s-single-run-*.md'%image))
    assert len(found)==1,'decision file for %s is missing or ambiguous (%d found): no device access'%(image,len(found))
    text=found[0].read_text()
    for need in (cfg['NEW_SHA'],cfg['CANARY_SHA'],'decision 0019'):
        assert need in text,'decision file %s does not name %s'%(found[0].name,need)
    return found[0]

def registry_blocker(decision):
    """None when the registry opens the launch, otherwise the reason. `native` must have been set by lab.py citing this decision file."""
    state=json.loads((ROOT/'state/lab.json').read_text())
    if state['project']['permissions'].get('native') is not True:return 'registry native permission is not set: no launch'
    native=[d for d in state['project'].get('permission_decisions',[]) if d.get('scope')=='native']
    if not native or native[-1].get('value') is not True or native[-1].get('decision')!='docs/decisions/'+decision.name:
        return 'the last registry native decision does not cite %s: no launch'%decision.name
    tasks={t['id']:t for t in state['tasks']}
    missing=[t for t in REQUIRED_DONE if tasks.get(t,{}).get('status')!='done']
    if missing:return 'precondition tasks are not done: %s'%', '.join(missing)
    return None

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);p.add_argument('--image',required=True,choices=sorted(IMAGES))
    mode=p.add_mutually_exclusive_group();mode.add_argument('--execute',action='store_true');mode.add_argument('--restore',action='store_true')
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    cfg=IMAGES[a.image];NEW_SHA=cfg['NEW_SHA'];CANARY_SHA=cfg['CANARY_SHA'];CANARY_LEN=cfg['CANARY_LEN']
    CANDIDATE=PACKAGE/a.image/'recovery.img'
    report=dict(at=now(),image=a.image,mode='restore' if a.restore else 'launch' if a.execute else 'preflight',
                outcome='preflight',target=TARGET,device_write_started=False,reboot_sent=False,commands=[])
    started=[]
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
    def host_access():
        # Host only: some udev rule must give this user write access to 1209:0001, else the collector is refused at the first open.
        r=subprocess.run([sys.executable,'-I',str(HOST_ACCESS),'--check'],capture_output=True,timeout=30)
        info=json.loads(r.stdout.decode() or '{}')
        report['host_access']=info.get('found');save()
        assert r.returncode==0 and info.get('found'),'no udev rule gives this user write access to USB 1209:0001 (docs/procedures/nat-049/70-s24-usbmon.rules): the collector would be refused'
    def collector_selftest():
        # Host only, opens no device: the pyusb venv python imports pyusb, a libusb backend loads, and no 1209:0001 device is on the bus yet.
        assert VENV_PY.exists(),'the pyusb venv python is missing: the collector cannot run'
        r=subprocess.run([str(VENV_PY),'-I',str(LAUNCHER),'--selftest'],capture_output=True,timeout=60)
        res=json.loads(r.stdout.decode() or '{}')
        report['collector_selftest']=dict(exit_code=r.returncode,result=res);save()
        assert r.returncode==0 and res.get('ok') is True,'collector self-test failed: %r'%(res,)
        assert res.get('monitor_devices_now')==0,'a 1209:0001 device is already on the bus: %r'%(res.get('monitor_devices_now'),)
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
        started.append(proc)
        report['watcher']=dict(pid=proc.pid,log=str(log),seconds=WATCH_S,started_at=now(),start_record_seen=False);save()
        for _ in range(100):
            if any(e['event']=='start' for e in read_events(log)):
                report['watcher']['start_record_seen']=True;save();return
            if proc.poll() is not None:break
            time.sleep(0.1)
        if proc.poll() is None:proc.terminate()
        raise RuntimeError('the USB watcher did not log its start record: no reboot')
    def collector_start():
        # After the watcher, before the reboot: detached; the heartbeat file proves it polls the bus (the archive stays empty until a device appears).
        log=a.out/'collector-heartbeat.jsonl';archive=a.out/'archive'
        argv=[str(VENV_PY),'-I',str(LAUNCHER),'--out',str(archive),'--heartbeat',str(log),'--seconds',str(COLLECT_S)]
        with (a.out/'collector.stdout').open('wb') as out,(a.out/'collector.stderr').open('wb') as err:
            proc=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True)
        started.append(proc)
        report['collector']=dict(pid=proc.pid,archive=str(archive),heartbeat=str(log),seconds=COLLECT_S,started_at=now(),first_poll_seen=False);save()
        for _ in range(150):
            ev=[e['event'] for e in read_events(log)]
            if 'error' in ev:break
            if 'poll' in ev:
                report['collector']['first_poll_seen']=True;save();return
            if proc.poll() is not None:break
            time.sleep(0.1)
        if proc.poll() is None:proc.terminate()
        raise RuntimeError('the collector did not log a poll of the USB bus: no reboot')
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
            decision=gate(a.image,cfg);report['decision_file']=decision.name;save()
            assert digest(candidate[PAYLOAD_OFFSET:PAYLOAD_OFFSET+CANARY_LEN])==CANARY_SHA,'loader Image.payload not at its expected offset'
            if not a.restore:
                blocker=registry_blocker(decision);report['registry_blocker']=blocker;save()
                assert not (a.execute and blocker),blocker
                host_access();collector_selftest()
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
                report['outcome']='ready-read-only' if not blocker else 'ready-read-only-registry-closed';save();print(report['outcome']);return 0
            if a.restore:
                write(stock,STOCK_SHA);report['outcome']='stock-written-readback-confirmed';save();print(report['outcome']);return 0
            marker=ROOT/('artifacts/nat-049/native-attempt-%s-used.json'%a.image)
            marker.parent.mkdir(parents=True,exist_ok=True)
            with marker.open('x') as f:
                json.dump(dict(at=now(),image=a.image,image_sha256=NEW_SHA,attempt=str(a.out)),f);f.write('\n');f.flush();os.fsync(f.fileno())
            write(candidate,NEW_SHA)
            report['outcome']='candidate-written-readback-confirmed';save()
            watcher_start()
            collector_start()
            # The sole native reboot in this session. No later reboot or retry.
            report['reboot_sent']=True;report['reboot_requested_at']=now();save()
            run(['adb','reboot','recovery'])
            report['outcome']='native-attempt-started';save();print(json.dumps(dict(outcome=report['outcome'],image=a.image,image_sha256=NEW_SHA,reboot_requested_at=report['reboot_requested_at'],usb_log=report['watcher']['log'],archive=report['collector']['archive'])));return 0
        except Exception as exc:
            report['outcome']='stopped';report['error']=str(exc);save()
            if not report['reboot_sent']:
                for proc in started:
                    if proc.poll() is None:proc.terminate()
            if report['device_write_started'] and not report['reboot_sent'] and not a.restore:
                try:
                    if dd_idle():
                        write(stock,STOCK_SHA);report['outcome']='launch-aborted-stock-restored';save()
                except Exception as restore_exc:
                    report['restore_error']=str(restore_exc);save()
            print(json.dumps(dict(outcome=report['outcome'],error=report.get('error'),restore_error=report.get('restore_error'))));return 2

if __name__=='__main__':sys.exit(main())
