#!/usr/bin/python3
"""Trace real MIG preprocessing and propagate its exact exit status."""
from pathlib import Path
import hashlib
import json
import os
import shlex
import subprocess
import sys

trace=Path(os.environ['S24_MIG_TRACE'])
compiler=Path(os.environ['S24_MIG_COMPILER'])
source=Path(os.environ['S24_MIG_SOURCE'])
arguments=sys.argv[1:]
if '-E' not in arguments or len([a for a in arguments if a.endswith('.c')])!=1:
    raise ValueError('Expected one actual MIG temporary C preprocessor input')
temporary=Path(next(a for a in arguments if a.endswith('.c')))
body=temporary.read_bytes()
expected=('#line 1 "'+str(source)+'"\n').encode()+source.read_bytes()
if body!=expected:raise ValueError('MIG temporary bytes differ from selected source')
(trace/'input.c').write_bytes(body)
dep=trace/'inputs.d'
argv=[str(compiler),*arguments,'-MD','-MF',str(dep),'-MT','preprocessing.o']
with (trace/'output.i').open('wb') as stdout:
    result=subprocess.run(argv,stdout=stdout)
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
inputs={str(source):sha(source)}
if result.returncode==0:
    line=dep.read_text().replace('\\\n',' ').splitlines()[0]
    for name in shlex.split(line.split(':',1)[1]):
        path=(Path.cwd()/name).resolve()
        if path==temporary.resolve():continue
        inputs[str(path)]=sha(path)
(trace/'provenance.json').write_text(json.dumps(dict(argv=argv,cwd=str(Path.cwd()),
    exit_code=result.returncode,inputs=inputs,temporary_sha256=sha(trace/'input.c'),
    preprocessed_sha256=sha(trace/'output.i')),indent=2)+'\n')
with (trace/'output.i').open('rb') as f:
    while data:=f.read(65536):sys.stdout.buffer.write(data)
sys.stdout.buffer.flush()
sys.exit(result.returncode)
