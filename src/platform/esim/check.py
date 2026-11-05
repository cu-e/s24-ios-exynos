#!/usr/bin/env python3
"""Build owned eUICC boundary tests;never select or access a phone."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import resource
import shutil
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
SOURCE = Path(__file__).resolve().parent
NDK = Path('/home/egor/Android/Sdk/ndk/28.2.13676358/toolchains/llvm/prebuilt/linux-x86_64/bin')


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def macho_constants(path):
    """Bound the tiny probe's thin ARM64 Mach-O and read its __const bytes."""
    data = path.read_bytes()
    if len(data) < 32:
        raise ValueError('Truncated probe')
    magic, cpu, _, kind, count, extent, _, _ = struct.unpack_from('<8I', data)
    if (magic, cpu, kind) != (0xfeedfacf, 0x100000c, 1) or extent > len(data)-32:
        raise ValueError('Actual thin ARM64 object required')
    at = 32
    for _ in range(count):
        if at + 8 > 32 + extent:
            raise ValueError('Command header outside probe')
        command, size = struct.unpack_from('<II', data, at)
        if size < 8 or at + size > 32 + extent:
            raise ValueError('Command outside probe')
        if command == 0x19:
            if size < 72:
                raise ValueError('Truncated segment')
            sections = struct.unpack_from('<I', data, at+64)[0]
            if sections > (size-72)//80:
                raise ValueError('Section table outside segment')
            for index in range(sections):
                pos = at+72+80*index
                name, segment, _, length, offset = struct.unpack_from('<16s16sQQI', data, pos)
                if name.rstrip(b'\0') == b'__const' and segment.rstrip(b'\0') == b'__TEXT':
                    if length != 80 or offset > len(data) or length > len(data)-offset:
                        raise ValueError('Unexpected probe constant extent')
                    return list(struct.unpack_from('<10Q', data, offset))
        at += size
    raise ValueError('Actual probe constant section absent')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    parser.add_argument('--lab-root', type=Path, default=ROOT)
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', args.run):
        parser.error('Use a canonical fresh run name')
    lab = args.lab_root.resolve()
    out = ROOT/'artifacts/esim-001'/args.run
    out.mkdir(parents=True, exist_ok=False)
    commands, checks = [], []
    report = dict(kind='host-test', origin='local-host', outcome='fail',
                  recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                  commands=commands, checks=checks, device_executed=False,
                  physical_transport_qualified=False, active_profile_qualified=False,
                  provisioning_qualified=False, ios16_frontend_qualified=False,
                  native_device_qualified=False, sdk_used=False)

    def relative(path):
        return str(path.relative_to(lab)) if path.is_relative_to(lab) else str(path)

    def run(argv, label, timeout=30, allowed_codes=(0,)):
        argv = [str(a) for a in argv]
        try:
            result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
            code, stdout, stderr, timed_out = result.returncode, result.stdout, result.stderr, False
        except subprocess.TimeoutExpired as error:
            code, stdout, stderr, timed_out = -1, '', str(error), True
        (out/(label+'.stdout.txt')).write_text(stdout)
        (out/(label+'.stderr.txt')).write_text(stderr)
        commands.append(dict(argv=argv, cwd=str(ROOT), exit_code=code, timed_out=timed_out,
                             stdout=relative(out/(label+'.stdout.txt')), stderr=relative(out/(label+'.stderr.txt'))))
        if code not in allowed_codes:
            raise RuntimeError(label+' failed;retained exact diagnostics')
        return stdout

    try:
        catalog = json.loads((SOURCE/'provenance.json').read_text())
        for source in catalog['sources']:
            checkout = lab/'references'/source['id']
            revision = run(['git','-C',checkout,'rev-parse','HEAD'], source['id']+'-revision').strip()
            if revision != source['revision']:
                raise ValueError('Pinned source revision changed')
            run(['git','-C',checkout,'diff','--exit-code','HEAD'],source['id']+'-clean')
            for name, expected in source['files'].items():
                if sha(checkout/name) != expected:
                    raise ValueError('Reviewed source bytes changed: '+name)
        checks.append(dict(name='pinned-primary-source-revisions-and-files', pass_check=True))
        cc = Path(shutil.which('cc') or '/usr/bin/cc').resolve()
        clang = NDK/'clang'
        native_clang = Path('/home/egor/.local/bin/clang')
        report['tools_sha256'] = {str(p):sha(p) for p in [cc, clang, native_clang.resolve(), NDK/'llvm-readobj', NDK/'llvm-objcopy']}
        flags = ['-std=c11','-Wall','-Wextra','-Werror','-Wconversion','-Wshadow','-I',SOURCE]
        for name, compiler in [('gcc',cc),('clang',clang)]:
            binary = out/('session-'+name)
            instrumentation = ['-fsanitize=undefined','-fsanitize-trap=all','-fno-omit-frame-pointer'] if name == 'clang' else []
            profile = name+('-ubsan-trap' if instrumentation else '-strict')
            run([compiler,*flags,'-D_GNU_SOURCE=1','-O1','-g',*instrumentation,'-pthread',SOURCE/'session.c',SOURCE/'tests/session_test.c','-o',binary],profile+'-build')
            result = run([binary],profile+'-execute',timeout=15)
            if 'PASS 11 scenario groups' not in result:
                raise ValueError('Actual scenario completion marker missing')
            checks.append(dict(name=profile+'-actual-eleven-scenario-groups',pass_check=True))
        negative = out/'undefined-negative'
        run([clang,*flags,'-O1','-fsanitize=undefined','-fsanitize-trap=all',SOURCE/'tests/undefined_negative.c','-o',negative],'ubsan-negative-build')
        ir=out/'undefined-negative.ll'
        run([clang,*flags,'-O1','-fsanitize=undefined','-fsanitize-trap=all','-S','-emit-llvm',SOURCE/'tests/undefined_negative.c','-o',ir],'ubsan-negative-IR')
        if 'llvm.ubsantrap' not in ir.read_text():
            raise ValueError('Actual UBSan instrumentation absent')
        run([negative],'ubsan-negative-execute',allowed_codes=(-4,))
        checks.append(dict(name='actual-UBSan-instrumentation-traps-deliberate-overflow',pass_check=True,negative_exit_code=commands[-1]['exit_code']))
        native_resources = Path(run([native_clang,'-print-resource-dir'],'native-clang-resources').strip())
        runtime = native_resources/'lib/x86_64-unknown-linux-gnu'
        runtime_paths = [runtime/'libclang_rt.asan_static.a',runtime/'libclang_rt.asan.a',runtime/'libclang_rt.ubsan_standalone.a']
        report['native_runtime_sha256'] = {str(p):sha(p) for p in runtime_paths}
        run([native_clang,'--version'],'native-clang-version')
        instrument = ['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer']
        binary = out/'session-native-asan-ubsan'
        run([native_clang,*flags,'-D_GNU_SOURCE=1',*instrument,'-pthread',SOURCE/'session.c',SOURCE/'tests/session_test.c','-o',binary],'native-sanitizer-build')
        environment = ['env','ASAN_OPTIONS=detect_leaks=1:halt_on_error=1','UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1']
        result = run([*environment,binary],'native-sanitizer-execute',timeout=15)
        if 'PASS 11 scenario groups' not in result:
            raise ValueError('Actual native sanitizer completion marker missing')
        run(['ldd',binary],'native-sanitizer-dynamic-dependencies')
        negative = out/'address-negative'
        run([native_clang,*flags,*instrument,SOURCE/'tests/address_negative.c','-o',negative],'asan-negative-build')
        run([*environment,negative],'asan-negative-execute',allowed_codes=(1,))
        diagnostic=(out/'asan-negative-execute.stderr.txt').read_text()
        if 'AddressSanitizer: heap-buffer-overflow' not in diagnostic:
            raise ValueError('Intentional overflow did not produce actual ASan diagnosis')
        checks.append(dict(name='native-ASan-UBSan-eleven-scenarios-and-deliberate-heap-overflow-control',pass_check=True))
        report['host_profiles'] = dict(gcc='Strict warnings and actual guard-page boundary execution',clang='Actual runtime-free UBSan trap and guard-page execution',native_clang='Actual Linux ASan+UBSan, leak detection and intentional overflow runtime control',asan_qualified=True,sanitizer_limits='ESIMHOST-001/002 retain missing GCC shared sanitizer and NDK28 host Linux ASan archives;existing NDK27 native Linux archives used without system changes or Android runtime substitution')
        abi = {}
        for name, triple in [('elf','aarch64-none-elf'),('macho','arm64-apple-ios16.5')]:
            target = ['-target',triple,'-ffreestanding','-fno-builtin','-O2']
            obj = out/(name+'-session.o')
            run([clang,*flags,*target,'-c',SOURCE/'session.c','-o',obj],name+'-actual-module-build')
            run([NDK/'llvm-readobj','--file-headers','--symbols',obj],name+'-actual-module-inspection')
            probe = out/(name+'-abi.o')
            run([clang,*flags,*target,'-c',SOURCE/'tests/abi_probe.c','-o',probe],name+'-actual-abi-build')
            run([NDK/'llvm-readobj','--file-headers','--sections','--symbols',probe],name+'-actual-abi-inspection')
            if name == 'elf':
                raw = out/'elf-abi.bin'
                run([NDK/'llvm-objcopy','--dump-section','.rodata='+str(raw),probe],name+'-independent-constant-dump')
                abi[name] = list(struct.unpack('<10Q',raw.read_bytes()))
            else:
                abi[name] = macho_constants(probe)
        if abi['elf'] != abi['macho'] or abi['elf'][3] != 4 or abi['elf'][6:] != [2,65544,65538,4096]:
            raise ValueError('Actual target ABI differs')
        report['target_layout'] = dict(names=['session_size','session_alignment','cancel_offset','atomic_uint_size','transport_size','limits_size','atomic_int_lock_free','max_command','max_response','max_exchanges'],values=abi)
        checks.append(dict(name='actual-ARM64-ELF-and-MachO-module-builds',pass_check=True))
        checks.append(dict(name='independent-target-data-layouts-agree',pass_check=True))
        checks.append(dict(name='all-device-profile-provisioning-and-ios-claims-false',pass_check=not any(report[k] for k in ['device_executed','physical_transport_qualified','active_profile_qualified','provisioning_qualified','ios16_frontend_qualified','native_device_qualified'])))
        report['outcome']='pass'
    except Exception as error:
        report['error']=str(error)
    report['summary']='Owned bounded APDU/session/error/cancellation/cleanup host qualification;physical transport and provisioning absent'
    report['source_sha256']={relative(p):sha(p) for p in sorted(SOURCE.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}
    report['commit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    files=sorted(p for p in out.rglob('*') if p.is_file())
    evidence={k:report[k] for k in ['kind','origin','outcome','recorded_at','summary','commands','commit','device_executed']}
    evidence.update(artifacts=[relative(p) for p in files],sha256={relative(p):sha(p) for p in files})
    (out/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps(dict(outcome=report['outcome'],error=report.get('error'),checks=len(checks),evidence=relative(out/'evidence.json'))))
    return 0 if report['outcome']=='pass' else 1


if __name__=='__main__':
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    sys.exit(main())
