#!/usr/bin/env python3
"""Real pipe/process failure controls. Synthetic producer, no phone access."""
import base64, hashlib, json, os
from pathlib import Path
import subprocess, sys, tempfile, time, unittest
import resource
SCRIPT=Path(__file__).with_name('archive.py').resolve()
def frame(boot,seq,kind,text=b''):
    return (json.dumps(dict(boot_id=boot,seq=seq,kind=kind,data_b64=base64.b64encode(text).decode()))+'\n').encode()
class ArchiveTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
    def cmd(self,out,*args):return [sys.executable,'-I',str(SCRIPT),'--out',str(out),'--channel','fixture','--provenance','synthetic',*args]
    def run_stream(self,data,*args):
        out=self.root/'run';r=subprocess.run(self.cmd(out,*args),input=data,capture_output=True,timeout=5)
        return out,r,json.loads((out/'manifest.json').read_text())
    def test_two_boots_and_restart_keep_all_raw_and_payloads(self):
        data=frame('one',0,'boot')+frame('one',1,'log',b'first\x00\xff')+frame('one',2,'end')+frame('two',0,'boot')+frame('two',1,'end',b'second')
        out,r,m=self.run_stream(data)
        self.assertEqual(r.returncode,0,r.stderr);self.assertFalse(m['hardware_execution_proven'])
        self.assertEqual((out/'received.bin').read_bytes(),data)
        self.assertEqual((out/'boots/000001-one/payload.bin').read_bytes(),b'first\x00\xff')
        self.assertEqual((out/'boots/000002-two/payload.bin').read_bytes(),b'second')
        for path,sha in m['sha256'].items():self.assertEqual(hashlib.sha256((out/path).read_bytes()).hexdigest(),sha)
        r2=subprocess.run(self.cmd(self.root/'next'),input=frame('one',0,'boot')+frame('one',1,'end'),capture_output=True,timeout=5)
        self.assertEqual(r2.returncode,0);self.assertEqual((out/'received.bin').read_bytes(),data)
    def test_existing_output_refused_without_mutation(self):
        out=self.root/'existing';out.mkdir();(out/'received.bin').write_bytes(b'prior')
        r=subprocess.run(self.cmd(out),input=b'new',capture_output=True,timeout=5)
        self.assertEqual(r.returncode,2);self.assertEqual((out/'received.bin').read_bytes(),b'prior');self.assertEqual(len(list(out.iterdir())),1)
    def test_duplicate_boot_gap_drop_and_reordered_frames_are_visible(self):
        data=frame('a',0,'boot')+frame('a',2,'drop')+frame('a',1,'log',b'bad')+frame('a',0,'boot')+frame('a',3,'end')
        out,r,m=self.run_stream(data)
        self.assertEqual(r.returncode,2);self.assertEqual(m['outcome'],'incomplete')
        self.assertEqual((out/'received.bin').read_bytes(),data)
        events=(out/'events.jsonl').read_text();self.assertIn('sequence-gap',events);self.assertIn('producer-reported-drop',events);self.assertIn('reused boot_id',events);self.assertNotIn(b'bad',(out/'boots/000001-a/payload.bin').read_bytes());self.assertTrue((out/'boots/000002-a/payload.bin').exists())
    def test_bad_and_oversize_lines_do_not_destroy_raw_or_later_boot(self):
        data=b'not-json\xff\n'+b'x'*70000+b'\n'+frame('later',0,'boot')+frame('later',1,'end',b'kept')+b'{partial'
        out,r,m=self.run_stream(data)
        self.assertEqual(r.returncode,2);self.assertEqual((out/'received.bin').read_bytes(),data)
        self.assertEqual((out/'boots/000001-later/payload.bin').read_bytes(),b'kept')
        e=(out/'events.jsonl').read_text();self.assertIn('oversize-frame',e);self.assertIn('truncated-frame',e)
    def test_fragmented_pipe_is_assembled_without_loss(self):
        out=self.root/'fragment';p=subprocess.Popen(self.cmd(out),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        data=frame('fragments',0,'boot')+frame('fragments',1,'end',b'marker')
        for start in range(0,len(data),7):p.stdin.write(data[start:start+7]);p.stdin.flush()
        p.stdin.close();p.stdin=None;stdout,stderr=p.communicate(timeout=5)
        self.assertEqual(p.returncode,0,stderr);self.assertEqual((out/'received.bin').read_bytes(),data)
        chunks=[json.loads(l) for l in (out/'chunks.jsonl').read_text().splitlines()]
        self.assertEqual(sum(c['length'] for c in chunks),len(data))
    def test_idle_pipe_deadline_and_size_limit_are_incomplete(self):
        out=self.root/'idle';p=subprocess.Popen(self.cmd(out,'--seconds','.1'),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:p.wait(timeout=3)
        finally:p.stdin.close();p.stdout.close();p.stderr.close()
        self.assertEqual(p.returncode,2);self.assertEqual(json.loads((out/'manifest.json').read_text())['stop'],'deadline')
        data=frame('limited',0,'boot')+frame('limited',1,'end',b'long')
        out,r,m=self.run_stream(data,'--max-bytes','50')
        self.assertEqual(m['stop'],'size-limit');self.assertEqual((out/'received.bin').read_bytes(),data[:50])
    def test_killed_collector_retains_fsynced_input_and_no_success_manifest(self):
        out=self.root/'crash';p=subprocess.Popen(self.cmd(out),stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        data=frame('crash',0,'boot')+frame('crash',1,'log',b'before reset')
        try:
            p.stdin.write(data);p.stdin.flush();end=time.monotonic()+3
            while time.monotonic()<end:
                idx=out/'chunks.jsonl'
                if idx.exists() and idx.stat().st_size>0:break
                time.sleep(.01)
            else:self.fail('collector did not persist input')
            p.kill();p.wait(timeout=3)
            self.assertEqual((out/'received.bin').read_bytes(),data);self.assertFalse((out/'manifest.json').exists())
        finally:
            if p.poll() is None:p.kill();p.wait()
            p.stdin.close();p.stderr.close()
    def test_input_device_or_symlink_is_refused_without_output(self):
        for name in ['/dev/null',str(self.root/'alias')]:
            if name!='/dev/null':Path(name).symlink_to('/dev/null')
            out=self.root/'refused';r=subprocess.run(self.cmd(out,'--input',name),capture_output=True,timeout=3)
            self.assertEqual(r.returncode,2);self.assertFalse(out.exists())
    def test_many_boots_under_low_fd_limit_keep_separate_payloads(self):
        data=b''.join(frame(f'boot-{i}',0,'boot')+frame(f'boot-{i}',1,'end',str(i).encode()) for i in range(80))
        out=self.root/'many'
        def limit_fds():resource.setrlimit(resource.RLIMIT_NOFILE,(32,32))
        r=subprocess.run(self.cmd(out),input=data,capture_output=True,timeout=10,preexec_fn=limit_fds)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(len(list((out/'boots').iterdir())),80)
        self.assertEqual((out/'boots/000001-boot-0/payload.bin').read_bytes(),b'0')
        self.assertEqual((out/'boots/000080-boot-79/payload.bin').read_bytes(),b'79')
if __name__=='__main__':unittest.main()
