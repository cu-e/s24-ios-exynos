"""Reject unsafe launcher inputs before a guest process or device mutation exists."""
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest
import uuid
import importlib.util

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'src/android-probe/emulator_check.py'
spec=importlib.util.spec_from_file_location('probe_emulator_check',SCRIPT)
emulator_check=importlib.util.module_from_spec(spec);spec.loader.exec_module(emulator_check)


class EmulatorAdmissionTests(unittest.TestCase):
    def test_offline_allowlist_never_replays_measurement_install_or_settings(self):
        allowed=[('exec-out','screencap','-p'),('exec-out','run-as','dev.egor.s24probe','cat','files/qualifier-run.json'),
                 ('shell','run-as','dev.egor.s24probe','rm','-f','files/last-report.json.new/blocker')]
        forbidden=[('install','-t','/owned.apk'),('shell','am','instrument','-w','qualifier'),
                   ('shell','input','tap','10','10'),('shell','settings','put','system','font_scale','1.3'),
                   ('shell','run-as','another.package','rm','-f','files/last-report.json'),
                   ('shell','run-as','dev.egor.s24probe','rm','-rf','files/'),
                   ('shell','run-as','dev.egor.s24probe','rm','-f','files/unrelated.json')]
        for command in allowed:self.assertTrue(emulator_check.retryable_offline_command(command),command)
        for command in forbidden:self.assertFalse(emulator_check.retryable_offline_command(command),command)

    def reject(self,options,expected,apk='/missing.apk'):
        name='guard-'+uuid.uuid4().hex
        out=ROOT/'artifacts/android-probe'/name
        r=subprocess.run(['python3',str(SCRIPT),'--run',name,'--apk',str(apk),*options],capture_output=True,text=True,timeout=10)
        self.assertEqual(r.returncode,2,r.stderr+r.stdout)
        self.assertIn(expected,r.stdout)
        self.assertFalse(out.exists(),'Rejected input created a guest run')

    def test_shared_server_and_unsafe_emulator_ports_are_rejected(self):
        self.reject(['--adb-server-port','5037'],'private ADB server port')
        self.reject(['--port','5554'],'dedicated test port')
        self.reject(['--port','5581'],'dedicated test port')

    def test_viewport_and_deadline_limits_precede_process_start(self):
        self.reject(['--width','0'],'Unsupported task viewport')
        self.reject(['--height','100000'],'Unsupported task viewport')
        self.reject(['--boot-timeout','0'],'Boot deadline')

    def test_paths_cannot_escape_the_run_root(self):
        r=subprocess.run(['python3',str(SCRIPT),'--run','../escape','--apk','/missing.apk'],capture_output=True,text=True,timeout=10)
        self.assertEqual(r.returncode,2)
        self.assertIn('Invalid run name',r.stdout)

    def test_occupied_console_port_cannot_be_adopted(self):
        with socket.socket() as owned:
            for port in range(5580,5681,2):
                try:owned.bind(('127.0.0.1',port));break
                except OSError:continue
            else:self.skipTest('No free dedicated test port')
            owned.listen()
            self.reject(['--port',str(port)],'refusing to adopt')

    def test_existing_apk_outside_project_artifacts_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix='external-probe-') as td:
            apk=Path(td)/'outside.apk';apk.write_bytes(b'not-an-apk')
            self.reject([],'Use an APK from project artifacts',apk)

    def test_changed_apk_is_rejected_before_launch(self):
        parent=ROOT/'artifacts/android-probe';parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='admission-fixture-',dir=parent) as td:
            p=Path(td);apk=p/'fixture.apk';apk.write_bytes(b'changed-owned-fixture')
            (p/'build-report.json').write_text(json.dumps({'outcome':'pass','apk':{'sha256':hashlib.sha256(b'original-owned-fixture').hexdigest()},'source_files':{}}))
            self.reject([],'APK does not match',apk)


if __name__=='__main__':unittest.main()
