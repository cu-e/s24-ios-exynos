#!/usr/bin/env python3
"""Reproducible small host checks; writes a new local artifact capsule only."""
import argparse
import datetime
import hashlib
import json
import pathlib
import subprocess
import sys

PIN = '417484173abc2c4fa93e738ea82ad9f2e84911b1'
FILES = [
    'COPYING', 'arch/arm64/configs/e1s_defconfig',
    'arch/arm64/boot/dts/samsung/e1s/s5e9945-e1s_common.dtsi',
    'arch/arm64/boot/dts/samsung/sensorhub_s5e9945.dtsi',
    'arch/arm64/boot/dts/exynos/board/erd/s5e9945-erd9945-gnss.dtsi',
    'drivers/sensorhub/comm/shub_comm.h', 'drivers/sensorhub/comm/shub_cmd.h',
    'drivers/sensorhub/comm/shub_comm.c',
    'drivers/sensorhub/sensormanager/shub_sensor_manager.c',
    'drivers/sensorhub/sensormanager/shub_sensor_type.h',
    'drivers/sensorhub/sensor/accelerometer.c', 'drivers/sensorhub/sensor/gyroscope.c',
    'drivers/sensorhub/utility/shub_utility.c', 'drivers/sensorhub/vendor/shub_lsi.c',
    'drivers/staging/nanohub/chub_shub.c',
    'drivers/soc/samsung/gnssif/include/exynos_ipc.h',
    'drivers/soc/samsung/gnssif/gnss_io_device.c',
    'drivers/soc/samsung/gnssif/gnss_link_device_memory.c',
]

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', type=pathlib.Path, required=True)
    ap.add_argument('--run', required=True)
    ap.add_argument('--ledger-root', type=pathlib.Path)
    ap.add_argument('--inventory', type=pathlib.Path, required=True)
    ap.add_argument('--cc', type=pathlib.Path, default=pathlib.Path('/home/egor/.local/bin/clang'))
    args = ap.parse_args()
    root = pathlib.Path(__file__).resolve().parents[3]
    if not args.run or pathlib.Path(args.run).name != args.run:
        ap.error('--run must be one path component')
    run = root / 'artifacts/sen-001' / args.run
    run.mkdir(parents=True, exist_ok=False)
    ledger = args.ledger_root.resolve() if args.ledger_root else root
    def relative(p):
        return str(p.relative_to(ledger))
    commands = []
    def command(argv, name):
        proc = subprocess.run(list(map(str, argv)), cwd=root, capture_output=True, timeout=90)
        log = run / (name + '.log')
        log.write_bytes(proc.stdout + proc.stderr)
        commands.append({'argv': list(map(str, argv)), 'exit_code': proc.returncode,
                         'output': relative(log), 'sha256': digest(log)})
        if proc.returncode:
            raise RuntimeError(f'{name} exited {proc.returncode}: {log}')
        return proc.stdout
    result = {'kind': 'host-test', 'origin': 'local-host', 'outcome': 'fail',
              'recorded_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'summary': 'Bounded synthetic SHUB/GNSS parser qualification',
              'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
              'commands': commands, 'source': {'revision': PIN, 'files': {}},
              'limitations': ['Synthetic host input only; no firmware, MMIO, phone or Apple service execution.',
                              'Only complete single SHUB bypass accel/gyro records and GNSS single frames supported.',
                              'Receipt time must be boot-time nanoseconds in the same epoch as the hub.']}
    try:
        command(['git', '-C', args.source, 'cat-file', '-e', PIN + '^{commit}'], 'pin')
        for i, path in enumerate(FILES):
            data = command(['git', '-C', args.source, 'show', PIN + ':' + path], f'source-{i:02}')
            target = run / 'sources' / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            result['source']['files'][path] = {'sha256': digest(target),
                                              'artifact': relative(target)}
        inventory = args.inventory.read_text()
        expected = json.loads((root / 'src/platform/sensors/identities.json').read_text())
        for sensor in expected['sensors']:
            line = next((line for line in inventory.splitlines()
                         if line.startswith(sensor['handle'] + ') ')), '')
            if sensor['name'] not in line or '(' + str(sensor['hal_type']) + ')' not in line:
                raise RuntimeError('Capture identity mismatch: ' + sensor['name'])
        result['inventory'] = {'path': str(args.inventory.resolve()), 'sha256': digest(args.inventory),
                               'observations': expected, 'origin': 'existing-local-device-capture'}
        (run / 'identity-check.log').write_text('Verified all seven advertised physical-sensor entries against existing capture.\n')
        command([args.cc, '--version'], 'compiler-version')
        result['compiler'] = {'path': str(args.cc.resolve()), 'sha256': digest(args.cc.resolve())}
        own = root / 'src/platform/sensors'
        result['owned_inputs'] = {str(p.relative_to(root)): digest(p) for p in own.rglob('*')
                                  if p.is_file() and '__pycache__' not in p.parts}
        flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-I', own]
        command([args.cc, *flags, '-g', '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                 own / 'transport.c', own / 'tests/transport_test.c', '-o', run / 'transport-test'], 'compile-host')
        command([run / 'transport-test'], 'run-host')
        command([args.cc, *flags, '--target=aarch64-none-elf', '-ffreestanding', '-c',
                 own / 'transport.c', '-o', run / 'transport-arm64.o'], 'compile-arm64')
        # Isolated *genuine* declarations with explicitly synthetic kernel type support.
        shim = run / 'header-support/linux'
        shim.mkdir(parents=True)
        (shim / 'kernel.h').write_text('#pragma once\n#include <stdint.h>\n#include <stddef.h>\n#include <stdbool.h>\n'
                                      'typedef uint8_t u8; typedef uint16_t u16; typedef uint64_t u64;\n'
                                      'struct list_head { struct list_head *next, *prev; };\n')
        oracle = run / 'header-oracle.c'
        oracle.write_text('#include "shub_comm.h"\n'
            '_Static_assert(SHUB_MSG_HEADER_SIZE == 15, "genuine SHUB prefix");\n'
            '_Static_assert(offsetof(struct shub_msg, total_length) == 3, "total");\n'
            '_Static_assert(offsetof(struct shub_msg, length) == 5, "length");\n'
            '_Static_assert(offsetof(struct shub_msg, timestamp) == 7, "timestamp");\n'
            '_Static_assert(CMD_REPORT == 5, "command");\nint main(void) { return 0; }\n')
        command([args.cc, '-std=c11', '-Wall', '-Werror', '-I', shim.parent,
                 '-I', run / 'sources/drivers/sensorhub/comm', oracle, '-o', run / 'header-oracle'], 'compile-genuine-header')
        command([run / 'header-oracle'], 'run-genuine-header')
        (shim / 'types.h').write_text('#include "kernel.h"\n#define __packed __attribute__((packed))\n')
        (shim.parent / 'gnss.h').write_text('/* Deliberately empty dependency shim: no GNSS driver ABI claimed. */\n')
        gnss_oracle = run / 'gnss-oracle.c'
        gnss_oracle.write_text('#include <assert.h>\n#include "exynos_ipc.h"\n#include "transport.h"\n'
            '_Static_assert(EXYNOS_HEADER_SIZE == 12, "header");\n'
            '_Static_assert(offsetof(struct exynos_link_header, seq) == 0, "known declaration discrepancy");\n'
            '_Static_assert(offsetof(struct exynos_link_header, len) == 4, "known declaration discrepancy");\n'
            '_Static_assert(EXYNOS_FRAME_SEQ_OFFSET == 2 && EXYNOS_LEN_OFFSET == 6, "actual helpers differ");\n'
            'int main(void) {\n'
            ' _Alignas(8) u8 p[65536] = {0xcd,0xab,0,0,0,0xc0};\n'
            ' struct sen_service svc = {true,true}; struct sen_gnss_frame frame;\n'
            ' for (unsigned n = 12; n <= 65535; ++n) {\n'
            '  p[6] = n; p[7] = n >> 8;\n'
            '  assert(exynos_start_valid(p) && exynos_single_frame(p));\n'
            '  assert(sen_gnss_frame(&svc,p,sizeof(p),&frame) == SEN_OK);\n'
            '  assert(frame.consumed == exynos_get_total_len(p));\n'
            '  assert(frame.payload_size + EXYNOS_HEADER_SIZE == exynos_get_frame_len(p));\n'
            ' } return 0; }\n')
        command([args.cc, '-std=c11', '-Wall', '-Werror', '-fsanitize=address,undefined',
                 '-I', shim.parent, '-I', own, '-I', run / 'sources/drivers/soc/samsung/gnssif/include',
                 gnss_oracle, own / 'transport.c', '-o', run / 'gnss-oracle'], 'compile-genuine-gnss')
        command([run / 'gnss-oracle'], 'run-genuine-gnss')
        result['outcome'] = 'pass'
    except Exception as exc:
        result['error'] = str(exc)
    result['artifacts'] = [relative(p) for p in run.rglob('*') if p.is_file()]
    result['output_hashes'] = {relative(p): digest(p) for p in run.rglob('*') if p.is_file()}
    (run / 'evidence.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'outcome': result['outcome'], 'evidence': str((run / 'evidence.json').relative_to(root)),
                      'error': result.get('error')}))
    return result['outcome'] != 'pass'

if __name__ == '__main__':
    sys.exit(main())
