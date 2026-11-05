#!/usr/bin/env python3
"""USBREV-002 exact-commit source-profile fix witness; no devices or builds."""
import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
HERE = Path(__file__).resolve().parent
IMPL = MAIN / 'worktrees/usb-001-20261105'
BEFORE = 'e1785878045751213cb1e8e49e42a364333ed496'
COMMIT = 'f3d705d737f1c863be019bd4b5d0cd78cb26ff26'
WITNESS = IMPL / 'artifacts/usb-readonly/host-session6'
OUT = HERE / 'local/followup-002'
OUT.mkdir(parents=True, exist_ok=False)
report = dict(kind='source-review', origin='local-host', outcome='fail',
              recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
              commit=COMMIT, commands=[], checks=[])


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def run(args, label, cwd=IMPL):
    p = subprocess.run(args, cwd=cwd, capture_output=True, timeout=30)
    out, err = OUT / (label + '.stdout.txt'), OUT / (label + '.stderr.txt')
    out.write_bytes(p.stdout)
    err.write_bytes(p.stderr)
    report['commands'].append(dict(argv=args, cwd=str(cwd), exit_code=p.returncode,
                                   stdout=str(out.relative_to(MAIN)), stderr=str(err.relative_to(MAIN))))
    assert p.returncode == 0, p.stderr
    return p.stdout


def rejects(module, source, profile):
    try:
        return not module.repeater_profile_matches(source, profile)
    except ValueError:
        return True


try:
    assert run(['git', 'rev-parse', 'HEAD'], 'head').decode().strip() == COMMIT
    assert not run(['git', 'status', '--porcelain'], 'status')
    for name in ['readonly.c', 'readonly.h', 'fixture.c', 'sanitizer-control.c', 'layout.cpp']:
        assert not run(['git', 'diff', BEFORE, COMMIT, '--', 'src/platform/usb/' + name], 'unchanged-' + name)
    for name in ['check.py', 'profile.json']:
        data = run(['git', 'show', COMMIT + ':src/platform/usb/' + name], 'exact-' + name)
        (OUT / name).write_bytes(data)
        assert data == (WITNESS / 'source' / name).read_bytes()
    evidence = json.loads((WITNESS / 'evidence.json').read_text())
    for name, expected in evidence['sha256'].items():
        assert sha(MAIN / name) == expected, name
    report['witness_hashes_verified'] = len(evidence['sha256'])
    summary = json.loads((IMPL / 'docs/procedures/usb-001/repeater-review-evidence.json').read_text())
    for name, expected in summary['evidence'].items():
        assert sha(MAIN / name) == expected
    assert evidence['outcome'] == 'pass' and len(evidence['checks']) == 28
    assert all(check['pass_check'] for check in evidence['checks'])
    report['owner_runner_checks_hash_audited'] = 28
    spec = importlib.util.spec_from_file_location('usb_fix_review', OUT / 'check.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    profile = json.loads((OUT / 'profile.json').read_text())['USB2_repeaters']
    assert profile['actual_fitted_component_qualified'] is False
    assert profile['BYH3_selection_qualified'] is False
    expected = [dict(node='ptn3222-repeater@4F', compatible='ptn3222-repeater', I2C_7bit_address='0x4f', status='okay'),
                dict(node='tusb2e11-repeater@3E', compatible='tusb2e11-repeater', I2C_7bit_address='0x3e', status='okay')]
    assert sorted(profile['enabled_source_nodes'], key=lambda n: n['compatible']) == expected
    pins = json.loads((WITNESS / 'source-review.json').read_text())
    donor = 'arch/arm64/boot/dts/samsung/e1s/e1s_eur_openx_w01_r17.dts'
    for label in ['reference', 'comparison']:
        pin = pins[label]
        repo = MAIN / pin['repository']
        source = run(['git', 'show', pin['revision'] + ':' + donor], label + '-donor', repo).decode()
        assert hashlib.sha256(source.encode()).hexdigest() == pin['files'][donor]['sha256']
        assert module.enabled_repeater_nodes(source) == expected
        assert module.repeater_profile_matches(source, profile)
        report['checks'].append(label + ': exact independently specified two-node set accepted')
        for candidate in expected:
            changed = copy.deepcopy(profile)
            changed['enabled_source_nodes'] = [n for n in changed['enabled_source_nodes'] if n['node'] != candidate['node']]
            assert rejects(module, source, changed)
            report['checks'].append(label + ': omitted ' + candidate['node'] + ' rejected')
            for key, value in [('compatible', 'wrong-repeater'), ('I2C_7bit_address', '0x01'), ('status', 'disabled'), ('node', 'wrong-repeater@01')]:
                changed = copy.deepcopy(profile)
                next(n for n in changed['enabled_source_nodes'] if n['node'] == candidate['node'])[key] = value
                assert rejects(module, source, changed)
                report['checks'].append(label + ': profile ' + candidate['node'] + '/' + key + ' mismatch rejected')
            start = source.index(candidate['node'] + ' {')
            end = source.index('repeater_tune_param', start)
            header = source[start:end]
            for key, old, new in [('compatible', '"' + candidate['compatible'] + '"', '"wrong-repeater"'),
                                  ('status', '"okay"', '"disabled"'),
                                  ('address', '<' + candidate['I2C_7bit_address'][0:2] + candidate['I2C_7bit_address'][2:].upper() + '>', '<0x01>')]:
                assert old in header
                changed_source = source[:start] + header.replace(old, new, 1) + source[end:]
                assert rejects(module, changed_source, profile)
                report['checks'].append(label + ': source ' + candidate['node'] + '/' + key + ' mismatch rejected')
        unknown = source.replace('&hsi2c_34 {', '&hsi2c_34 {\n#if 1\n#endif', 1)
        assert rejects(module, unknown, profile)
        report['checks'].append(label + ': unexpected selected-controller conditional rejected')
    report['outcome'] = 'pass'
    report['summary'] = 'USBREV-F01 resolved in f3d705d; both exact-source alternatives represented, hardware selection remains unqualified; 34 independently executed omission/mismatch/conditional negatives reject, plus two positive source sets.'
    report['finding_status'] = {'USBREV-F01': 'resolved', 'new_P0_P1_P2': 0}
except Exception as error:
    report['error'] = repr(error)
finally:
    paths = sorted(p for p in OUT.rglob('*') if p.is_file()) + [Path(__file__).resolve(), HERE / 'followup-procedure.md']
    report['artifacts'] = [str(p.relative_to(MAIN)) for p in paths]
    report['sha256'] = {str(p.relative_to(MAIN)): sha(p) for p in paths}
    report['limitations'] = ['Pinned-source extractor only, not arbitrary DTS preprocessing or a live DTB.', 'C unchanged: prior independent ASan/UBSan and DMA oracle apply; not rerun.', 'No native USB/Apple ABI/device qualification.']
    (HERE / 'followup-evidence.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k: report.get(k) for k in ['outcome', 'error', 'summary', 'witness_hashes_verified', 'finding_status']}, indent=2))
print('Actual source checks:', len(report['checks']))
raise SystemExit(0 if report['outcome'] == 'pass' else 1)
