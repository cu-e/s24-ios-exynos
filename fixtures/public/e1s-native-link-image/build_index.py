#!/usr/bin/env python3
"""Join the 916-row accepted index with the 126 BSD-a products and requalify all 1042.

Runs no compiler or linker. Output is the complete native body index and a physical
requalification record; neither alone authorizes linking.
"""
import argparse
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
COMMON = (MAIN/'tools/build/avf_kernel_objects.py', '9929a7d6f1e748770f54abf3e101350648092027a18c419a242d0348f620f755')
INDEX916 = (MAIN/'worktrees/int-e1s-profile-20261106/artifacts/integration-gate/e1s-source-review-20261106/native-current916-actual-index.json', '5e23b1952fee2bfd81b52c754e2d9fa2ff336f2713c88383567696a6dd2aa02e')
TAIL = MAIN/'worktrees/str-040-e1s-native-bsd-a-tail-20261110'
PRODUCTS65 = TAIL/'artifacts/e1s-native-objects/bsd-a-tail/products-65.json'
EVIDENCE61 = TAIL/'artifacts/e1s-native-compile/bsd-a-tail-001/evidence.json'
PLAN61 = TAIL/'docs/procedures/e1s-native-objects/bsd-a-tail/plan-001/plan.json'
ORIGINS170 = TAIL/'docs/procedures/e1s-native-objects/bsd-a-tail/complete-170-origins.json'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_common():
    raw = COMMON[0].read_bytes()
    require(hashlib.sha256(raw).hexdigest() == COMMON[1], 'Changed common helper')
    spec = importlib.util.spec_from_file_location('index_common', COMMON[0])
    module = importlib.util.module_from_spec(spec)
    exec(compile(raw, str(COMMON[0]), 'exec'), module.__dict__)
    return module


def bind(path):
    return {'path': str(path), 'sha256': sha(path)}


def row_65(item, component, authority):
    return dict(id=item['id'], component=component, object={'path': item['object'], 'sha256': item['object_sha256']},
                depfile={'path': item['depfile'], 'sha256': item['depfile_sha256']}, source=item['source'], recipe=item['recipe'],
                actual_tuple_authority={**authority, 'format': 'list-of-independent-actual-products', 'row_id': item['id']},
                actual_argv_sha256=canonical(item['actual_argv']), actual_cwd=item['actual_cwd'],
                actual_MD_map_sha256=canonical(item['actual_MD_dependencies']), actual_MD_dependency_count=len(item['actual_MD_dependencies']),
                actual_object_input_resource_qualification='pass')


def row_61(obj, process, source, component, authority, plan_ref):
    return dict(id=obj['id'], component=component, object={'path': obj['object'], 'sha256': obj['object_sha256']},
                depfile={'path': obj['depfile'], 'sha256': obj['depfile_sha256']},
                source={'path': source['source'], 'sha256': source['source_sha256']}, recipe=source['recipe'],
                actual_tuple_authority={**authority, 'format': 'native-worker-evidence', 'objects_collection': 'objects', 'command_role': obj['id'], 'source_plan': plan_ref},
                actual_argv_sha256=canonical(process['argv']), actual_cwd=process['cwd'], actual_MD_map_sha256=canonical(obj['dependencies']),
                actual_MD_dependency_count=len(obj['dependencies']), actual_object_input_resource_qualification='pass')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--index916-sha256', default=INDEX916[1])
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    common = load_common()
    require(sha(INDEX916[0]) == args.index916_sha256, 'Accepted 916 index changed')
    base = json.loads(INDEX916[0].read_text())
    require(base['owner'] == 'INT-002' and len(base['rows']) == 916 and base['baseline_ABSENT_count'] == 126, 'Unexpected baseline index')
    graph = json.loads(Path(base['graph']['path']).read_text())
    order = [row['id'] for row in graph['objects']]
    component = {row['id']: row['component'] for row in graph['objects']}

    products = json.loads(PRODUCTS65.read_text())
    origins = json.loads(ORIGINS170.read_text())
    authority65 = bind(PRODUCTS65)
    rows65 = [row_65(item, component[item['id']], authority65) for item in products]

    evidence = json.loads(EVIDENCE61.read_text())
    plan = json.loads(PLAN61.read_text())
    processes = {c['role']: c['process'] for c in evidence['commands']}
    sources = {c['id']: c for c in plan['commands']}
    authority61 = bind(EVIDENCE61)
    plan_ref = {'path': str(PLAN61.relative_to(MAIN)), 'sha256': sha(PLAN61), 'bytes': PLAN61.stat().st_size}
    rows61 = [row_61(obj, processes[obj['id']], sources[obj['id']], component[obj['id']], authority61, plan_ref) for obj in evidence['objects']]

    added = {row['id']: row for row in rows65+rows61}
    require(len(added) == 126 and set(added) == set(base['ABSENT_ids']) and not set(added) & {r['id'] for r in base['rows']}, 'Added rows do not fill exactly the absent set')
    require({o['id'] for o in origins['origins'][44:]} == set(added), 'Origins disagree with added rows')
    existing = {row['id']: row for row in base['rows']}
    merged = [existing.get(i) or added[i] for i in order]
    require(len(merged) == 1042 and [r['id'] for r in merged] == order, 'Merged rows differ from graph order')

    verified = 0
    for row in merged:
        require(sha(row['object']['path']) == row['object']['sha256'] and sha(row['depfile']['path']) == row['depfile']['sha256'], 'Changed product: '+row['id'])
        result = common.macho(row['object']['path'], row['id'] == 'libkern/OSData.cpo')
        require(result['arm64_macho_object'] is True and result['sha256'] == row['object']['sha256'], 'Not ARM64 Mach-O: '+row['id'])
        verified += 1

    index = {key: base[key] for key in base if key not in ('rows', 'ABSENT_ids', 'owner', 'recorded_at', 'main_head', 'baseline_accepted_count', 'baseline_ABSENT_count', 'final_available_slots_with_overrides', 'final_ABSENT_slots_with_overrides', 'limits', 'producer_continuation_contract')}
    index.update(owner='STR-041', recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
                 rows=merged, ABSENT_ids=[], baseline_accepted_count=1042, baseline_ABSENT_count=0,
                 final_available_slots_with_overrides=1042, final_ABSENT_slots_with_overrides=0,
                 parent_index={'path': str(INDEX916[0]), 'sha256': args.index916_sha256, 'owner': 'INT-002', 'rows': 916},
                 limits=['Join of 916 accepted INT-002 rows and 126 BSD-a rows; every object and depfile re-hashed and parsed as ARM64 Mach-O here.', 'No link, private37 ABI, runtime, physical ownership or hardware qualification.'])
    path = args.out/'native-complete-1042-index.json'
    path.write_text(json.dumps(index, indent=1)+'\n')
    written = {row['id']: row for row in json.loads(path.read_text())['rows']}
    parent_unchanged = all(written[row['id']] == row for row in base['rows'])
    require(parent_unchanged and len(base['rows']) == 916, 'Parent rows changed')
    record = dict(schema='e1s-native-link-input-requalification-v1', outcome='pass', index=bind(path), rows=len(merged), physically_requalified=verified,
                  added_from=dict(str024_build005=len(rows65), str040=len(rows61)), parent_index_rows_unchanged=parent_unchanged,
                  target_tools_executed=False)
    (args.out/'requalification.json').write_text(json.dumps(record, indent=2)+'\n')
    print(json.dumps(dict(outcome='pass', rows=len(merged), requalified=verified, index_sha256=record['index']['sha256'])))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
