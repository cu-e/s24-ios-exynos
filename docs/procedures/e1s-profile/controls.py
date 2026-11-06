#!/usr/bin/env python3
"""Finite source-only controls against copied actual accepted E1S bodies."""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--main', type=Path, required=True)
    p.add_argument('--prepared', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    project = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location('selected_e1s_profile', project/'tools/build/e1s_profile.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    pins_path = project/'fixtures/public/e1s-profile/pins.json'
    pins = json.loads(pins_path.read_text())
    report = json.loads((a.prepared.parent/'report.json').read_text())
    if a.out.exists() or a.out.is_symlink():
        raise ValueError('Fresh output required')
    a.out.mkdir()
    baseline = module.source_profile(project, a.main/'references/s24-port', a.prepared,
                                     report['provenance'], report['patches'])
    records = [{'case': 'actual accepted source coherence', 'outcome': 'pass'}]
    cases = ['wrong_revision', 'wrong_header', 'wrong_board', 'wrong_topology',
             'adt_cluster_disagreement', 'loader_gic_disagreement', 'bringup_cpus_changed',
             'stm_patch_changed', 'memory_patch_changed', 'patch_order_changed',
             'stale_prepared_source', 'compatible_witness_changed']
    for case in cases:
        (a.out/'partial.json').write_text(json.dumps(records, indent=2)+'\n')
        with tempfile.TemporaryDirectory(prefix='control-', dir=a.out) as tmp:
            base = Path(tmp); pr = base/'project'; donor = base/'donor'; tree = base/'xnu'
            selected = copy.deepcopy(pins)
            for source, target, names in [
                    (project, pr, list(pins['project_sha256']) + [pins['compatible_loader_evidence']['evidence_path']]),
                    (a.main/'references/s24-port', donor, pins['donor_sha256']),
                    (a.prepared, tree, pins['prepared_sha256'])]:
                for name in names:
                    path = target/name; path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source/name, path)
            provenance = copy.deepcopy(report['provenance']); patches = copy.deepcopy(report['patches'])
            def change(root, relative, old, new, pin_group=None):
                path = root/relative; text = path.read_text(); assert old in text
                if case == 'wrong_topology':
                    start = text.index('#ifdef ARM64_BOARD_CONFIG_E1S\n')
                    text = text[:start] + text[start:].replace(old, new, 1)
                else:
                    text = text.replace(old, new, 1)
                path.write_text(text)
                if pin_group:
                    selected[pin_group][relative] = digest(path)
            if case == 'wrong_revision':
                provenance[0]['revision'] = '0'*40
            elif case == 'wrong_header':
                change(tree, 'pexpert/pexpert/arm64/E1S.h', '#define E1S 1', '#define BCM2837 1', 'prepared_sha256')
            elif case == 'wrong_board':
                change(tree, 'pexpert/pexpert/arm64/board_config.h', '#include <pexpert/arm64/E1S.h>', '#include <pexpert/arm64/BCM2837.h>', 'prepared_sha256')
            elif case == 'wrong_topology':
                change(tree, 'pexpert/pexpert/arm64/board_config.h', '#define MAX_CPUS                       10', '#define MAX_CPUS                       8', 'prepared_sha256')
            elif case == 'adt_cluster_disagreement':
                change(donor, 'tools/e1s/xnu/mkadt.py', '(0x900, 3, 0, False)', '(0x900, 2, 2, False)', 'donor_sha256')
            elif case == 'loader_gic_disagreement':
                change(donor, 'shim/e1s-xnu/gic.c', '0x10200000UL', '0x10210000UL', 'donor_sha256')
            elif case == 'bringup_cpus_changed':
                change(donor, 'tools/e1s/xnu/mkpayload.py', 'serial=3 cpus=1 keepsyms=1', 'serial=3 cpus=8 keepsyms=1', 'donor_sha256')
            elif case == 'stm_patch_changed':
                path = pr/'patches/display-input/0001-e1s-stm-coordinate-nibbles.patch'; path.write_bytes(path.read_bytes()+b'\n')
            elif case == 'memory_patch_changed':
                path = pr/'patches/e1s-boot/0001-loader-memory-validation.patch'; path.write_bytes(path.read_bytes()+b'\n')
            elif case == 'patch_order_changed':
                patches[1], patches[2] = patches[2], patches[1]
            elif case == 'stale_prepared_source':
                path = tree/'bsd/dev/e1s_touch.c'; path.write_bytes(path.read_bytes()+b'\n')
            elif case == 'compatible_witness_changed':
                path = pr/pins['compatible_loader_evidence']['evidence_path']; path.write_bytes(path.read_bytes()+b'\n')
            pinfile = pr/'fixtures/public/e1s-profile/pins.json'; pinfile.parent.mkdir(parents=True, exist_ok=True)
            pinfile.write_text(json.dumps(selected))
            try:
                module.source_profile(pr, donor, tree, provenance, patches)
            except ValueError as e:
                records.append({'case': case, 'outcome': 'rejected', 'reason': str(e)})
            else:
                raise AssertionError('Invalid source profile accepted: '+case)
    result = {'kind':'host-test','origin':'local-host','outcome':'pass',
              'recorded_at':datetime.now(timezone.utc).isoformat(), 'source_only':True,
              'cases':records,'profile':baseline,'source_preparation_report_sha256':digest(a.prepared.parent/'report.json'),
              'profile_emitter_sha256':digest(project/'tools/build/e1s_profile.py'),
              'controls_sha256':digest(Path(__file__)), 'hardware_executed':False}
    (a.out/'controls.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'outcome':'pass','positive':1,'meaningful_rejections':12,'report':str(a.out/'controls.json')}))


if __name__ == '__main__':
    main()
