#!/usr/bin/env python3
"""Run only on a fresh task-owned emulator. Never selects or changes a physical device."""
import argparse
from datetime import datetime, timezone
import json
import hashlib
import os
from pathlib import Path
import re
import socket
import shutil
import signal
import subprocess
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = 'dev.egor.s24probe'


def retryable_offline_command(arguments):
    """Only repeat reads or idempotent removal of our fixed private test file."""
    a=tuple(arguments)
    if a in [('exec-out','screencap','-p'),('exec-out','cat','/sdcard/Download/s24-vulkan-report.json')]:return True
    if len(a)==5 and a[:4]==('exec-out','run-as',PACKAGE,'cat') and a[4].startswith('files/'):return True
    if len(a)==6 and a[:5]==('shell','run-as',PACKAGE,'rm','-f') and a[5] in [
        'files/last-report.json','files/last-report.json.new/blocker','files/last-report.json/blocker']:return True
    return False


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--apk', type=Path, required=True)
    p.add_argument('--run', required=True)
    p.add_argument('--port', type=int, default=5580)
    p.add_argument('--boot-timeout', type=int, default=300)
    p.add_argument('--width', type=int, default=720)
    p.add_argument('--height', type=int, default=1560)
    p.add_argument('--density', type=int, default=280)
    p.add_argument('--adb-server-port', type=int, default=5482)
    p.add_argument('--qualifier-apk', type=Path)
    p.add_argument('--start-coordinate',type=int,nargs=2,metavar=('X','Y'),help='Optional Start location reviewed from the same fixed-size emulator screenshot; records unavailable semantic UI coverage')
    p.add_argument('--sdk', type=Path, default=Path(os.environ.get('ANDROID_HOME','/home/egor/Android/Sdk')))
    args = p.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}', args.run): raise ValueError('Invalid run name')
    if args.port % 2 or not 5580 <= args.port <= 5680: raise ValueError('Use an even dedicated test port from 5580 to 5680')
    if not 60 <= args.boot_timeout <= 600: raise ValueError('Boot deadline must be 60..600 seconds')
    if not 5400 <= args.adb_server_port <= 5499: raise ValueError('Use a dedicated private ADB server port from 5400 to 5499')
    if not (480 <= args.width <= 1440 and 800 <= args.height <= 3200 and 160 <= args.density <= 640): raise ValueError('Unsupported task viewport')
    with socket.socket() as connection:
        if connection.connect_ex(('127.0.0.1',args.port)) == 0: raise ValueError('Emulator port already in use; refusing to adopt it')
    apk = args.apk.resolve()
    if not apk.is_file() or not apk.is_relative_to(ROOT / 'artifacts'): raise ValueError('Use an APK from project artifacts')
    build = json.loads((apk.parent/'build-report.json').read_text())
    apk_digest = hashlib.sha256(apk.read_bytes()).hexdigest()
    if build.get('outcome') != 'pass' or build['apk']['sha256'] != apk_digest: raise ValueError('APK does not match its passing build report')
    for name, digest in build['source_files'].items():
        if hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest() != digest: raise ValueError('Compiled app inputs changed; rebuild before qualification')
    qualifier=None
    if args.qualifier_apk:
        qualifier=args.qualifier_apk.resolve()
        if not qualifier.is_relative_to(ROOT/'artifacts'): raise ValueError('Qualifier must be a project artifact')
        qbuild=json.loads((qualifier.parent/'build-report.json').read_text())
        if qbuild.get('outcome')!='pass' or qbuild['apk_sha256']!=hashlib.sha256(qualifier.read_bytes()).hexdigest() or qbuild['target_apk_sha256']!=apk_digest: raise ValueError('Qualifier/target build mismatch')
        for name,digest in qbuild['source_sha256'].items():
            if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest: raise ValueError('Qualifier inputs changed; rebuild')
    with socket.socket() as connection:
        if connection.connect_ex(('127.0.0.1',args.adb_server_port))==0: raise ValueError('Private ADB port already in use; refusing adoption')
    out = ROOT / 'artifacts/android-probe' / args.run
    if out.resolve() != out: raise ValueError('Run path cannot use symlinks')
    out.mkdir(parents=True,exist_ok=False)
    helper_bytes=Path(__file__).read_bytes()
    (out/'emulator_check.py').write_bytes(helper_bytes)
    avdhome = out / 'avd'; avd = avdhome / 's24-probe.avd'; avd.mkdir(parents=True)
    avd_name = 's24-probe-' + args.run
    emulator_home = out / 'emulator-home'; emulator_home.mkdir()
    # The emulator must be able to inject the existing host's PUBLIC adb key.
    # Never restart the shared server or copy/print its private key.
    public_key = Path.home() / '.android/adbkey.pub'
    if public_key.is_file(): shutil.copyfile(public_key, emulator_home / 'adbkey.pub')
    (avdhome/(avd_name+'.ini')).write_text(f'avd.ini.encoding=UTF-8\npath={avd}\ntarget=android-36\n')
    (avd/'config.ini').write_text(f'AvdId={avd_name}\navd.ini.displayname=S24 probe host emulator\nabi.type=x86_64\nhw.cpu.arch=x86_64\nhw.cpu.ncore=2\nhw.ramSize=2048\nhw.lcd.width={args.width}\nhw.lcd.height={args.height}\nhw.lcd.density={args.density}\nhw.keyboard=yes\nhw.gpu.enabled=yes\nhw.gpu.mode=swiftshader\ndisk.dataPartition.size=2G\nimage.sysdir.1=system-images/android-36/google_apis_playstore/x86_64/\ntag.id=google_apis_playstore\ntag.display=Google Play\nPlayStore.enabled=true\n')
    env = {**os.environ,'ANDROID_AVD_HOME':str(avdhome),'ANDROID_EMULATOR_HOME':str(out/'emulator-home'),'ANDROID_SDK_ROOT':str(args.sdk),
           'ANDROID_ADB_SERVER_PORT':str(args.adb_server_port),'ADB_SERVER_SOCKET':'tcp:'+str(args.adb_server_port),
           'ADB_LOCAL_TRANSPORT_MAX_PORT':'0','ADB_MDNS_AUTO_CONNECT':'0'}
    serial = 'emulator-' + str(args.port)
    log = (out/'emulator.log').open('w')
    emulator_argv = [str(args.sdk/'emulator/emulator'),'-avd',avd_name,'-port',str(args.port),'-no-window','-no-audio','-no-boot-anim','-no-snapshot','-gpu','swiftshader','-skip-adb-auth','-wipe-data']
    report = dict(schema_version=1,origin='local-host',kind='host-test',outcome='inconclusive',recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),environment='fresh x86_64 Android36 extension17 Google Play r7 emulator; not S24',commands=[],apk_sha256=apk_digest,compiled_source_sha256=build['source_sha256'],viewport=[args.width,args.height,args.density],emulator_argv=emulator_argv,physical_device_selected=False)
    image_properties = args.sdk/'system-images/android-36/google_apis_playstore/x86_64/source.properties'
    report['image_source_properties'] = image_properties.read_text()
    report['image_source_properties_sha256'] = hashlib.sha256(image_properties.read_bytes()).hexdigest()
    report['helper_sha256']=hashlib.sha256(helper_bytes).hexdigest()
    adb = str(args.sdk/'platform-tools/adb')
    adb_log=(out/'adb-server.log').open('w')
    # No USB device has this task-generated selector. Disable automatic local
    # emulator scanning/mDNS as well; only our emulator self-registers here.
    server_argv=[adb,'-L',env['ADB_SERVER_SOCKET'],'--one-device','s24-host-no-usb-'+args.run,'server','nodaemon']
    server=subprocess.Popen(server_argv,env=env,stdout=adb_log,stderr=subprocess.STDOUT,start_new_session=True)
    emulator=None
    report.update(private_adb_argv=server_argv,private_adb_pid=server.pid,private_adb_port=args.adb_server_port)
    def terminate_owned(process):
        if process is None:return
        if process.poll() is None:
            try:os.killpg(process.pid,signal.SIGTERM)
            except ProcessLookupError:pass
        try:process.wait(timeout=15)
        except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)
    def call(*arguments,check=True,binary=False):
        if server.poll() is not None:raise RuntimeError('Owned private ADB server exited; refusing client fallback')
        argv = [adb,'-s',serial,*arguments]
        timeout=180 if arguments[:3]==('shell','am','instrument') else 90 if arguments[0]=='install' else 20
        x = subprocess.run(argv,capture_output=True,timeout=timeout,env=env)
        report['commands'].append({'argv':argv,'exit_code':x.returncode})
        if x.returncode and b'device offline' in x.stderr and retryable_offline_command(arguments) and report.get('guest_boot_id_sha256'):
            recovery=dict(argv=argv,started_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),outcome='unrecovered')
            report.setdefault('offline_recoveries',[]).append(recovery)
            deadline=time.monotonic()+30
            while time.monotonic()<deadline:
                if emulator.poll() is not None or server.poll() is not None:raise RuntimeError('Owned process exited during transport observation')
                state=subprocess.run([adb,'-s',serial,'get-state'],capture_output=True,timeout=5,env=env)
                if state.returncode==0 and state.stdout.strip()==b'device':
                    identity=subprocess.run([adb,'-s',serial,'emu','avd','name'],capture_output=True,text=True,timeout=5,env=env)
                    epoch=subprocess.run([adb,'-s',serial,'exec-out','cat','/proc/sys/kernel/random/boot_id'],capture_output=True,timeout=5,env=env)
                    if identity.returncode==0 and identity.stdout.splitlines()[0].strip()==avd_name and epoch.returncode==0:
                        if hashlib.sha256(epoch.stdout).hexdigest()!=report['guest_boot_id_sha256']:raise RuntimeError('Guest rebooted during transport loss; no implicit session reuse')
                        recovery['outcome']='same-owned-avd-and-boot-recovered';break
                time.sleep(1)
            if recovery['outcome']=='same-owned-avd-and-boot-recovered':
                x=subprocess.run(argv,capture_output=True,timeout=timeout,env=env)
                report['commands'].append({'argv':argv,'exit_code':x.returncode,'single_idempotent_retry':True})
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
            if not 0<=x<args.width or not 0<=y<args.height: raise ValueError('Start coordinates outside the configured viewport')
            report['ui_automation_limitation']='Android 36 hierarchy exposes the app root without child controls; Start used explicitly reviewed screenshot coordinates. Accessibility semantics unqualified.'
            report['start_coordinate']=[x,y]
            return call('shell','input','tap',str(x),str(y))
        raise RuntimeError('Missing enabled control: '+label)
    try:
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            if server.poll() is not None:raise RuntimeError('Private ADB startup failed')
            with socket.socket() as connection:
                if connection.connect_ex(('127.0.0.1',args.adb_server_port))==0:break
            time.sleep(.1)
        else:raise RuntimeError('Private ADB server did not listen')
        emulator=subprocess.Popen(emulator_argv,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        report['owned_pid']=emulator.pid
        deadline=time.monotonic()+args.boot_timeout
        while time.monotonic()<deadline:
            if emulator.poll() is not None: raise RuntimeError('Task emulator exited; inspect emulator.log')
            if call('shell','getprop','sys.boot_completed',check=False).strip()=='1': break
            time.sleep(2)
        else: raise RuntimeError('Emulator boot timed out')
        identity=call('emu','avd','name').splitlines()
        if not identity or identity[0].strip()!=avd_name: raise RuntimeError('Selected emulator identity differs from the process-owned AVD; no mutation allowed')
        report['owned_avd_identity_verified']=True
        report['guest_boot_id_sha256']=hashlib.sha256(call('exec-out','cat','/proc/sys/kernel/random/boot_id',binary=True)).hexdigest()
        devices=subprocess.run([adb,'devices'],env=env,capture_output=True,text=True,timeout=10)
        private_serials=[line.split()[0] for line in devices.stdout.splitlines()[1:] if line.strip()]
        if devices.returncode or private_serials!=[serial]:raise RuntimeError('Private ADB contains unexpected transports; no mutation allowed')
        report['private_adb_transports']=[serial]
        print('Task emulator booted; installing only on '+serial,flush=True)
        call('shell','input','keyevent','KEYCODE_WAKEUP'); call('shell','wm','dismiss-keyguard')
        call('install','-t',str(apk))
        call('shell','am','start','-W','-n',PACKAGE+'/.MainActivity')
        # Boot-completed and an app root do not prove controls are ready.
        # Wait for semantic Start instead of a fixed delay or guessed coordinate.
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            tree=ET.fromstring(hierarchy())
            if any(n.get('text')=='Start test' and n.get('enabled')=='true' for n in tree.iter('node')): break
            time.sleep(2)
        else: raise RuntimeError('App semantic controls did not become ready')
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
        if result.get('source_sha256')!=build['source_sha256']: raise RuntimeError('Runtime source identity differs from the exact APK build')
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
        if qualifier:
            call('install','-t',str(qualifier));report['qualifier_apk_sha256']=qbuild['apk_sha256'];report['qualification_cases']=[]
            for theme in ['no','yes']:
                call('shell','cmd','uimode','night',theme);call('shell','settings','put','system','font_scale','1.3')
                call('shell','pm','clear',PACKAGE)
                for mode in ['initial','run','storage','commit','lifecycle','restart','export','theme']:
                    prefix='qualification-'+theme+'-'+mode
                    if mode in ['storage','commit']:
                        call('shell','run-as',PACKAGE,'rm','-f','files/last-report.json')
                        fault='files/last-report.json' if mode=='commit' else 'files/last-report.json.new'
                        call('shell','run-as',PACKAGE,'mkdir',fault)
                        call('shell','run-as',PACKAGE,'touch',fault+'/blocker')
                    if mode=='export':call('shell','rm','-f','/sdcard/Download/s24-vulkan-report.json')
                    output=call('shell','am','instrument','-w','-e','mode',mode,'-e','apk_sha256',apk_digest,'-e','source_sha256',build['source_sha256'],'dev.egor.s24probe.qualifier/.Qualifier')
                    (out/(prefix+'.stdout.txt')).write_text(output)
                    actual=json.loads(call('exec-out','run-as',PACKAGE,'cat','files/qualifier-'+mode+'.json'))
                    (out/(prefix+'.json')).write_text(json.dumps(actual,indent=2)+'\n')
                    (out/(prefix+'.png')).write_bytes(call('exec-out','run-as',PACKAGE,'cat','files/qualifier-'+mode+'.png',binary=True))
                    report['qualification_cases'].append(dict(theme=theme,mode=mode,outcome=actual.get('outcome'),report=prefix+'.json'))
                    if mode in ['storage','commit']:
                        call('shell','run-as',PACKAGE,'rm','-f',fault+'/blocker')
                        call('shell','run-as',PACKAGE,'rmdir',fault)
                    if actual.get('outcome')!='pass':raise RuntimeError('Instrumented '+prefix+' failed: '+actual.get('error','missing outcome'))
                    if mode=='export':
                        exported=json.loads(call('exec-out','cat','/sdcard/Download/s24-vulkan-report.json'))
                        (out/(prefix+'-export.json')).write_text(json.dumps(exported,indent=2)+'\n')
                        if exported!=actual['measurement']:raise RuntimeError('System picker export differs from genuine measured result')
                    if mode=='theme' and actual.get('live_theme_recreated') is not True:raise RuntimeError('Live theme recreation unverified')
            report['extended_runtime_qualification']=True
        report.update(outcome='pass',summary='Fresh emulator ran exact Vulkan fixture, preserved saved report after reopen, and captured light/dark UI at larger text; UI semantics limitations remain separate',probe=result)
    except Exception as error:
        report.update(outcome='fail',error=str(error))
        if emulator is not None and emulator.poll() is None:
            try:
                (out/'failure.png').write_bytes(call('exec-out','screencap','-p',binary=True))
                (out/'crash.txt').write_text(call('logcat','-b','crash','-d',check=False))
            except (OSError,subprocess.SubprocessError,RuntimeError) as diagnostic_error:
                report['diagnostic_error']=str(diagnostic_error)
    finally:
        # Terminate the process we created, never an unrelated emulator or device.
        terminate_owned(emulator);terminate_owned(server)
        report['owned_emulator_exit_code']=emulator.returncode if emulator else None
        report['owned_emulator_started']=emulator is not None
        report['owned_emulator_exited']=emulator is not None and emulator.poll() is not None
        report['private_adb_exited']=server.poll() is not None
        log.close();adb_log.close();(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'outcome':report['outcome'],'error':report.get('error'),'report':str((out/'report.json').relative_to(ROOT))},indent=2))
    return 0 if report['outcome']=='pass' else 1


if __name__=='__main__':
    try: raise SystemExit(main())
    except (ValueError,OSError) as error: print(error);raise SystemExit(2)
