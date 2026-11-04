#!/usr/bin/env python3
"""Build the pinned open translator with a committed dependency lock; no Apple SDK."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
import sources


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',required=True);args=p.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',args.run):raise ValueError('Invalid run name')
    source=next(s for s in json.loads((ROOT/'research/sources.json').read_text())['sources'] if s['id']=='metal2vulkan')
    sources.verify(ROOT,source);checkout=ROOT/'references/metal2vulkan'
    sources.git(checkout,'sparse-checkout','add','/crates/*/Cargo.toml','/crates/*/src/','/crates/*/build.rs','/crates/*/build_support.rs','/crates/*/examples/','/LICENSE-*')
    out=ROOT/'artifacts/metal-build'/args.run
    if out.resolve()!=out:raise ValueError('Symlink run directory is not supported')
    out.mkdir(parents=True,exist_ok=False);shutil.copytree(checkout,out/'source',ignore=shutil.ignore_patterns('.git','target','__pycache__'))
    shutil.copyfile(ROOT/'src/graphics/Cargo.dependencies.lock',out/'source/Cargo.lock')
    argv=['cargo','+1.98.1','build','--locked','--manifest-path',str(out/'source/Cargo.toml'),'-p','metal2vulkan','--features','cli']
    process=subprocess.run(argv,cwd=ROOT,capture_output=True,text=True,timeout=600)
    (out/'stdout.txt').write_text(process.stdout);(out/'stderr.txt').write_text(process.stderr)
    binary=out/'source/target/debug/metal2vulkan'
    report={'source':source['revision'],'rust':'1.98.1','lock_sha256':hashlib.sha256((ROOT/'src/graphics/Cargo.dependencies.lock').read_bytes()).hexdigest(),'argv':argv,'exit_code':process.returncode,'binary':str(binary.relative_to(ROOT))}
    if binary.is_file():report['binary_sha256']=hashlib.sha256(binary.read_bytes()).hexdigest()
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));return process.returncode


if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,sources.SourceError,subprocess.TimeoutExpired) as error:print(error,file=sys.stderr);raise SystemExit(2)
