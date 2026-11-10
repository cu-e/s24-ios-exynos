#!/usr/bin/env python3
"""Keep a complete command log and exit status without a shell pipeline.

No automatic retries, timeout/kill, reboot or device selection logic. An active
restore must be observed through its own log; never start a duplicate.
"""
import datetime
import json
from pathlib import Path
import subprocess
import sys
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=False)
argv=sys.argv[2:];assert argv
row=dict(argv=argv,started_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
(out/'command.json').write_text(json.dumps(row,indent=2)+'\n')
with (out/'output.log').open('wb') as log:
    p=subprocess.Popen(argv,stdout=log,stderr=subprocess.STDOUT)
    row['pid']=p.pid
    (out/'command.json').write_text(json.dumps(row,indent=2)+'\n')
    rc=p.wait()
row.update(exit_code=rc,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
(out/'command.json').write_text(json.dumps(row,indent=2)+'\n')
print('Finished:',out,'exit_code='+str(rc))
sys.exit(rc)
