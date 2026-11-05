"""Two tiny actual-supervisor probes for the RSS-only gate followup."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import shutil
import sys
import unittest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('original_independent_probe',HERE/'probe.py')
original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)
gate=original.gate
expected=sys.argv[1]
with original.fixture.SCRIPT.open('rb') as stream:
    assert hashlib.file_digest(stream,'sha256').hexdigest()==expected

class Followup(original.IndependentProbes):
    def test_followup_javac_version_under_actual_common_supervisor(self):
        target=self.root/'tools/build';target.mkdir(parents=True)
        shutil.copyfile(original.MAIN/'tools/build/qemu_host.py',target/'qemu_host.py')
        binary=self.root/'artifacts/jdk-bin';binary.mkdir()
        make=binary/'make'
        make.write_text('#!'+sys.executable+'\n'+'''import fcntl,json,os,pathlib,resource,subprocess,sys
root=pathlib.Path.cwd();fd=os.open(root/'state/.integration.lock',os.O_RDWR)
try:
 fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
except BlockingIOError:
 held=True
else:
 held=False
finally:
 os.close(fd)
result=subprocess.run(['javac','-version'],capture_output=True,text=True,timeout=10)
print(json.dumps({'fixture_only':True,'lock_held':held,'rlimit_as':resource.getrlimit(resource.RLIMIT_AS),'javac_exit':result.returncode,'stdout':result.stdout,'stderr':result.stderr}),flush=True)
sys.exit(result.returncode if held else 98)
''')
        make.chmod(0o755);output=self.root/'artifacts/jdk-common';output.mkdir()
        report={};old_admit,old_env=gate.admit,gate.ENV
        gate.admit=lambda *args:None
        gate.ENV=dict(old_env,PATH=str(binary)+':'+old_env.get('PATH','/usr/bin:/bin'))
        try:
            with gate.integration_lock(self.root) as (fd,_):
                gate.common_check(self.root,output,fd,report)
            data=json.loads((output/'make-check.log').read_text())
            self.assertEqual(data['javac_exit'],0)
            self.assertTrue(data['lock_held'])
            self.assertEqual(data['rlimit_as'],list(resource.getrlimit(resource.RLIMIT_AS)))
            self.assertIsNone(report['common_check']['address_space_limit_bytes'])
            self.assertEqual(report['common_check']['aggregate_rss_stop_bytes'],2147483648)
            self.assertEqual(report['common_check']['max_jobs'],2)
            self.assertFalse(any(p['state']!='Z' for p in report['common_check']['after']['owned_processes']))
            dest=original.fixture.RECORD/'review-jdk-version-artifacts';shutil.copytree(output,dest)
            shutil.copyfile(make,dest/'fixture-make.py')
            (original.fixture.RECORD/'review-jdk-version.json').write_text(json.dumps({'report':report,'fixture':data,'admission_substituted':True,'project_common_check':False,'source_compilation':False},indent=2)+'\n')
        finally:
            gate.admit,gate.ENV=old_admit,old_env

if __name__=='__main__':
    suite=unittest.TestSuite([Followup('test_review_actual_common_supervisor_reaps_failed_make_descendant'),Followup('test_followup_javac_version_under_actual_common_supervisor')])
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
