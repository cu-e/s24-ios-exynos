#!/usr/bin/env python3
"""Mechanical admission of independently reviewed STR018 products; no decoder."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

WT = Path(__file__).resolve().parents[4]
MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
PRODUCER = MAIN / 'worktrees/str-018-e1s-development-providers-20261106'
REVIEW = MAIN / 'worktrees/e1s-export-providers-update-20261106/artifacts'
OUT = WT / 'artifacts/e1s-native-providers-admission-20261106/admission-002'
PINS = {}

def pin(path, expected=None):
    path = Path(path)
    assert path.is_file() and not path.is_symlink(), path
    with path.open('rb') as f:
        before = os.fstat(f.fileno())
        digest = hashlib.file_digest(f, 'sha256').hexdigest()
        after = os.fstat(f.fileno())
    key = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    assert key(before) == key(after) == key(path.stat()), path
    assert expected is None or digest == expected, (path, digest)
    PINS[str(path)] = digest
    return digest

def load(path, expected=None):
    pin(path, expected)
    assert Path(path).stat().st_size < 32 * 1024**2
    return json.loads(Path(path).read_text())

def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], env={
        **os.environ, 'GIT_NO_LAZY_FETCH': '1', 'GIT_OPTIONAL_LOCKS': '0'})

def main():
    OUT.mkdir(parents=True, exist_ok=False)
    base = git(MAIN, 'rev-parse', 'HEAD').decode().strip()
    source = load(REVIEW / 'str018-objects-review-002/evidence.json', '9d8d854d3640627c1331dbc5a3ad3e742e9a0b1e64199f05e526c0d546da2429')
    actual = load(REVIEW / 'str018-actual-providers-review-001/evidence.json', '08d8c0232d1605c54a6dc6d4b1a41f004c5f0dd509eebae118c6f74fc642292c')
    partial = load(REVIEW / 'str018-actual-qualification-review-001/evidence.json', '95bdeecc6a5796443675d1c9b750710d46f7652492d855c2a62146e1d3fa9051')
    assert source['outcome'] == actual['outcome'] == partial['outcome'] == 'pass'
    assert source['reviewed_commit'] == actual['source_freeze'] == 'ef5850d57745c5eee4215cc99fd6dab359c43276'
    assert actual['findings'] == partial['findings'] == []
    assert partial['source_commit'] == '1f238daebbeee16bd1d8a7c177da42b43988e584'
    assert partial['producer_commit'] == '2c50bcbec3ea1f9a589fa056a2138f02fcf943fe'
    products = load(PRODUCER / 'fixtures/public/e1s-development-providers/generated-products.json', '56c8010325631342d425bf743dd68d40d596f225154d96c67cf5572ff011775f')
    qualification = load(PRODUCER / 'fixtures/public/e1s-development-providers/generated-qualification.json', '2c3f4f5eab70807d953cb5bd94daafc0bde8f92e1ef7a52313e04c8b83ce089e')
    pin(MAIN / 'fixtures/public/e1s-development-providers/generated-headers.json', '07724b361a15671a7a31d5f14daf11b4d892dc732d0f181cfd780c7223c97fbe')
    assert actual['artifact_sha256'][str(PRODUCER / 'fixtures/public/e1s-development-providers/generated-products.json')] == '56c8010325631342d425bf743dd68d40d596f225154d96c67cf5572ff011775f'
    assert products['header_descriptor']['sha256'] == '07724b361a15671a7a31d5f14daf11b4d892dc732d0f181cfd780c7223c97fbe'
    assert products['actual_dependency_unique_count'] == actual['actual_dependencies'] == 624
    assert len(products['objects']) == len(actual['objects']) == 4 and len(products['archives']) == len(actual['archive_observations']) == 2
    for product, observed in zip(products['objects'], actual['objects']):
        for key in ('path', 'sha256', 'file_size', 'MD_sha256'):
            assert product[key] == observed[key], key
        pin(product['path'], product['sha256'])
        pin(product['MD'], product['MD_sha256'])
    for archive in products['archives']:
        reviewed_archive = next(x for x in actual['archive_observations'] if x['id'] == archive['id'])
        assert reviewed_archive['TOC'] == archive['strict_toc_name'] and reviewed_archive['members'] == [m['name'] for m in archive['members']]
        pin(archive['path'], archive['sha256'])
        assert archive['strict_toc_name'] == '__.SYMDEF SORTED'
    assert source['input_bindings'][products['caller']['path']]['sha256'] == products['caller']['sha256']
    assert actual['artifact_sha256'][products['caller']['path']] == products['caller']['sha256']
    for key in ('source_plan', 'caller', 'raw_evidence', 'root_evidence', 'evidence', 'manifest'):
        pin(products[key]['path'], products[key]['sha256'])
    for key in ('raw', 'root_receipt', 'assessment', 'evidence'):
        pin(qualification[key]['path'], qualification[key]['sha256'])
    assert partial['descriptor_sha256'] == pin(PRODUCER / 'fixtures/public/e1s-development-providers/generated-qualification.json')
    assert qualification['producer_descriptor']['sha256'] == pin(PRODUCER / 'fixtures/public/e1s-development-providers/generated-products.json')
    assert qualification['actual_provider_definition_count'] == partial['observed']['definitions'] == 47
    assert qualification['actual_pthread_function_table_bytes'] == partial['observed']['table_bytes'] == 1016
    assert qualification['actual_pthread_function_table_version'] == partial['observed']['table_version'] == 0
    assert qualification['actual_pthread_function_table_relocations'] == partial['observed']['callback_relocations'] == 25
    assert partial['observed']['unique_imports'] == 107 and partial['observed']['outside_provider_union'] == 73
    for flag in ('firehose_numeric_layout_qualified', 'native_callback_layout_qualified', 'full_tuple_qualified', 'alias_import_closure_qualified', 'task_criteria_complete', 'full_private_ABI_link_image_runtime_hardware_qualified'):
        assert qualification[flag] is False, flag
    commits = ['0187ebba3668ee13ef4d58b566c881884a8e8db6', 'ef5850d57745c5eee4215cc99fd6dab359c43276', 'a8b6d7688ac78fed3208ad6d25631bf0f4884011', '2c50bcbec3ea1f9a589fa056a2138f02fcf943fe', 'c4863af989baa4e3c2590e9a8ac20d2e7a855c4e', '876df0b9b1bc01be8d5bfeef127e33cc02d16de3', '1f238daebbeee16bd1d8a7c177da42b43988e584']
    previous = '29c11a6983f11a64a587a65f03cf182b03703ee4'
    mapping = []
    for commit in commits:
        assert git(PRODUCER, 'rev-parse', commit + '^').decode().strip() == previous
        paths = git(PRODUCER, 'diff-tree', '--no-commit-id', '--name-only', '-r', commit).decode().splitlines()
        assert paths and all(p.startswith(('fixtures/public/e1s-development-providers/', 'docs/procedures/e1s-development-providers/')) for p in paths)
        patch = git(PRODUCER, 'diff', '--binary', '--full-index', '--no-ext-diff', '--no-textconv', previous, commit)
        mapping.append({'source': commit, 'parent': previous, 'paths': paths, 'binary_fullindex_patch_sha256': hashlib.sha256(patch).hexdigest()})
        previous = commit
    assert git(PRODUCER, 'rev-parse', 'HEAD').decode().strip() == previous
    assert not git(PRODUCER, 'status', '--porcelain').strip()
    pin(__file__)
    result = {'kind': 'source-review', 'origin': 'local-host', 'outcome': 'pass', 'task': 'INT-003', 'owner': 'codex-integrator-platform-20261106-cn', 'main_observed_base': base,
        'admission': 'Exact reviewed native provider producer products and partial semantic facts only', 'source_commit_map': mapping,
        'actual_objects': products['objects'], 'actual_archives': products['archives'], 'actual_unique_MD_paths': 624,
        'partial_semantic_facts': partial['observed'], 'limits': partial['limits'],
        'prior_HOLD0187_not_standalone_accepted': True, 'strict_TOC_correction_ef5850_is_required': True,
        'decoder_MD_or_semantic_review_repeated': False, 'target_tool_or_MAIN_common_queue_or_ledger_mutation': False, 'STR018_task_completion': False,
        'artifact_sha256': PINS}
    p = OUT / 'evidence.json'
    p.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'outcome': 'pass', 'source_commits': 7, 'objects': 4, 'archives': 2, 'admission_sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'main_observed_base': base}))

if __name__ == '__main__':
    main()
