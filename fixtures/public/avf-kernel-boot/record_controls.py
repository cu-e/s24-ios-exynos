#!/usr/bin/env python3
"""Record one registered light control run with the repository evidence schema."""
import argparse
import importlib.util
import json
from pathlib import Path
import resource
import sys

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('collector', ROOT / 'tools/run/avf_kernel_boot.py')
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--main', type=Path, required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--run', required=True)
    args = parser.parse_args()
    resource.setrlimit(resource.RLIMIT_AS, (256 << 20, 256 << 20))
    base = ROOT / 'artifacts/avf-kernel-boot'
    record_root = c.output_dir(base / ('measurement-' + args.run)); record_root.mkdir(parents=True)
    controls_out = c.output_dir(base / ('controls-' + args.run))
    supervisor = c.helper(args.main.resolve(), c.read_json(c.FIXTURE), 'process')
    argv = [sys.executable, '-s', str(ROOT / 'fixtures/public/avf-kernel-boot/controls.py'),
            '--main', str(args.main.resolve()), '--out', str(controls_out)]
    record = c.own_process(argv, record_root, supervisor, c.Stop(), seconds=60,
                           memory_floor=False, rss_limit=256 << 20)
    c.write_json(record_root / 'supervisor.json', record)
    artifacts = [p for folder in (record_root, controls_out) if folder.exists()
                 for p in sorted(folder.rglob('*')) if p.is_file() and not p.is_symlink()]
    relative = lambda p: str(p.relative_to(args.main.resolve()))
    commands = [{'argv': argv, 'cwd': str(record_root), 'exit_code': record['exit_code'],
                 'elapsed_seconds': record['elapsed_seconds'], 'supervisor': relative(record_root / 'supervisor.json')}]
    control_report = controls_out / 'controls.json'
    if control_report.is_file():
        control = c.read_json(control_report)
        commands.extend(row for row in control['records'] if 'argv' in row)
    for path in artifacts:
        if path.name == 'record.json':
            child = c.read_json(path)
            commands.append({'argv': child['argv'], 'cwd': child['cwd'], 'exit_code': child['exit_code'],
                             'elapsed_seconds': child['elapsed_seconds'], 'record': relative(path)})
    sources = [ROOT / 'tools/run/avf_kernel_boot.py', ROOT / 'fixtures/public/avf-kernel-boot/controls.py',
               Path(__file__), c.FIXTURE]
    passed = record['exit_code'] == 0 and record['live_owned_pids'] == [] and record['stop_reason'] is None
    evidence = {'kind': 'host-test', 'origin': 'local-host', 'outcome': 'pass' if passed else 'fail',
        'recorded_at': c.now(), 'summary': 'Registered finite collector host controls; no compiler, QEMU or guest execution.',
        'commit': args.commit, 'task': 'VM-040', 'owner': c.OWNER, 'experiment': 'VMBOOTCOLLECT-001',
        'commands': commands, 'artifacts': [relative(p) for p in artifacts],
        'artifact_sha256': {relative(p): c.digest(p) for p in artifacts},
        'source_sha256': {relative(p): c.digest(p) for p in sources},
        'current_image_memory': c.memory_self(), 'control_report': relative(control_report),
        'limitations': ['No genuine kernel image is admitted; complete image/source-to-link/production branch remains unmeasured.',
            'Python processes, parser bytes and QMP peers are authored host controls, never XNU evidence.',
            'No compiler, QEMU, phone, production packaging or common repository checks ran.',
            'Per-session RSS samples do not measure all nested independent sessions together; individual process controls retain their own session samples.',
            'Independent source review/integrator acceptance and a new image-bound protocol/root lease are future gates.']}
    c.write_json(record_root / 'evidence.json', evidence)
    print(json.dumps({'outcome': evidence['outcome'], 'evidence': str(record_root / 'evidence.json'),
                      'control_report': str(control_report), 'exit_code': record['exit_code']}))
    return 0 if passed else 1


if __name__ == '__main__': sys.exit(main())
