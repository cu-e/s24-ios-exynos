"""Run the actual Android worker-admission class on the host JVM, including races."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


class ProbeLifecycleTests(unittest.TestCase):
    def test_one_worker_across_recreation_and_poison_survives_completion(self):
        if not shutil.which('javac') or not shutil.which('java'): self.skipTest('Host JDK unavailable')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            test=root/'GateTest.java'
            test.write_text('''package dev.egor.s24probe;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
public class GateTest {
 public static void main(String[] args) throws Exception {
  RunGate gate=new RunGate(); AtomicInteger winners=new AtomicInteger();
  CountDownLatch start=new CountDownLatch(1); Thread[] workers=new Thread[8];
  for(int i=0;i<workers.length;i++){ workers[i]=new Thread(()->{try{start.await();if(gate.tryStart())winners.incrementAndGet();}catch(Exception e){throw new RuntimeException(e);}});workers[i].start(); }
  start.countDown();for(Thread t:workers)t.join();
  if(winners.get()!=1 || !gate.isBusy() || gate.tryStart())throw new AssertionError("duplicate worker admitted");
  // A new Activity uses the same gate; cancellation does not clear it before native completion.
  if(gate.tryStart())throw new AssertionError("recreated Activity admitted another worker");
  gate.finish(false);if(!gate.tryStart())throw new AssertionError("completed worker did not release");
  gate.finish(true);if(gate.isBusy() || !gate.isPoisoned() || gate.tryStart())throw new AssertionError("poisoned process admitted work");
  gate.finish(false);if(gate.tryStart())throw new AssertionError("completion erased poison");
 }
}''')
            build=subprocess.run(['javac','--release','8','-d',str(root),str(ROOT/'src/android-probe/java/dev/egor/s24probe/RunGate.java'),str(test)],capture_output=True,text=True,timeout=20)
            self.assertEqual(build.returncode,0,build.stderr)
            run=subprocess.run(['java','-cp',str(root),'dev.egor.s24probe.GateTest'],capture_output=True,text=True,timeout=10)
            self.assertEqual(run.returncode,0,run.stderr)


if __name__=='__main__':unittest.main()
