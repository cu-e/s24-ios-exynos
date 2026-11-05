#!/usr/bin/env python3
"""Narrow corrected-predicate recheck; no source/header matrix regeneration."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
FH = MAIN/'worktrees/vm-020-20261106'
PTH = MAIN/'worktrees/vm-021-20261106'
ENV = dict(os.environ, GIT_NO_LAZY_FETCH='1', GIT_OPTIONAL_LOCKS='0', PYTHONDONTWRITEBYTECODE='1')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def main():
    name = sys.argv[1]
    assert re.fullmatch(r'[A-Za-z0-9_-]+', name)
    out = HERE/'runs'/name; out.mkdir(parents=True, exist_ok=False)
    r = dict(kind='source-review', origin='local-host', outcome='fail', task='INT-003',
             recorded_at=datetime.now(timezone.utc).isoformat(), commands=[], bindings={}, controls=[], admission=[],
             source_header_matrix_repeated=False, compiler_executed=False, guest_executed=False,
             registry_mutated=False, compiled_ABI_qualified=False, provider_closure_qualified=False)

    def bind(path, expected=None):
        actual = sha(path)
        if expected is not None and actual != expected:
            raise ValueError('Changed frozen input: '+str(path))
        r['bindings'][str(path)] = actual

    def frozen(commit, relative, actual):
        argv = ['git','-C',str(MAIN),'show',commit+':'+relative]
        p = subprocess.run(argv, env=ENV, capture_output=True, timeout=30)
        r['commands'].append(dict(argv=argv, exit_code=p.returncode, stdout_sha256=hashlib.sha256(p.stdout).hexdigest(), stderr_sha256=hashlib.sha256(p.stderr).hexdigest()))
        if p.returncode:
            raise ValueError('Frozen source unavailable')
        bind(actual, hashlib.sha256(p.stdout).hexdigest())

    def reject(label, fn):
        try:
            fn()
        except ValueError as e:
            r['controls'].append(dict(name=label, rejected=True, message=str(e)))
        else:
            raise ValueError('Corrected predicate accepted: '+label)

    try:
        bind(__file__); bind(HERE/'guard-procedure.md')
        for i in range(3):
            n = int(re.search(r'^MemAvailable:\s+(\d+)',Path('/proc/meminfo').read_text(),re.M)[1])
            r['admission'].append(dict(at=datetime.now(timezone.utc).isoformat(), MemAvailable_KiB=n))
            if n < 4194304:
                raise ValueError('Resource-deferred before source children below4GiB')
            if i < 2:
                time.sleep(1)
        fhcommit = '27303145d33105170a6f9623240c5be0685675fc'
        pthcommit = '1df0f1c9869bc93201a77b897a6ca515c5e7f560'
        r['corrected_source_commits'] = dict(VM020=fhcommit, VM021=pthcommit, VM021_documentation='34443d5a2c87525cecb7521fbe5dd1e00e7174d9')
        for commit, relative, actual in [
            (fhcommit,'tools/build/avf_guest_firehose.py',FH/'tools/build/avf_guest_firehose.py'),
            (pthcommit,'tools/build/avf_guest_pthread.py',PTH/'tools/build/avf_guest_pthread.py'),
            (pthcommit,'fixtures/public/avf-guest-pthread/execution-plan-freeze.json',PTH/'fixtures/public/avf-guest-pthread/execution-plan-freeze.json')]:
            frozen(commit, relative, actual)
        bind(FH/'docs/procedures/avf-guest-firehose/admission-controls-session2.json','5d2212987504e84712b5d10c5bafe8d4b5626c2f2bfb429dc0d63914b8d2926a')
        bind(PTH/'artifacts/avf-guest-pthread/predicate-controls-1/evidence.json','c16f8c71f2ba6deaa8a57b7fa0e0d2eb80087646d08976b5bd9b23d9228ba803')
        bind(PTH/'docs/procedures/avf-guest-pthread/predicate-evidence.json','30d4bbb14e277216cb0cbd9718290f17378d58d6593a8143729a170307504b0f')
        fhplan = FH/'docs/procedures/avf-guest-firehose/preparation-session3/compile-plan.json'
        pthplan = PTH/'artifacts/avf-guest-pthread/prepare-2/component-plan.json'
        bind(fhplan,'f6c1f5ef1dd60353ae887bc257f0c900f0c8ba0fdf8f5bb1c3e31c62b940b197')
        bind(pthplan,'96065bf4ebe697cfd1a0d43eb52d0ae315275f25efe619e60ae14d66ae350298')
        fm = module(FH/'tools/build/avf_guest_firehose.py','corrected_firehose')
        pm = module(PTH/'tools/build/avf_guest_pthread.py','corrected_pthread')
        manifest = MAIN/fm.MANIFEST; bind(manifest,fm.MANIFEST_SHA256)
        row = next(x for x in load(manifest) if x['id']=='bsd/subr_log.o')
        compiler = Path(row['next_owned_compile_argv_template'][0])
        fm.validate_guest_row(deepcopy(row),MAIN,compiler)
        canonical_argv = json.dumps(row['next_owned_compile_argv_template'],ensure_ascii=True,separators=(',',':')).encode('ascii')
        assert hashlib.sha256(canonical_argv).hexdigest() == fm.GUEST_ARGV_SHA256 == 'cf737937e6e6c74f00302f2bebcc1ec6a08329fb48ab35b451dd226f590113ca'
        for label, tokens in [('undef-development',['-UDEVELOPMENT']),('development-zero',['-DDEVELOPMENT=0']),
                              ('split-development-zero',['-D','DEVELOPMENT=0']),('undef-board',['-UARM64_BOARD_CONFIG_BCM2837']),
                              ('response-file',['@/tmp/unapproved.args']),('wrong-target',['-target','x86_64-apple-ios16.5'])]:
            changed = deepcopy(row); changed['next_owned_compile_argv_template'] += tokens
            reject('VM020-'+label,lambda:fm.validate_guest_row(changed,MAIN,compiler))
        changed = deepcopy(row); changed['next_owned_compile_argv_template'].remove('-DDEVELOPMENT')
        reject('VM020-remove-development',lambda:fm.validate_guest_row(changed,MAIN,compiler))
        plan = load(pthplan); pm.validate_plan(deepcopy(plan))
        freeze = load(pm.EXECUTION_FREEZE)
        canonical_plan = json.dumps(plan,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('utf-8')
        assert hashlib.sha256(canonical_plan).hexdigest() == freeze['canonical_plan_sha256'] == 'bfb88d88d6f44d936fd1fc5758b687ba29ca50f19626e6750224d6db2d69f475'
        changed = deepcopy(plan)
        for x in changed['translation_units']:
            x['argv_template'] = [a for a in x['argv_template'] if a not in ['-DMACH_ASSERT','-DDEBUG']]
        reject('VM021-original-drop-both-development-definitions',lambda:pm.validate_plan(changed))
        for label, token in [('undef-debug','-UDEBUG'),('undef-mach-assert','-UMACH_ASSERT'),('debug-zero','-DDEBUG=0'),('ndebug','-DNDEBUG')]:
            changed=deepcopy(plan); changed['translation_units'][0]['argv_template'].append(token)
            reject('VM021-'+label,lambda:pm.validate_plan(changed))
        for label, option, value in [('output','-o','/tmp/unowned.o'),('target','-target','x86_64-apple-ios16.5')]:
            changed=deepcopy(plan); argv=changed['translation_units'][0]['argv_template']; argv[argv.index(option)+1]=value
            reject('VM021-change-'+label,lambda:pm.validate_plan(changed))
        changed=deepcopy(plan); changed['translation_units'][0]['argv_template'][0]='/tmp/clang'
        reject('VM021-change-compiler',lambda:pm.validate_plan(changed))
        changed=deepcopy(plan); changed['translation_units'][0]['source']='/tmp/changed.c'
        reject('VM021-change-source-metadata',lambda:pm.validate_plan(changed))
        bind(fhplan,r['bindings'][str(fhplan)]);bind(pthplan,r['bindings'][str(pthplan)])
        r['positives']=dict(firehose_exact_frozen_row=True,pthread_exact_frozen_plan=True,original_plan_bytes_unchanged=True)
        r['outcome']='pass';r['summary']='Both observed source-predicate gaps reject under corrected exact fingerprints; original good plans unchanged; source-only'
    except Exception as e:
        r['error']=repr(e);r['summary']='Narrow guard recheck failed/deferred; no compile or source/header matrix repeat'
    finally:
        r['process_memory']=[s for s in Path('/proc/self/status').read_text().splitlines() if s.startswith(('VmHWM:','VmRSS:'))]
        r['finished_at']=datetime.now(timezone.utc).isoformat()
        (out/'evidence.json').write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps({k:r.get(k) for k in ['outcome','summary','error','positives','process_memory']},indent=2))
    return r['outcome']!='pass'


if __name__=='__main__':
    raise SystemExit(main())
