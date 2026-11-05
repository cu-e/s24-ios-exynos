#!/usr/bin/env python3
"""Run source-only controls through the accepted immutable process boundary."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
p=argparse.ArgumentParser();p.add_argument('--main',required=True,type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args();wt=Path(__file__).resolve().parents[3]
helper=a.main/'worktrees/vm-035-20261106/tools/build/avf_kernel_objects.py';spec=importlib.util.spec_from_file_location('source_control_boundary',helper);h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
if h.sha(helper)!='5c7b9c549e2740f3fad2a80c060e558dff3c9aa15e98bb2d9a56b33684e687d8':raise ValueError('Changed accepted boundary')
out=h.canonical_output_path(a.out)
if not out.is_relative_to(wt/'artifacts/avf-guest-components') or out==wt/'artifacts/avf-guest-components':raise ValueError('Owned source-control output required')
out.mkdir(parents=True,exist_ok=False)
record=h.run_child([sys.executable,'-s',str(wt/'fixtures/public/avf-guest-components/controls.py'),'--main',str(a.main),'--out',str(out/'cases')],wt,out,'controls',h.supervisor(a.main),timeout=120,admit=True)
record.update(launcher_sha256=h.sha(Path(__file__)),process_helper_sha256=h.sha(helper))
h.write(out/'supervised.json',record);print(json.dumps({k:record.get(k) for k in ['outcome','exit_code','elapsed_seconds','peak_total_owned_rss_bytes','stop_reason']}));sys.exit(0 if record['outcome']=='pass' else 1)
