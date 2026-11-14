#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-186 session driver for the NAT-185 image (decisions 0019/0044/0061; loader-diag-xnu-scV-md1: scU with a read-only per-process CPU-time sampler (NAT-185 kernel); scU was scS with the framebuffer driver's nearest-neighbour scaling copying a per-layer run table of consecutive picture columns with memcpy (NAT-183 kernel); scS was scR with a read-only display-layer snapshot gated on PMU DPUB/DPUF0/DPUF1 status (NAT-176 kernel); scR was scQ with a synthetic home-screen swipe thread 215-375 s (finger 9, NAT-174 kernel) and touch_lat=1 in place of cpuload=1000; scQ was scO with a cpu0 clock probe and one stock FREQ_REQ 1959000 kHz on APM channel 0 (NAT-172 kernel); scO was scN with the touch GPP9 DAT shadowed and the poll gated on gpa1-2 (NAT-169 kernel); scN was scM with the touch SPI half-bit 8; scM was scJ with cpuload=1000 and the NAT-165 kernel; scJ was scH with boot-arg fb_filter=0 (nearest-neighbour scaling) in place of rec_secs=270 rec_mb=64, and NAT-157's loader message fix; scH was scF with the NAT-152 kernel (NAT-150's early marks out of line, every loader-checked kernel address in place, 1 s start wait) and small_cores=0 (no slow-core pairing); scF was scE with cpu1-cpu9 state "waiting" (one boot CPU); scE was scD with all ten CPUs (ADT cpu0-cpu9, no cpus=1); scD was scC with the NAT-143 touch kernel (every press/release logged), loader_return_after=270, rec_secs=270 and a 595 s loader deadline; scC was scB with the NAT-141 touch kernel (Samsung screen-on STM start sequence and a polled event thread); scB was scA with the NAT-139 touch kernel (USI SPI9 pad order CLK gpp9-0 / MISO gpp9-2, read-only MISO level check) and msgbuf=1048576; scA was the NAT-128 polling-only touch ID kernel with e1spmic=2 (touch rails LDO18/LDO9, exact readbacks) and e1skeys=0 on the us1 loader (NAT-130 engine); sc9 was NAT-119's image with the PMIC init disabled (e1spmic=0), NAT-125 touch IRQ admission guard and /dev/hakios-touch, `loader_return_after=150`, `rec_secs=150`, `deadline_s=475`; derived from session_nat119.py by derive121.py): one fixed RECOVERY write, readback, collector + USB watcher + delivery companion, one reboot; no retries.

Derived from docs/procedures/nat-108/session_nat108.py by docs/procedures/nat-110/derive110.py (counted substitutions; `derive110.py --check`); the execution body below is NAT-108's / NAT-106's / NAT-078's unchanged.

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
and the companion keep running for WATCH_S / COLLECT_S / their own bounds and the analyses are analyze_nat110.py plus decode113.py (--mode stage-c, stage-b, hb, stage-a and chain over NAT-110's 8192+524288 return window) (run separately)."""
from pathlib import Path
import argparse,datetime,fcntl,hashlib,json,os,subprocess,sys,time

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
SIZE=100663296
PAYLOAD_OFFSET=2048
IMAGES={
    'loader-diag-xnu-scV-md1':dict(
        NEW_SHA='57ab39447993b83b48e4afef2674ec0ead000de87f609729c9c9f01be907b27e',
        CANARY_SHA='117aafcc15c8e78e1c04707c1921a962bd680678cd3b3090ed0a8803943c7a88',  # Image.payload (loader + XNU payload + ADT)
        CANARY_LEN=26208032,
        RX_CAP_S=240),
}
PACKAGE=ROOT/'artifacts/nat-185/package-001'
STOCK=ROOT/'devices/recovery/backups/2026-11-10/recovery.img'
STOCK_SHA='96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67'
TARGET='/dev/block/sda18'
WRITE="su -c 'test -b /dev/block/sda18 && dd of=/dev/block/sda18 bs=1048576 count=100663296 iflag=count_bytes conv=notrunc,fsync'"
WATCH_S=720      # both outlive the reboot: the analyzer accepts a first record up to 300 s after it and needs the USB log to reach 120 s
COLLECT_S=720
WATCHER=ROOT/'docs/procedures/nat-048/usb_watch.py'
LAUNCHER=ROOT/'docs/procedures/nat-049/collector_launch.py'
HOST_ACCESS=ROOT/'docs/procedures/nat-049/host_access.py'
VENV_PY=ROOT/'artifacts/recovery-rescue-20261110-01/venv/bin/python'   # the only python with pyusb; the system python has none
ROOT_IMAGE=ROOT/'artifacts/nat-083/system-padded.apfs'   # the padded root image the companion streams into the md1 reserve
ROOT_SIZE=2475720704
ROOT_SHA='4377e98854753f648afde01d884bde352f316acad172eb5e46d44717954262f6'
DELIVER=ROOT/'docs/procedures/nat-130/deliver130.py'
DELIVER_WAIT_S=300     # how long the companion waits for the loader's engine to hand over the reserve (device enumerated +27 s in NAT-068, layout ~13 s after)
DELIVER_S=225      # and how long it sends at most, counted from the moment the device reported the reserve
DELIVER_MARGIN_S=15  # the loader's own receive cap must exceed DELIVER_S by this much
REQUIRED_DONE=('NAT-039','NAT-046','NAT-043','NAT-052','NAT-058','NAT-059','NAT-060','NAT-062','NAT-063','NAT-064','NAT-065','NAT-066','NAT-067','NAT-068','NAT-074','NAT-075','NAT-076','NAT-077','NAT-079','NAT-080','NAT-070','NAT-083','NAT-084','NAT-085','NAT-087','NAT-089','NAT-090','NAT-092','NAT-096','NAT-097','NAT-101','NAT-102','NAT-104','NAT-105','NAT-106','NAT-107','NAT-108','NAT-109','NAT-110','NAT-111','NAT-112','NAT-113','NAT-114','KRN-044','NAT-071','NAT-115','NAT-116','NAT-117','NAT-118','NAT-119','NAT-120','NAT-121','NAT-122','NAT-123','NAT-125','NAT-126','NAT-127','NAT-128','NAT-129','NAT-130','NAT-132','NAT-139','NAT-140','NAT-141','NAT-142','NAT-143','NAT-144','NAT-145','NAT-148','NAT-150','NAT-152','NAT-153','NAT-156','NAT-157','NAT-158','NAT-159','NAT-166','NAT-167','NAT-168','NAT-169','NAT-170','NAT-171','NAT-172','NAT-173','NAT-174','NAT-175','NAT-176','NAT-177','NAT-180','NAT-181','NAT-182','NAT-183','NAT-184','NAT-185')   # NAT-068: the md0 probe PID 1 ran; NAT-074/075: the big window ran; NAT-076/077/079/080: the delivery path, probe, loader and driver exist

def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def digest(b):return hashlib.sha256(b).hexdigest()

def gate(image,cfg):
    """The agent-written decision file of this image: exactly one, naming both hashes and decision 0019. Never created here."""
    found=sorted((ROOT/'docs/decisions').glob('*-nat186-%s-single-run-*.md'%image))
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
    def root_image_check():
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
    def deliver_start():
        # After the collector, before the reboot: detached; the `loaded` record proves the image is verified and in memory. The companion then waits for the device by itself.
        out=a.out/'delivery';journal=out/'delivery.jsonl'
        argv=[str(VENV_PY),'-I',str(DELIVER),'--root',str(ROOT_IMAGE),'--size',str(ROOT_SIZE),'--sha256',ROOT_SHA,'--out',str(out),'--wait-s',str(DELIVER_WAIT_S),'--deliver-s',str(DELIVER_S),'--chunk','8388608','--write-size','8388608','--policy','auto','--none-chunks','4']
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
                host_access();collector_selftest();deliver_selftest();root_image_check()
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
            marker=ROOT/('artifacts/nat-186/native-attempt-%s-used.json'%a.image)
            marker.parent.mkdir(parents=True,exist_ok=True)
            with marker.open('x') as f:
                json.dump(dict(at=now(),image=a.image,image_sha256=NEW_SHA,attempt=str(a.out)),f);f.write('\n');f.flush();os.fsync(f.fileno())
            write(candidate,NEW_SHA)
            report['outcome']='candidate-written-readback-confirmed';save()
            watcher_start()
            collector_start()
            deliver_start()
            # The sole native reboot in this session. No later reboot or retry.
            report['reboot_sent']=True;report['reboot_requested_at']=now();save()
            run(['adb','reboot','recovery'])
            report['outcome']='native-attempt-started';save();print(json.dumps(dict(outcome=report['outcome'],image=a.image,image_sha256=NEW_SHA,reboot_requested_at=report['reboot_requested_at'],usb_log=report['watcher']['log'],archive=report['collector']['archive'],delivery=report['delivery']['out'])));return 0
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
