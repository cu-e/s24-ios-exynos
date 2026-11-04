#!/usr/bin/env python3
"""Run only on a fresh task-owned emulator. Never selects or changes a physical device."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import socket
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = 'dev.egor.s24probe'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--apk', type=Path, required=True)
    p.add_argument('--run', required=True)
    p.add_argument('--port', type=int, default=5580)
    p.add_argument('--start-coordinate',type=int,nargs=2,metavar=('X','Y'),help='Optional Start location reviewed from the same fixed-size emulator screenshot; records unavailable semantic UI coverage')
    p.add_argument('--sdk', type=Path, default=Path(os.environ.get('ANDROID_HOME','/home/egor/Android/Sdk')))
    args = p.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}', args.run): raise ValueError('Invalid run name')
    if args.port % 2 or not 5580 <= args.port <= 5680: raise ValueError('Use an even dedicated test port from 5580 to 5680')
    with socket.socket() as connection:
        if connection.connect_ex(('127.0.0.1',args.port)) == 0: raise ValueError('Emulator port already in use; refusing to adopt it')
    apk = args.apk.resolve()
    if not apk.is_file() or not apk.is_relative_to(ROOT / 'artifacts'): raise ValueError('Use an APK from project artifacts')
    out = ROOT / 'artifacts/android-probe' / args.run
    if out.resolve() != out: raise ValueError('Run path cannot use symlinks')
    out.mkdir(parents=True,exist_ok=False)
    avdhome = out / 'avd'; avd = avdhome / 's24-probe.avd'; avd.mkdir(parents=True)
    emulator_home = out / 'emulator-home'; emulator_home.mkdir()
    # The emulator must be able to inject the existing host's PUBLIC adb key.
    # Never restart the shared server or copy/print its private key.
    public_key = Path.home() / '.android/adbkey.pub'
    if public_key.is_file(): shutil.copyfile(public_key, emulator_home / 'adbkey.pub')
    (avdhome/'s24-probe.ini').write_text(f'avd.ini.encoding=UTF-8\npath={avd}\ntarget=android-36\n')
    (avd/'config.ini').write_text('AvdId=s24-probe\navd.ini.displayname=S24 probe host emulator\nabi.type=x86_64\nhw.cpu.arch=x86_64\nhw.cpu.ncore=4\nhw.ramSize=3072\nhw.lcd.width=1080\nhw.lcd.height=2340\nhw.lcd.density=420\nhw.keyboard=yes\nhw.gpu.enabled=yes\nhw.gpu.mode=swiftshader\ndisk.dataPartition.size=2G\nimage.sysdir.1=system-images/android-36/google_apis_playstore/x86_64/\ntag.id=google_apis_playstore\ntag.display=Google Play\nPlayStore.enabled=true\n')
    env = {**os.environ,'ANDROID_AVD_HOME':str(avdhome),'ANDROID_EMULATOR_HOME':str(out/'emulator-home'),'ANDROID_SDK_ROOT':str(args.sdk)}
    serial = 'emulator-' + str(args.port)
    log = (out/'emulator.log').open('w')
    emulator = subprocess.Popen([str(args.sdk/'emulator/emulator'),'-avd','s24-probe','-port',str(args.port),'-no-window','-no-audio','-no-boot-anim','-no-snapshot','-gpu','swiftshader','-skip-adb-auth','-wipe-data'],env=env,stdout=log,stderr=subprocess.STDOUT)
    report = dict(schema_version=1,origin='local-host',kind='host-test',outcome='inconclusive',recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),environment='fresh x86_64 Android emulator; not S24',commands=[])
    adb = str(args.sdk/'platform-tools/adb')
    def call(*arguments,check=True,binary=False):
        argv = [adb,'-s',serial,*arguments]
        x = subprocess.run(argv,capture_output=True,timeout=90 if arguments[0]=='install' else 20)
        report['commands'].append({'argv':argv,'exit_code':x.returncode})
        if check and x.returncode: raise RuntimeError(x.stderr.decode(errors='replace'))
        return x.stdout if binary else x.stdout.decode(errors='replace')
    def hierarchy():
        # uiautomator can return exit 0 while reporting an idle-window failure.
        # Retain its actual output and retry a bounded number of fresh dumps.
        for attempt in range(3):
            call('shell','rm','-f','/data/local/tmp/probe-window.xml')
            dump = call('shell','uiautomator','dump','/data/local/tmp/probe-window.xml')
            raw = call('exec-out','cat','/data/local/tmp/probe-window.xml',check=False)
            (out/f'hierarchy-{len(report["commands"])}.txt').write_text(dump+'\n'+raw)
            start = raw.find('<?xml')
            if start < 0: start = raw.find('<hierarchy')
            if start >= 0:
                xml = raw[start:]
                ET.fromstring(xml)
                return xml
            time.sleep(1)
        raise RuntimeError('No XML hierarchy after three dumps; inspect retained hierarchy logs')
    def tap(label):
        tree = ET.fromstring(hierarchy())
        for n in tree.iter('node'):
            if n.get('text') == label and n.get('enabled') == 'true':
                a,b,c,d = map(int,re.findall(r'\d+',n.attrib['bounds']))
                return call('shell','input','tap',str((a+c)//2),str((b+d)//2))
        if label == 'Start test' and args.start_coordinate and any(n.get('package')==PACKAGE for n in tree.iter('node')):
            x,y=args.start_coordinate
            if not 0<=x<1080 or not 0<=y<2340: raise ValueError('Start coordinates outside the configured viewport')
            report['ui_automation_limitation']='Android 36 hierarchy exposes the app root without child controls; Start used explicitly reviewed screenshot coordinates. Accessibility semantics unqualified.'
            report['start_coordinate']=[x,y]
            return call('shell','input','tap',str(x),str(y))
        raise RuntimeError('Missing enabled control: '+label)
    try:
        deadline=time.monotonic()+150
        while time.monotonic()<deadline:
            if emulator.poll() is not None: raise RuntimeError('Task emulator exited; inspect emulator.log')
            if call('shell','getprop','sys.boot_completed',check=False).strip()=='1': break
            time.sleep(2)
        else: raise RuntimeError('Emulator boot timed out')
        # Cold Google Play images can set boot_completed before System UI settles.
        # This bounded host-only settling period avoids measuring a boot ANR.
        time.sleep(20)
        print('Task emulator booted; installing only on '+serial,flush=True)
        call('shell','input','keyevent','KEYCODE_WAKEUP'); call('shell','wm','dismiss-keyguard')
        call('install','-t',str(apk))
        call('shell','am','start','-W','-n',PACKAGE+'/.MainActivity')
        time.sleep(1)
        (out/'before-test.png').write_bytes(call('exec-out','screencap','-p',binary=True))
        tap('Start test')
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            text=call('exec-out','run-as',PACKAGE,'cat','files/last-report.json',check=False)
            (out/'last-report-poll.txt').write_text(text)
            try:
                result=json.loads(text)
                break
            except ValueError: time.sleep(.25)
        else: raise RuntimeError('No actual probe report within deadline')
        (out/'probe-report.json').write_text(json.dumps(result,indent=2)+'\n')
        if (result.get('outcome'),result.get('compared_pixels'),result.get('mismatched_pixels'))!=('pass',65536,0): raise RuntimeError('Emulator GPU fixture failed: '+text)
        call('shell','input','keyevent','KEYCODE_HOME')
        call('shell','am','start','-W','-n',PACKAGE+'/.MainActivity')
        restored=hierarchy(); (out/'restored.xml').write_text(restored)
        persisted=json.loads(call('exec-out','run-as',PACKAGE,'cat','files/last-report.json'))
        if persisted != result: raise RuntimeError('App did not retain the actual saved report unchanged')
        (out/'restored.png').write_bytes(call('exec-out','screencap','-p',binary=True))
        report['saved_report_unchanged_after_reopen']=True
        report['restored_status_semantically_verified']='Previous result: pass' in restored or 'Result: pass' in restored
        for mode in ['no','yes']:
            call('shell','cmd','uimode','night',mode)
            call('shell','settings','put','system','font_scale','1.3')
            call('shell','am','force-stop',PACKAGE)
            call('shell','am','start','-W','-n',PACKAGE+'/.MainActivity'); time.sleep(.5)
            (out/('phone-'+mode+'.png')).write_bytes(call('exec-out','screencap','-p',binary=True))
            (out/('phone-'+mode+'.xml')).write_text(hierarchy())
        report.update(outcome='pass',summary='Fresh emulator ran exact Vulkan fixture, preserved saved report after reopen, and captured light/dark UI at larger text; UI semantics limitations remain separate',probe=result)
    except Exception as error:
        report.update(outcome='fail',error=str(error))
        if emulator.poll() is None:
            try:
                (out/'failure.png').write_bytes(call('exec-out','screencap','-p',binary=True))
                (out/'crash.txt').write_text(call('logcat','-b','crash','-d',check=False))
            except (OSError,subprocess.SubprocessError): pass
    finally:
        # Terminate the process we created, never an unrelated emulator or device.
        emulator.terminate()
        try: emulator.wait(timeout=15)
        except subprocess.TimeoutExpired: emulator.kill(); emulator.wait(timeout=5)
        log.close();(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'outcome':report['outcome'],'error':report.get('error'),'report':str((out/'report.json').relative_to(ROOT))},indent=2))
    return 0 if report['outcome']=='pass' else 1


if __name__=='__main__':
    try: raise SystemExit(main())
    except (ValueError,OSError) as error: print(error);raise SystemExit(2)
