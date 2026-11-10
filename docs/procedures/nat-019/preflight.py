#!/usr/bin/env python3
"""Host preflight for current request; cannot flash or reboot a phone."""
from pathlib import Path
import argparse,datetime,hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[3]
def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    commands=[]
    def run(argv):
        r=subprocess.run(list(map(str,argv)),cwd=ROOT,capture_output=True,text=True,timeout=60)
        commands.append(dict(argv=list(map(str,argv)),exit_code=r.returncode,stdout=r.stdout,stderr=r.stderr))
        (a.out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        if r.returncode:raise RuntimeError('host range probe failed; no native operation allowed')
        return r.stdout
    exe=a.out.resolve()/'range_probe'
    run(['clang','-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all','-Isrc/native/watchdog','docs/procedures/nat-019/range_probe.c','src/native/watchdog/s5e9945.c','-o',exe])
    rows=json.loads(run([exe]));(a.out/'range.json').write_text(json.dumps(rows,indent=2)+'\n')
    row=next(r for r in rows if r['requested_seconds']==120)
    assert row['return_code']==-1 and row['registers_unchanged']
    # This report is a current readiness assessment, not a permissive flashing API.
    blockers=[
      '120 seconds is rejected by the actual watchdog API at the cited 25.6MHz rate (prescaler would be 367 >256).',
      'No qualified native early-log receiver. Host enumeration shows Android ADB only and no USB serial adapters; current loader logs only to image RAM.',
      'Existing payload command line lacks an explicit RAM-root/internal-storage-disable contract. No fresh linked-image no-write audit exists.',
      'Automatic one-shot Android return after watchdog reset is unqualified; the prior experimental attempt looped.']
    files=['src/native/watchdog/s5e9945.c','src/native/watchdog/s5e9945.h','docs/procedures/nat-019/range_probe.c','docs/procedures/nat-019/preflight.py']
    result=dict(recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),kind='host-test',origin='local-host',readiness='not-ready',requested_watchdog_seconds=120,nominal_max_seconds=65535*256*128/25600000,blockers=blockers,range_probe=rows,device_write_performed=False,image_built=False,reboot_performed=False,sha256={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files})
    (a.out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));return 2
if __name__=='__main__':sys.exit(main())
