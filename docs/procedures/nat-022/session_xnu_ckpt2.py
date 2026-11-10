#!/usr/bin/env python3
"""NAT-034 / decision 0017 (owner decision required, this image only): one fixed loader-diag-xnu-ckpt2 RECOVERY write, readback, one reboot; no retries.

The image is the run-008 loader whose return stub resumes the payload kernel at assembly checkpoint 5 (the kernel's own
MMU-enable block, slot[2] = 11) and holds at the first C checkpoint, loader_checkpoint(11): the kernel's start code runs on
past the point where run 008 stopped, through arm_init, cpu_data_init and PE_init_platform. Every preflight and launch path
stops before touching the phone unless the owner decision file named below exists (it is written only after the owner's
answer; this script never creates it).

The default is read-only preflight. --restore writes only the pinned stock image
without rebooting. No file is staged on the phone. Failed writes never reboot.
"""
from pathlib import Path
import argparse,datetime,fcntl,hashlib,json,os,subprocess,sys,time

ROOT=Path(__file__).resolve().parents[3]
SIZE=100663296
CANDIDATE=ROOT/'artifacts/nat-034/package-001/recovery.img'
NEW_SHA='56f06e2582a4692f3f40d0d1ef3fb46633799fd9bc107e963d38731150961f59'
CANARY_SHA='27d5c0075d28bde69ee8a172d2cc34f4c3b98957d562ae1e7b70e914c8684a77'  # loader-diag-xnu-ckpt2 Image.payload
CANARY_LEN=21784160
STOCK=ROOT/'devices/recovery/backups/2026-11-10/recovery.img'
STOCK_SHA='96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67'
TARGET='/dev/block/sda18'
WRITE="su -c 'test -b /dev/block/sda18 && dd of=/dev/block/sda18 bs=1048576 count=100663296 iflag=count_bytes conv=notrunc,fsync'"

def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def digest(b):return hashlib.sha256(b).hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path)
    mode=p.add_mutually_exclusive_group();mode.add_argument('--execute',action='store_true');mode.add_argument('--restore',action='store_true')
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    report=dict(at=now(),mode='restore' if a.restore else 'launch' if a.execute else 'preflight',
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
    lockpath=ROOT/'artifacts/nat-022/recovery-write.lock';lockpath.parent.mkdir(parents=True,exist_ok=True)
    with lockpath.open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            stock=STOCK.read_bytes();candidate=CANDIDATE.read_bytes()
            assert len(stock)==len(candidate)==SIZE and digest(stock)==STOCK_SHA and digest(candidate)==NEW_SHA
            pkg=json.loads((CANDIDATE.parent/'package.json').read_text())
            assert pkg['recovery_sha256']==NEW_SHA and pkg['source_image_sha256']==CANARY_SHA and pkg['flashed'] is False
            assert (ROOT/'docs/decisions/0017-nat034-loader-diag-xnu-ckpt2-single-run-2026-11-11.md').exists(), 'owner decision 0017 is missing: no device access'
            assert digest(candidate[2048:2048+CANARY_LEN])==CANARY_SHA,'loader Image.payload not at its expected offset'
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
            if not (a.execute or a.restore):
                report['outcome']='ready-read-only';save();print(report['outcome']);return 0
            if a.restore:
                write(stock,STOCK_SHA);report['outcome']='stock-written-readback-confirmed';save();print(report['outcome']);return 0
            marker=ROOT/'artifacts/nat-022/native-attempt-xnuckpt2-used.json'
            with marker.open('x') as f:
                json.dump(dict(at=now(),image_sha256=NEW_SHA,attempt=str(a.out)),f);f.write('\n');f.flush();os.fsync(f.fileno())
            write(candidate,NEW_SHA)
            report['outcome']='candidate-written-readback-confirmed';save()
            # The sole native reboot in this session. No later reboot or retry.
            report['reboot_sent']=True;report['reboot_requested_at']=now();save()
            run(['adb','reboot','recovery'])
            report['outcome']='native-attempt-started';save();print(json.dumps(dict(outcome=report['outcome'],image_sha256=NEW_SHA,reboot_requested_at=report['reboot_requested_at'])));return 0
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
