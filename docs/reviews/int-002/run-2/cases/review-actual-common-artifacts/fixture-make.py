#!/usr/bin/python3
import fcntl,os,pathlib,subprocess,sys,time
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
