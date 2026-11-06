#!/usr/bin/env python3
"""Bounded source-control worker; uses accepted shared child engine unchanged."""
import importlib.util
import json
from pathlib import Path
import sys
import time

sys.dont_write_bytecode=True
root=Path(__file__).resolve().parents[3]
scope=root/"src/platform/gpu/native/userclient"
sys.path.insert(0,str(scope))
import admission
import launcher

out=Path(sys.argv[1]);case=sys.argv[2]
spec=admission.policy()
helper=admission.module(spec["source_control_helper"],"gpu_control_shared")
supervisor=admission.module(spec["source_control_supervisor"],"gpu_control_supervisor")
started=time.monotonic()
record={"case":case,"compiler":False,"sanitizer":False,"resource_allocation":False}
def run():
    return helper.run_child([sys.executable,"-s",str(root/"fixtures/public/gpu-userclient/process_probe.py"),str(out),"exit" if case=="normal" else "wait"],out,out,"probe",supervisor,timeout=.3 if case=="child-deadline" else 10,admit=False)
try:
    record["launcher"]=launcher.guarded(run,.8 if case=="whole-deadline" else 8)
finally:
    ready=out/"probe-ready.json"
    record["identities"]=json.loads(ready.read_text()) if ready.exists() else []
    session=record["identities"][0]["session"] if record["identities"] else record.get("launcher",{}).get("result",{}).get("owned_session")
    record["after"]=supervisor.sample(session)["owned_processes"] if session else []
    record["elapsed_seconds"]=time.monotonic()-started
    record["proc_status"]=[l for l in Path('/proc/self/status').read_text().splitlines() if l.startswith(("VmHWM:","VmRSS:"))]
    (out/"worker.json").write_text(json.dumps(record,indent=2)+"\n")
