#!/usr/bin/env python3
"""Stage exact accepted component commits; never publish or execute tools."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
from datetime import datetime, timezone

MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
REPORT = MAIN/'worktrees/int-platform-20261106'
OUT = REPORT/'artifacts/platform-integration/components-stage1'
WT = MAIN/'worktrees/int-components-20261106'
BRANCH = 'team/int-components-20261106'
SOURCES = ['8b11fb80061d18f9c0c9c34b952e67b4bd54a8d1',
 'ada7eb273eba64256b54b34e57401dac85d8d2de',
 'df11548f2c31ba4434d290ba353a0e4e962730f3',
 'd5553d007ff1da656b3702ce84f92b67df77ce5b',
 'fd5ae5588033e53a0b85b705b56969977db667c1',
 '4d7a46214945fd16986cdfe24e3e3c60ad90b272',
 'fa310c575da8d638f06a22b9f025ccfcccd12fd4']
ENV = dict(os.environ, GIT_NO_LAZY_FETCH='1', GIT_OPTIONAL_LOCKS='0',
           LC_ALL='C', PYTHONDONTWRITEBYTECODE='1')
LOG = []

def digest(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def git(cwd, *args):
    r = subprocess.run(['git', *args], cwd=cwd, env=ENV, capture_output=True, timeout=45)
    LOG.append({'argv':['git',*args], 'cwd':str(cwd), 'exit_code':r.returncode,
                'stdout_sha256':hashlib.sha256(r.stdout).hexdigest(),
                'stderr':r.stderr.decode(errors='replace')})
    if r.returncode:
        raise RuntimeError(r.stderr.decode(errors='replace'))
    return r.stdout

def allowed(p):
    return (p == 'tools/build/avf_guest_components.py' or
            p.startswith(('fixtures/public/avf-guest-components/',
                          'docs/procedures/avf-guest-components/',
                          'docs/integration/platform/')))

def main():
    OUT.mkdir(parents=True, exist_ok=False)
    if WT.exists():
        raise RuntimeError('Candidate path already exists; preserve it')
    base = git(MAIN, 'rev-parse', 'HEAD').decode().strip()
    git(MAIN, 'worktree', 'add', '-b', BRANCH, str(WT), base)
    mapping = []
    for i, source in enumerate(SOURCES):
        paths = git(MAIN, 'diff-tree', '--no-commit-id', '--name-only', '-r', source).decode().splitlines()
        if not paths or not all(allowed(p) for p in paths):
            raise RuntimeError('Source path scope mismatch')
        git(WT, 'cherry-pick', source)
        candidate = git(WT, 'rev-parse', 'HEAD').decode().strip()
        shas = []
        for role, commit in [('source',source),('candidate',candidate)]:
            raw = git(MAIN, 'show', '--format=', '--binary', '--full-index',
                      '--no-ext-diff', '--no-textconv', '--no-renames', commit)
            p = OUT/f'{i:02d}-{role}.patch'
            p.write_bytes(raw)
            shas.append(digest(p))
        if shas[0] != shas[1]:
            raise RuntimeError('Mapped exact patch mismatch')
        mapping.append({'source':source,'candidate':candidate,'patch_sha256':shas[0]})
    head = git(WT, 'rev-parse', 'HEAD').decode().strip()
    paths = git(WT, 'diff', '--name-only', base, head).decode().splitlines()
    if not all(allowed(p) for p in paths):
        raise RuntimeError('Final path scope mismatch')
    git(WT, 'diff', '--check', base, head)
    if git(WT, 'status', '--porcelain=v1', '--untracked-files=no'):
        raise RuntimeError('Candidate is dirty')
    source_root = MAIN/'worktrees/vm-036-dz-fix2-20261106'
    final = []
    bindings = {}
    for name in paths:
        origin = REPORT if name.startswith('docs/integration/platform/') else source_root
        if (WT/name).read_bytes() != (origin/name).read_bytes():
            raise RuntimeError(f'Final frozen source mismatch: {name}')
        for p in [WT/name, origin/name]:
            bindings[str(p.relative_to(MAIN))] = digest(p)
        final.append({'path':name,'sha256':digest(WT/name)})
    witnesses = [
      source_root/'artifacts/avf-guest-components/handoff-003/evidence.json',
      MAIN/'worktrees/vm-036-dz-fix1-20261106/artifacts/avf-guest-components/handoff-002/evidence.json',
      REPORT/'docs/integration/platform/component-adapter-review-20261106/evidence-fail1.json',
      REPORT/'docs/integration/platform/component-adapter-review-20261106/evidence-pass2.json',
      REPORT/'docs/integration/platform/component-adapter-review-20261106/runs/regression1/supervised.json',
      REPORT/'docs/integration/platform/component-adapter-review-20261106/runs/regression1/evidence.json',
      MAIN/'tools/integration_gate.py']
    for p in witnesses:
        bindings[str(p.relative_to(MAIN))] = digest(p)
    policy = json.loads((WT/'fixtures/public/avf-guest-components/policy.json').read_bytes())
    if policy['prospective_process']['independently_accepted'] is not False:
        raise RuntimeError('Unexpected process-policy adoption')
    plan = {'base_head':base,'candidate_head':head,'candidate_worktree':str(WT.relative_to(MAIN)),
            'commits':[m['candidate'] for m in mapping],
            'commit_map':[{'source':m['source'],'candidate':m['candidate']} for m in mapping],
            'paths':paths,'bindings':[{'path':p,'sha256':s} for p,s in sorted(bindings.items())]}
    (OUT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    evidence = {'kind':'source-review','origin':'local-host','task':'INT-003',
      'owner':'codex-integrator-platform-20261106-cn','experiment':'PLATCOMPINT-001',
      'recorded_at':datetime.now(timezone.utc).isoformat(),'outcome':'pass',
      'summary':'Exact reviewed VM036 chain staged unchanged, unpublished; provisional base before039 and no policy adoption.',
      'base_head':base,'candidate_head':head,'commit_map':mapping,'files':final,
      'plan_sha256':digest(OUT/'plan.json'),'commands':LOG,
      'prepare_source_sha256':digest(Path(__file__)),
      'source_capsule_sha256':digest(witnesses[0]),'deep_capsule_remeasurement':False,
      'publication_or_common_or_compiler_executed':False,'policy_independently_accepted':False,
      'gate_audit_executed':False,
      'next':'After039 accepted publication, refresh exact base and add only separately reviewed original-owner policy adoption before root approval.'}
    (OUT/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps({'candidate':head,'base':base,'commits':len(mapping),'paths':len(paths),
                      'bindings':len(bindings),'plan_sha256':digest(OUT/'plan.json'),
                      'evidence_sha256':digest(OUT/'evidence.json')}))

if __name__ == '__main__':
    try:
        main()
    except Exception:
        if OUT.is_dir():
            (OUT/'failed-commands.json').write_text(json.dumps(LOG,indent=2)+'\n')
        raise
