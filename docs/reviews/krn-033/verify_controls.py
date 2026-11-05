#!/usr/bin/env python3
"""Read-only independent framing/byte/console audit; never starts a guest."""
import hashlib
import json
from pathlib import Path
import struct
import sys
sys.dont_write_bytecode = True

BASE = Path('/home/egor/dev/pet/s24-ios-exynos/worktrees/krn-033-20261105/artifacts/crypto-gcm')


def unpack(path):
    data = path.read_bytes()
    magic, size = struct.unpack_from('<II', data)
    assert magic == 0x50554e58 and size == len(data) - 8
    offset = 8
    result = {}
    while True:
        name, length, reserved = struct.unpack_from('<16sII', data, offset)
        offset += 24
        assert reserved == 0
        if name == bytes(16):
            assert length == 0 and offset == len(data)
            return result
        name = name.rstrip(b'\0').decode()
        assert name not in result and offset + length <= len(data)
        result[name] = data[offset:offset+length]
        offset += length
        padding = -length % 16
        assert data[offset:offset+padding] == bytes(padding)
        offset += padding


def main():
    helper = BASE.parents[1].parents[1] / 'tools/build'
    # The implementation worktree is below MAIN/worktrees; use the existing
    # primary read-only Mach-O parser, then verify actual object bytes.
    helper = Path('/home/egor/dev/pet/s24-ios-exynos/tools/build')
    sys.path.insert(0, str(helper))
    from xnu_kernel_syscalls import ObjectData
    layout = ObjectData(BASE / 'host-session4/arm-adapter.o').value('_s24_gcm_layout', '<6Q')
    assert tuple(layout) == (1312, 16, 624, 296, 288, 80)
    positive = unpack(BASE / 'cpu-session1/positive.xnup')
    wrong = unpack(BASE / 'cpu-controls-session2/wrong-cookie.xnup')
    corrupt = unpack(BASE / 'cpu-controls-session2/corrupt-vector.xnup')
    spin = unpack(BASE / 'cpu-controls-session2/spin-timeout.xnup')
    normal = (BASE / 'arm-session1/normal.macho').read_bytes()
    assert positive['kernel'] == wrong['kernel'] == normal
    assert positive['cmdline'] == corrupt['cmdline'] == spin['cmdline'] == b'cpus=1 gcm_cookie=owned-adapter-v1\0'
    assert wrong['cmdline'] == b'cpus=1 gcm_cookie=wrong\0'
    assert spin['kernel'] == (BASE / 'arm-session1/spin.macho').read_bytes()
    changed = [i for i, (a, b) in enumerate(zip(normal, corrupt['kernel'])) if a != b]
    assert len(normal) == len(corrupt['kernel']) and changed == [297016]
    assert normal[changed[0]] ^ corrupt['kernel'][changed[0]] == 1
    blob = (BASE / 'arm-session1/vectors.bin').read_bytes()
    controls = json.loads((BASE / 'cpu-controls-session2/evidence.json').read_text())
    wanted = bytes.fromhex(controls['corrupt_vector_control']['original_expected'])
    assert normal.count(blob) == 1 and blob.count(wanted) == 1
    assert normal.index(blob) + blob.index(wanted) == changed[0]
    console = (BASE / 'cpu-session1/positive.log').read_text()
    assert 'GCM ARM PASS checks=0x18bf0d2 failure_line=0x0' in console
    assert int('18bf0d2', 16) == 25948370
    assert 'GCM SYNTHETIC HANDOFF VERIFIED' in console and 'GCM SYNTHETIC PSCI_SYSTEM_OFF' in console
    for name, marker in [('wrong-cookie', 'GCM SYNTHETIC REJECT command-cookie'),
                         ('corrupt-vector', 'GCM ARM FAIL'), ('spin-timeout', 'GCM SYNTHETIC SPIN-CONTROL')]:
        text = (BASE / 'cpu-controls-session2' / (name + '.log')).read_text()
        assert marker in text and 'GCM ARM PASS' not in text
    assert len(controls['commands']) == 3
    for command in controls['commands']:
        assert command['after']['owned_processes'] == [] and command['after']['owned_tree_rss_bytes'] == 0
    timeout = controls['commands'][2]
    assert timeout['outcome'] == 'timeout' and timeout['timeout_seconds'] == 3 and timeout['elapsed_seconds'] >= 3
    for admission in controls['admission_waits']:
        assert admission['admitted']
        samples = admission['samples'][-3:]
        assert len(samples) == 3 and all(s['mem_available_kib'] >= 4194304 for s in samples)
        assert all(b['elapsed_seconds'] - a['elapsed_seconds'] >= 1 for a, b in zip(samples, samples[1:]))
    before = (BASE / 'cpu-session1/executed-cpu.py').read_bytes()
    expected = before.decode().replace(" finally:\n  report['owned_source_hashes']", " finally:\n  report.setdefault('summary','Actual GCM CPU qualification failed or memory-deferred; retain commands and conditional markers, no complete qualification claim')\n  report['owned_source_hashes']").encode()
    actual = BASE.parents[1] / 'src/platform/crypto/gcm/cpu.py'
    assert actual.read_bytes() == expected
    patch = controls['qualification_metadata_patch']
    assert hashlib.sha256(before).hexdigest() == patch['before_sha256']
    assert hashlib.sha256(expected).hexdigest() == patch['after_sha256']
    original = json.loads((BASE / 'cpu-session1/original-evidence.json').read_text())
    labelled = json.loads((BASE / 'cpu-session1/evidence.json').read_text())
    assert original['outcome'] == labelled['outcome'] == 'fail'
    assert original['commands'] == labelled['commands'] and original['guest_cases'] == labelled['guest_cases']
    print(json.dumps(dict(outcome='pass', guest_executed=False, canonical_image_bytes=True,
                         actual_ARM_object_layout=list(layout),
                         wrong_cookie_only_command_change=True, corrupt_kernel_changed_bytes=changed,
                         positive_checks=25948370, three_console_controls=True, finite_timeout_and_cleanup=True,
                         exact_driver_label_patch=True, original_failed_outcome_preserved=True), indent=2))


if __name__ == '__main__':
    main()
