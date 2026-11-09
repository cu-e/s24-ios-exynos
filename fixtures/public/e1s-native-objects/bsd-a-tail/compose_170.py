#!/usr/bin/env python3
"""Requalify 126 physical BSD-a products and join them to the accepted 44 origins.

Runs no compiler or linker. Checks hashes, Mach-O validity and depfile closure on
the files that exist now; recorded verdicts alone are not accepted.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
COMMON = (MAIN/'tools/build/avf_kernel_objects.py', '9929a7d6f1e748770f54abf3e101350648092027a18c419a242d0348f620f755')
BUILD5 = MAIN/'worktrees/str-024-e1s-native-objects-bsd-a-20261106/docs/procedures/e1s-native-objects/bsd-a'
PARTIAL = BUILD5/'build-005/partial-109-origins.json'
PRODUCTS5 = BUILD5/'build-005/actual-products.json'
PLAN5 = BUILD5/'plan-005/plan.json'
TAIL = MAIN/'worktrees/str-040-e1s-native-bsd-a-tail-20261110'
EVIDENCE = TAIL/'artifacts/e1s-native-compile/bsd-a-tail-001/evidence.json'
PLAN = TAIL/'docs/procedures/e1s-native-objects/bsd-a-tail/plan-001/plan.json'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_common():
    raw = COMMON[0].read_bytes()
    require(hashlib.sha256(raw).hexdigest() == COMMON[1], 'Changed common helper')
    spec = importlib.util.spec_from_file_location('compose_common', COMMON[0])
    module = importlib.util.module_from_spec(spec)
    exec(compile(raw, str(COMMON[0]), 'exec'), module.__dict__)
    return module


def requalify(common, identifier, item, cwd, expected_deps):
    """Physical check of one product; independent of the producing run."""
    require(sha(item['object']) == item['object_sha256'], 'Object changed: '+identifier)
    require(sha(item['depfile']) == item['depfile_sha256'], 'Depfile changed: '+identifier)
    require(all(item[key] == 'pass' for key in ['object_validity', 'input_qualification', 'resource_qualification']), 'Unqualified row: '+identifier)
    validation = common.macho(item['object'], False)
    require(validation['arm64_macho_object'] is True and validation['sha256'] == item['object_sha256'], 'Not an ARM64 Mach-O object: '+identifier)
    observed = common.dependencies(item['depfile'], cwd, item['object'])
    require(set(observed) == set(expected_deps), 'Depfile closure differs: '+identifier)
    for path, digest in expected_deps.items():
        require(sha(path) == digest, 'Dependency changed: '+path)
    return validation


def by_role(report):
    return {command['role']: command['process'] for command in report['commands']}


def product(row, process, plan_row):
    return dict(id=row['id'], object=row['object'], object_sha256=row['object_sha256'], depfile=row['depfile'],
                depfile_sha256=row['depfile_sha256'], source={'path': plan_row['source'], 'sha256': plan_row['source_sha256']},
                recipe=plan_row['recipe'], actual_argv=process['argv'], actual_cwd=process['cwd'],
                actual_MD_dependencies=row['dependencies'], actual_resource_qualification=row['resource_qualification'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--descriptor', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    common = load_common()

    partial = json.loads(PARTIAL.read_text())
    require(partial['qualified_count'] == 109 and partial['missing_count'] == 61, 'Unexpected partial inventory')
    origins = partial['origins']
    require([o['original_index'] for o in origins] == list(range(109)), 'Origin order changed')

    products5 = json.loads(PRODUCTS5.read_text())
    report5 = json.loads(Path(products5['raw_parent_evidence']).read_text())
    require(sha(products5['raw_parent_evidence']) == products5['raw_parent_sha256'] and report5['outcome'] == 'fail', 'Unexpected BUILD-005 parent')
    plan5 = {row['id']: row for row in json.loads(PLAN5.read_text())['commands']}
    roles5 = by_role(report5)
    list65 = []
    for row in products5['qualified_objects']:
        process = roles5[row['id']]
        require(process['exit_code'] == 0 and process['outcome'] == 'pass' and process['resource_qualification'] == 'pass', 'BUILD-005 command not clean: '+row['id'])
        requalify(common, row['id'], row, process['cwd'], row['dependencies'])
        list65.append(product(row, process, plan5[row['id']]))
    require(len(list65) == 65 and [p['id'] for p in list65] == [o['id'] for o in origins[44:109]], 'BUILD-005 rows differ from origins')
    for item, origin in zip(list65, origins[44:109]):
        require(item['object_sha256'] == origin['object_sha256'] and item['depfile_sha256'] == origin['depfile_sha256'], 'Origin hash differs: '+item['id'])

    report = json.loads(EVIDENCE.read_text())
    require(report['outcome'] == 'pass' and not report['owned_survivors'] and len(report['objects']) == 61, 'STR-040 run not clean')
    plan = {row['id']: row for row in json.loads(PLAN.read_text())['commands']}
    roles = by_role(report)
    new = []
    for row in report['objects']:
        process = roles[row['id']]
        require(process['exit_code'] == 0 and process['outcome'] == 'pass' and process['resource_qualification'] == 'pass', 'STR-040 command not clean: '+row['id'])
        requalify(common, row['id'], row, process['cwd'], row['dependencies'])
        new.append(dict(original_index=109+len(new), id=row['id'], experiment='STR040BUILD-001',
                        raw_parent_report={'path': str(EVIDENCE), 'sha256': sha(EVIDENCE), 'outcome': 'pass'},
                        executor_sha256=report['executor_sha256'], source_plan_sha256=report['source_plan_sha256'],
                        object=row['object'], object_sha256=row['object_sha256'], depfile=row['depfile'], depfile_sha256=row['depfile_sha256'],
                        object_validity='pass', input_qualification='pass', resource_qualification='pass', object_validation=row['object_validation']))
    require([n['id'] for n in new] == partial['remaining_ordered_object_ids'], 'STR-040 rows differ from remaining IDs')

    products_path = args.out/'products-65.json'
    products_path.write_text(json.dumps(list65, indent=1)+'\n')
    descriptor = dict(schema='e1s-native-bsd-a-complete-origins-v1', kind='host-test', origin='local-host', outcome='pass', task='STR-040',
                      owner='claude-e1s-native-objects-20261110-sr40', original_shard='bsd-a', required_object_count=170, qualified_count=170,
                      composed_from=dict(partial_109={'path': str(PARTIAL), 'sha256': sha(PARTIAL)}, str040_evidence={'path': str(EVIDENCE), 'sha256': sha(EVIDENCE)}),
                      origins=origins+new, failed_parent_statuses_preserved=True, origin_paths_or_hashes_relabelled=False,
                      prior_44_independently_accepted_by_codex_reviewers=True,
                      requalified_physically_here=dict(str024_build005=len(list65), str040=len(new)),
                      str024_task_status='left in_progress with its Codex owner; not released or completed here',
                      full_kernel_or_ABI_or_runtime_or_hardware_qualified=False)
    args.descriptor.write_text(json.dumps(descriptor, indent=2)+'\n')
    print(json.dumps(dict(outcome='pass', origins=len(descriptor['origins']), requalified=len(list65)+len(new), products65=str(products_path), products65_sha256=sha(products_path), descriptor_sha256=sha(args.descriptor))))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
