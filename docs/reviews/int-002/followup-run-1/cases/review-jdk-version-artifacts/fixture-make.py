#!/usr/bin/python3
import fcntl,json,os,pathlib,resource,subprocess,sys
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
