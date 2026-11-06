#!/usr/bin/env python3
"""Read-only frozen owner handoff and historical policy receipt intake."""
from pathlib import Path
import json,hashlib,datetime
R=Path('/home/egor/dev/pet/s24-ios-exynos');D=Path(__file__).parent;C=R/'worktrees/vm-022-tail-admission-20261106';H=C/'artifacts/avf-guest-link-inputs/actual-tail-handoff-1';P=C/'artifacts/avf-guest-link-inputs/policy-provenance-pre-run';bindings={};checks=[]
def sha(p):
 p=Path(p)
 with p.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
 bindings[str(p.relative_to(R))]=h;return h
def check(label,ok):
 checks.append(label)
 if not ok:raise ValueError(label)
def load(p,h):check('Frozen '+str(Path(p).name),sha(p)==h);return json.loads(Path(p).read_text())
actual=json.loads((D/'runs/actual2/evidence.json').read_text())
desc=load(C/'fixtures/public/avf-guest-link-inputs/built-tails.json','1ac4322a4e8b44e4e6192f6c3a7228384e7952693d1c523467c7b33a6faeb2ac')
owner=load(C/'docs/procedures/avf-guest-link-inputs/first-tail-actual-evidence.json','0f3ee01763d6debf600ceda9dc42947dfbbed5bde66b862be969fd20205930d4')
outputs=load(H/'output-bindings.json','6687fe701ccddef225d1ac3792098915673d48c45e7190d2249b831ec7f6fa9d')
# Accept either the documented map or its versioned files field, without any
# source substitution. Each physical actual output is independently streamed.
rows=outputs['files']
check('Exactly29 frozen actual output records',len(rows)==29)
for item in rows:check('Owner actual output '+Path(item['path']).name,sha(item['path'])==item['sha256'] and Path(item['path']).is_relative_to(Path(outputs['root'])))
for name,item in owner['admission_snapshots'].items():
 check('Root original snapshot equality '+name,sha(item['original']['path'])==sha(item['snapshot']['path'])==item['snapshot']['sha256']==item['original']['sha256'])
provenance=load(P/'provenance.json','652876deacb1a808b06a264d17832a730c255b5fbcfd27b1f2f1e45d1a75591d')
policy=Path(provenance['snapshot_path']);digest=sha(policy)
check('Exact archivalAF193 matches independent actual physical MAIN observation',digest==provenance['snapshot_sha256']==provenance['original_sha256']==actual['artifacts']['tools/build/avf_kernel_objects.py']=='af193e91ef5a7c24cbba0f797415cc1f2944673e62aadc6d4ace4511810582e0')
check('Pre-run identity provenance and no import/rebind authority',provenance['captured_before_run'] is True and provenance['historical_path_rebind_authorized'] is False and provenance['old_policy_import_authorized'] is False and provenance['original_canonical_path']==str(R/'tools/build/avf_kernel_objects.py'))
check('Descriptor retains exact canonical path and inspection-only archive',desc['canonical_policy']['path']==provenance['original_canonical_path'] and desc['policy_snapshot_is_inspection_only'] is True and desc['historical_path_identity_or_cross_profile_adoption_qualified'] is False)
release=json.loads((H/'tail-first25-release.json').read_text());reservation=json.loads((H/'tail-first25-allocation.reservations.json').read_text())
check('Root current-process cleanup/release witness and completed original reservation',release['current_owned_after']==[] and release['reservation_status']=='complete' and reservation['entries']['VM-022']['status']=='complete' and release['evidence_sha256']=='3abed3cb6de1cbe0c9e493340ef9b8af4fa00330d89254b5bb3dadfb87f4a0f1')
for name,item in desc['objects'].items():check('Owner descriptor actual object '+name,item['sha256']==actual['summary']['objects'][name]['sha256'])
report={'kind':'source-review','origin':'local-host','outcome':'pass','recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'task':'INT-003','owner':'codex-integrator-platform-20261106-cn','experiment':'PLATTAIL-001','checks':checks,'check_count':len(checks),'artifact_sha256':bindings,'historical_policy_observation':{'canonical_path':provenance['original_canonical_path'],'observed_actual_sha256':digest,'archival_witness':str(policy.relative_to(R)),'provenance':str((P/'provenance.json').relative_to(R)),'future_import_path_identity_or_cross_profile_rebind_accepted':False},'actual_product_scope_accepted':True,'whole_VM022_full_kernel_link_runtime_native_or_future_execution_accepted':False,'source_sha256':sha(__file__)}
(D/'runs/receipt.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'checks':len(checks),'outcome':'pass','evidence':str(D/'runs/receipt.json')}))
