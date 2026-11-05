"""Independent fixture probes; never operate on the primary checkout."""
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
PRODUCER = MAIN / 'worktrees/int-kernel-20261106'
spec = importlib.util.spec_from_file_location('producer_fixture', PRODUCER / 'docs/integration/kernel/test_gate.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
gate = fixture.gate

class IndependentProbes(fixture.GateTests):
    # Use producer setup to build disposable repos; select only these independent cases.
    def test_review_lock_descriptor_remains_exclusive_in_child(self):
        with gate.integration_lock(self.root) as (fd, _):
            child = subprocess.Popen([sys.executable, '-s', '-c', 'import time; time.sleep(0.6)'], pass_fds=(fd,))
        try:
            with self.assertRaisesRegex(gate.GateError, 'Integration lock timeout'):
                with gate.integration_lock(self.root, timeout=0.1):
                    self.fail('Child inherited descriptor did not retain lock')
            self.assertEqual(child.wait(timeout=3), 0)
            with gate.integration_lock(self.root, timeout=0.1):
                pass
        finally:
            if child.poll() is None:
                child.terminate(); child.wait(timeout=3)

    def test_review_stale_candidate_keeps_dirty_ledger(self):
        ledger = self.root / 'state/lab.json'
        ledger.write_text('live reviewer fixture ledger\n')
        (self.candidate / 'source.txt').write_text('moved candidate after plan\n')
        self.git(self.candidate, 'commit', '-am', 'move candidate after freezing')
        code, evidence = self.finish(self.start())
        self.assertEqual(code, 2)
        self.assertIn('Candidate HEAD changed', evidence['error'])
        self.assertEqual(ledger.read_text(), 'live reviewer fixture ledger\n')
        self.assertEqual(self.git(self.root, 'rev-parse', 'HEAD'), self.base)

    def test_review_ignored_symlink_parent_is_rejected(self):
        (self.candidate / 'nested').mkdir()
        (self.candidate / 'nested/new.txt').write_text('candidate\n')
        self.git(self.candidate, 'add', 'nested/new.txt')
        self.git(self.candidate, 'commit', '-m', 'new nested source')
        tip = self.git(self.candidate, 'rev-parse', 'HEAD')
        self.plan.update(candidate_head=tip, commits=[self.tip, tip], paths=['source.txt', 'nested/new.txt'],
                         commit_map=[{'source': value, 'candidate': value} for value in [self.tip, tip]])
        self.save_plan()
        with (self.root / '.git/info/exclude').open('a') as stream:
            stream.write('\nnested\n')
        outside = self.root / 'artifacts/outside'; outside.mkdir()
        (self.root / 'nested').symlink_to(outside, target_is_directory=True)
        code, evidence = self.finish(self.start())
        self.assertEqual(code, 2)
        self.assertIn('Candidate parent is a primary symlink', evidence['error'])
        self.assertFalse((outside / 'new.txt').exists())

    def test_review_actual_common_supervisor_reaps_failed_make_descendant(self):
        # Actual gate common_check and existing supervisor, tiny owned process only.
        # Admission is explicitly substituted; this is not host admission evidence.
        target = self.root / 'tools/build'; target.mkdir(parents=True)
        shutil.copyfile(MAIN / 'tools/build/qemu_host.py', target / 'qemu_host.py')
        binary = self.root / 'artifacts/bin'; binary.mkdir()
        make = binary / 'make'
        make.write_text('#!' + sys.executable + '\n' + '''import fcntl,os,pathlib,subprocess,sys,time
root=pathlib.Path.cwd()
fd=os.open(root/'state/.integration.lock',os.O_RDWR)
try:
 fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
except BlockingIOError:
 (root/'artifacts/check-lock-held').write_text('yes')
else:
 sys.exit(98)
finally:
 os.close(fd)
child=subprocess.Popen([sys.executable,'-s','-c','import time; time.sleep(10)'],process_group=0)
(root/'artifacts/child-pid').write_text(str(child.pid))
time.sleep(0.25)
sys.exit(7)
''')
        make.chmod(0o755)
        output = self.root / 'artifacts/actual-common'; output.mkdir()
        report = {}; old_admit, old_env = gate.admit, gate.ENV
        gate.admit = lambda *args: None
        gate.ENV = dict(old_env, PATH=str(binary) + ':/usr/bin:/bin')
        try:
            with gate.integration_lock(self.root) as (fd, _):
                with self.assertRaisesRegex(gate.GateError, 'Common check failed'):
                    gate.common_check(self.root, output, fd, report)
            self.assertEqual((self.root / 'artifacts/check-lock-held').read_text(), 'yes')
            self.assertEqual(report['common_check']['exit_code'], 7)
            self.assertFalse(any(p['state'] != 'Z' for p in report['common_check']['after']['owned_processes']))
            self.assertGreater(report['common_check']['peak_owned_tree_rss_bytes'], 0)
            if fixture.RECORD:
                retained = fixture.RECORD / 'review-actual-common-artifacts'
                shutil.copytree(output, retained)
                shutil.copyfile(make, retained / 'fixture-make.py')
                child_pid = int((self.root / 'artifacts/child-pid').read_text())
                (fixture.RECORD / 'review-actual-common.json').write_text(json.dumps({'report': report, 'admission_substituted': True, 'project_common_check': False, 'fixture_child_pid': child_pid, 'fixture_lock_held': True}, indent=2)+'\n')
        finally:
            gate.admit, gate.ENV = old_admit, old_env

if __name__ == '__main__':
    suite = unittest.TestSuite(IndependentProbes(name) for name in sorted(dir(IndependentProbes)) if name.startswith('test_review_'))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
