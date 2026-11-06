#!/usr/bin/env python3
"""Focused fictional negative admission fixtures, using frozen actual AF193 APIs."""
import copy
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import review


def run(out):
    out.mkdir(parents=True, exist_ok=False)
    policy = Path(__file__).resolve().parents[3] / 'tools/build/avf_kernel_objects.py'
    expected = 'af193e91ef5a7c24cbba0f797415cc1f2944673e62aadc6d4ace4511810582e0'
    assert review.sha(policy) == expected, 'Explicit reviewer-only historical policy import changed'
    assert review.sha(review.SOURCE) == review.SOURCE_SHA
    common = review.load(policy, 'review_frozen_af193_only')
    module = review.load(review.SOURCE, 'review_admission')
    checks = []
    def check(name, condition, detail=None):
        checks.append(dict(name=name,pass_=bool(condition),detail=detail))
    initial = module.proc_status()
    prefix = review.AUTHOR / 'artifacts/avf-guest-link-inputs'
    for mode, kind in [('production','link-vectors-2'), ('xnup','xnup-vectors-2')]:
        frozen = json.loads((prefix/kind/'execution-plan.json').read_text())
        args = SimpleNamespace(main=review.MAIN, vm008=review.MAIN/'worktrees/vm-008-20261105',
                               execute_out=Path(frozen['actual_output']),admission=None)
        actual = module.production_vectors(args,common) if mode == 'production' else module.xnup_vectors(args,common)
        check(mode+'-actual-vector-reconstruction', actual == frozen)

    manifest = review.MAIN/'worktrees/vm-008-20261105/artifacts/avf-kernel-headers/handoff-1/next-full-object-manifest.json'
    rows = common.load_project(manifest, common.PIN)
    common.validate_graph(rows)
    row = rows[0]
    identifier = row['id']
    source = row['bound_source']
    assert review.sha(source) == row['bound_source_sha256']
    original_argv = common.expand(row,out)
    obj = out/'objects'/identifier
    dep = out/'dependencies'/(identifier+'.d')
    obj.parent.mkdir(parents=True); dep.parent.mkdir(parents=True)
    obj.write_bytes(review.macho(False))
    dep.write_text(str(obj)+': '+source+'\n')
    selected = dict(id=identifier,input_key='FICTIONAL-UNRECOMPUTED-KEY',source=source,
                    source_sha256=row['bound_source_sha256'],configuration=row['configuration'],
                    configuration_sha256=row['configuration_sha256'],
                    recipe_sha256=common.canonical(row['next_owned_compile_argv_template']),
                    argv=original_argv,cwd=row['cwd'])
    record = dict(id=identifier,input_key=selected['input_key'],source=source,source_sha256=row['bound_source_sha256'],
                  cwd=row['cwd'],outcome='pass',object=str(obj),object_sha256=review.sha(obj),
                  dependency_file=str(dep),dependency_file_sha256=review.sha(dep),
                  object_validation=common.macho(obj),dependencies={source:row['bound_source_sha256']},
                  command=dict(outcome='pass',exit_code=0,argv=original_argv,after=dict(owned_processes=[])))
    execution = dict(task='FIXTURE-ORIGINAL',owner='fixture-original-owner',shard='fixture-shard',
                     provenance=dict(compiler_sha256=common.COMPILER),selected=[selected])
    namespace = out/'namespace.json'
    review.write(namespace,dict(sha256='FIXTURE-NAMESPACE',files={source:row['bound_source_sha256']}))
    resource = out/'resource.json'
    review.write(resource,dict(outcome='pass',fixture_only=True))
    def binding(path):
        return dict(path=str(path),sha256=review.sha(path))
    profile = dict(manifest=binding(manifest),namespace_receipt=binding(namespace),
                   namespace_sha256='FIXTURE-NAMESPACE',resource_evidence=binding(resource))
    raw = dict(task='FIXTURE-ORIGINAL',owner='fixture-original-owner',outcome='pass',shard='fixture-shard',
               ownership_binding=dict(task='FIXTURE-ORIGINAL',owner='fixture-original-owner',mode='execute',
                   requested_shard='fixture-shard',authorized_shards=['fixture-shard'],source_only_tooling_exception=False,
                   paths=['fixtures/public/avf-object-shards/fixture-shard','docs/procedures/avf-object-shards/fixture-shard']),
               provenance=dict(manifest_sha256=common.PIN,namespace_sha256='FIXTURE-NAMESPACE',compiler_sha256=common.COMPILER),
               objects=[])
    baseline = (copy.deepcopy(raw),copy.deepcopy(record),copy.deepcopy(execution))
    cases = ['baseline-to-missing1080-boundary','wrong-literal-owner','wrong-literal-task',
             'missing-literal-reservations','source-only-raw','compiler-never-started',
             'wrong-raw-compiler-hash','wrong-plan-compiler-hash','forged-input-key',
             'failed-object','changed-argv','live-owned-process','wrong-source','foreign-shard',
             'cross-profile-namespace','duplicate-object']
    try:
        module.LINK_PROFILE_PINS[common.PIN] = profile
        for case in cases:
            raw,record,execution = copy.deepcopy(baseline)
            if case == 'wrong-literal-owner':raw['ownership_binding']['owner'] = 'UNRELATED-OWNER'
            if case == 'wrong-literal-task':raw['ownership_binding']['task'] = 'VM-039'
            if case == 'missing-literal-reservations':raw['ownership_binding']['paths'] = []
            if case == 'source-only-raw':raw['source_only'] = True
            if case == 'compiler-never-started':raw['compiler_started'] = False
            if case == 'wrong-raw-compiler-hash':raw['provenance']['compiler_sha256'] = '0'*64
            if case == 'wrong-plan-compiler-hash':execution['provenance']['compiler_sha256'] = '0'*64
            if case == 'forged-input-key':
                record['input_key'] = execution['selected'][0]['input_key'] = 'NEITHER-QUALIFIED-NOR-DERIVED'
            if case == 'failed-object':record['outcome'] = 'fail'
            if case == 'changed-argv':record['command']['argv'] = ['fictional-wrong-compiler']
            if case == 'live-owned-process':record['command']['after']['owned_processes'] = [dict(state='S')]
            if case == 'wrong-source':record['source_sha256'] = '0'*64
            if case == 'foreign-shard':raw['shard'] = 'foreign'
            if case == 'cross-profile-namespace':raw['provenance']['namespace_sha256'] = 'OTHER'
            record_path, execution_path, raw_path = out/'record.json',out/'execution-plan.json',out/'raw.json'
            review.write(record_path,record);review.write(execution_path,execution)
            raw['objects'] = [dict(id=identifier,record=str(record_path),record_sha256=review.sha(record_path))]
            review.write(raw_path,raw)
            accepted = out/'acceptance.json'
            review.write(accepted,dict(schema='avf-guest-link-acceptance-v1',outcome='pass',profile=profile,
                                     accepted_evidence={str(resource):review.sha(resource),str(raw_path):review.sha(raw_path)},
                                     fixture_only=True))
            item = dict(id=identifier,raw_evidence=binding(raw_path),record=binding(record_path),execution_plan=binding(execution_path))
            request = dict(schema='avf-guest-link-admission-v1',profile=profile,acceptance=binding(accepted),objects=[item])
            if case == 'duplicate-object':request['objects'].append(item)
            rejected, boundary, error = False,False,None
            try:
                module.admission_inputs(request,dict(ordered_ids=[r['id'] for r in rows]),common)
            except ValueError as caught:
                error = str(caught)
                boundary = error.startswith('Missing accepted measured object IDs:')
                rejected = not boundary
            check(case, boundary if case == cases[0] else rejected,
                  dict(first_object_credited_before_missing1080=boundary,error=error,
                       no_actual_input_credit=True,fixture_only=True))
            case_out = out/case
            case_out.mkdir()
            for name,value in [('record',record),('execution-plan',execution),('raw',raw),('admission',request)]:
                review.write(case_out/(name+'.json'),value)
    finally:
        module.LINK_PROFILE_PINS.clear()
    check('empty-profile-allowlist-restored',module.LINK_PROFILE_PINS == {})
    check('source-unchanged',review.sha(review.SOURCE) == review.SOURCE_SHA)
    evidence = dict(task='REV-041',experiment='REVMAIN-001',outcome='pass' if all(x['pass_'] for x in checks) else 'fail',
                    checks=checks,failed=[x['name'] for x in checks if not x['pass_']],
                    explicit_review_only_policy=dict(path=str(policy),sha256=review.sha(policy)),
                    production_pins_rebound=False,actual_common_reusable=True,read_bypass=False,
                    initial_process=initial,final_process=module.proc_status(),argv=sys.argv,
                    script_sha256=review.sha(__file__),no_target_tools=True,no_production_grant=True)
    evidence['artifacts_sha256'] = {str(p.relative_to(out)):review.sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    review.write(out/'evidence.json',evidence)
    print(json.dumps(dict(outcome=evidence['outcome'],checks=len(checks),failed=evidence['failed'],final_process=evidence['final_process']),indent=2))
    return 0 if evidence['outcome'] == 'pass' else 2


if __name__ == '__main__':
    raise SystemExit(run(Path(sys.argv[1]).resolve()))
