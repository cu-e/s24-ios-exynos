#!/usr/bin/env python3
"""Bounded ADB wait and minimal, read-only post-restore checks.

No content of apps, accounts or user files is read. Save only selected properties,
current numeric user id, mounted /data flag and full RECOVERY hash.
"""
from pathlib import Path
import datetime,hashlib,json,subprocess,time,sys
out=Path(sys.argv[1]);assert not out.exists()
commands=[]
def run(argv,timeout=30):
    r=subprocess.run(argv,capture_output=True,text=True,timeout=timeout)
    commands.append(dict(argv=argv,exit_code=r.returncode,stdout=r.stdout.strip(),stderr=r.stderr.strip()))
    return r
end=time.monotonic()+180
while time.monotonic()<end:
    r=subprocess.run(['adb','get-state'],capture_output=True,text=True,timeout=10)
    if r.returncode==0 and r.stdout.strip()=='device':break
    time.sleep(2)
else:
    out.write_text(json.dumps(dict(outcome='inconclusive',reason='No authorized ADB device within 180 seconds',recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat()),indent=2)+'\n');sys.exit(2)
boot_deadline=time.monotonic()+180
while time.monotonic()<boot_deadline:
    r=run(['adb','shell','getprop','sys.boot_completed'],timeout=10)
    if r.returncode==0 and r.stdout.strip()=='1':break
    time.sleep(3)
props={}
for name in ['ro.product.model','ro.product.device','ro.build.PDA','sys.boot_completed','init.svc.bootanim']:
    r=run(['adb','shell','getprop',name]);props[name]=r.stdout.strip()
assert props['ro.product.model']=='SM-S921B' and props['ro.product.device']=='e1s',props
user=run(['adb','shell','am','get-current-user'])
data=run(['adb','shell',"if test -d /data/user/0 && test -d /data/app; then echo user_data_directories_present; else echo unavailable; fi"])
root_hash=run(['adb','shell',"su -c 'sha256sum /dev/block/by-name/recovery'"],timeout=120)
expected='96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67'
hash_ok=root_hash.returncode==0 and root_hash.stdout.split()[:1]==[expected]
result=dict(recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),properties=props,current_user=user.stdout.strip(),user_data_directories=data.stdout.strip(),recovery_hash_match=hash_ok,commands=commands)
result['outcome']='pass' if hash_ok and props['sys.boot_completed']=='1' and data.stdout.strip()=='user_data_directories_present' else 'inconclusive'
out.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='commands'},indent=2))
sys.exit(0 if result['outcome']=='pass' else 2)
