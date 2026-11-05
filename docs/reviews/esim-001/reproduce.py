#!/usr/bin/env python3
"""Independent bounded ESIM review reproduction; no implementation writes."""
import datetime
import hashlib
import json
from pathlib import Path
import resource
import struct
import subprocess
import sys

HERE = Path(__file__).resolve().parent
WT = HERE.parents[2]
MAIN = WT.parents[1]
IMPL = MAIN / 'worktrees/esim-001-20261105'
SRC = IMPL / 'src/platform/esim'
TIP = '9daf884467c1fe0b816a53dafe86675587570605'
OUT = WT / 'artifacts/rev-esim-001' / sys.argv[1]
OUT.mkdir(parents=True, exist_ok=False)
commands, checks = [], []
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

def digest(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def relative(path):
    return str(Path(path).relative_to(MAIN))

def run(name, argv, allowed=(0,)):
    argv = [str(a) for a in argv]
    p = subprocess.run(argv, cwd=WT, capture_output=True, timeout=45)
    stdout, stderr = OUT/(name+'.stdout'), OUT/(name+'.stderr')
    stdout.write_bytes(p.stdout); stderr.write_bytes(p.stderr)
    commands.append(dict(argv=argv,cwd=str(WT),exit_code=p.returncode,
                         stdout=relative(stdout),stderr=relative(stderr),timed_out=False))
    assert p.returncode in allowed, (name,p.returncode,p.stderr.decode(errors='replace'))
    return p.stdout

def pass_check(name, **kw):
    checks.append(dict(name=name, pass_check=True, **kw))

def macho_constants(path):
    # Separate object reader, not imported from the implementation checker.
    b = path.read_bytes()
    magic, cpu, sub, kind, count, extent, flags, reserved = struct.unpack_from('<8I', b)
    assert magic == 0xfeedfacf and cpu == 0x100000c and kind == 1
    cursor = 32
    for i in range(count):
        code, size = struct.unpack_from('<II',b,cursor)
        assert size >= 8 and cursor+size <= 32+extent <= len(b)
        if code == 0x19:
            assert size >= 72
            nsect = struct.unpack_from('<I',b,cursor+64)[0]
            assert 72+nsect*80 <= size
            for j in range(nsect):
                section = cursor+72+j*80
                if b[section:section+16].rstrip(b'\0') == b'__const':
                    nbytes, offset = struct.unpack_from('<QI',b,section+40)
                    assert nbytes == 80 and offset+nbytes <= len(b)
                    return struct.unpack_from('<10Q',b,offset)
        cursor += size
    raise AssertionError('No constant section')

report = dict(kind='source-review',origin='local-host',outcome='fail',
              recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
              commit=TIP,review_worktree_commit=run('review-head',['git','rev-parse','HEAD']).decode().strip(),
              commands=commands,checks=checks,device_executed=False,
              summary='Independent source review and bounded synthetic reproduction of exact ESIM-001 tip')
try:
    assert run('implementation-head',['git','-C',IMPL,'rev-parse','HEAD']).decode().strip() == TIP
    assert not run('implementation-clean',['git','-C',IMPL,'status','--porcelain','--untracked-files=no'])
    run('implementation-ancestry',['git','-C',IMPL,'merge-base','--is-ancestor','bc2b6ec260c3235f6be30fc5ea63a6eaccfef9b0',TIP])
    pass_check('exact-implementation-tip-and-clean-tracked-worktree')
    source = json.loads((SRC/'provenance.json').read_text())
    for entry in source['sources']:
        checkout = MAIN/'references'/entry['id']
        assert run(entry['id']+'-head',['git','-C',checkout,'rev-parse','HEAD']).decode().strip() == entry['revision']
        run(entry['id']+'-clean',['git','-C',checkout,'diff','--exit-code','HEAD'])
        assert all(digest(checkout/name) == value for name,value in entry['files'].items())
    pass_check('all-local-source-pins-and-reviewed-file-hashes')
    existing = json.loads((IMPL/'artifacts/esim-001/session5/evidence.json').read_text())
    for name, value in existing['sha256'].items():
        assert digest(MAIN/name) == value, name
    prior = json.loads((IMPL/'artifacts/esim-001/session5/report.json').read_text())
    for name, value in prior['source_sha256'].items():
        assert digest(MAIN/name) == value, name
    assert existing['commit'] == 'bc2b6ec260c3235f6be30fc5ea63a6eaccfef9b0'
    assert all(not prior[k] for k in ['physical_transport_qualified','active_profile_qualified',
               'provisioning_qualified','ios16_frontend_qualified','native_device_qualified'])
    pass_check('existing-session5-artifact-and-source-hashes',artifact_count=len(existing['sha256']))
    compiler = Path('/home/egor/.local/bin/clang')
    bindir = compiler.resolve().parent
    run('clang-version',[compiler,'--version'])
    report['tools_sha256'] = {str(p):digest(p) for p in [compiler.resolve(),bindir/'llvm-readobj',bindir/'llvm-objcopy']}
    runtime = Path(run('clang-resource',[compiler,'-print-resource-dir']).decode().strip())/'lib/x86_64-unknown-linux-gnu'
    report['runtime_sha256'] = {str(runtime/n):digest(runtime/n) for n in ['libclang_rt.asan.a','libclang_rt.asan_static.a','libclang_rt.ubsan_standalone.a']}
    flags = ['-std=c11','-Wall','-Wextra','-Werror','-Wconversion','-Wshadow','-I',SRC]
    instrument = ['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer']
    env = ['env','ASAN_OPTIONS=detect_leaks=1:halt_on_error=1','UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1']
    original = OUT/'original-scenarios'
    run('original-build',[compiler,*flags,*instrument,'-D_GNU_SOURCE=1','-pthread',SRC/'session.c',SRC/'tests/session_test.c','-o',original])
    assert b'PASS 11 scenario groups' in run('original-run',[*env,original])
    pass_check('independently-rebuilt-original-eleven-groups-ASan-UBSan')
    probe = OUT/'independent-probe'
    run('independent-build',[compiler,*flags,*instrument,SRC/'session.c',HERE/'boundary_probe.c','-o',probe])
    result = run('independent-run',[*env,probe]).decode().strip()
    assert 'PASS independent boundary controls' in result
    pass_check('independent-exhaustive-framing-and-lifecycle-controls',result=result)
    negative = OUT/'address-negative'
    run('asan-control-build',[compiler,*flags,*instrument,SRC/'tests/address_negative.c','-o',negative])
    run('asan-control-run',[*env,negative],allowed=(1,))
    assert b'AddressSanitizer: heap-buffer-overflow' in (OUT/'asan-control-run.stderr').read_bytes()
    negative = OUT/'undefined-negative'
    run('ubsan-control-build',[compiler,*flags,'-O1','-fsanitize=undefined','-fsanitize-trap=all',SRC/'tests/undefined_negative.c','-o',negative])
    run('ubsan-control-run',[negative],allowed=(-4,))
    pass_check('actual-ASan-overflow-report-and-UBSan-SIGILL-negative-controls')
    layouts = {}
    for kind, triple in [('elf','aarch64-none-elf'),('macho','arm64-apple-ios16.5')]:
        target = ['-target',triple,'-ffreestanding','-fno-builtin','-O2']
        module, obj = OUT/(kind+'-session.o'), OUT/(kind+'-abi.o')
        run(kind+'-module-build',[compiler,*flags,*target,'-c',SRC/'session.c','-o',module])
        run(kind+'-module-inspect',[bindir/'llvm-readobj','--file-headers','--symbols',module])
        run(kind+'-abi-build',[compiler,*flags,*target,'-c',SRC/'tests/abi_probe.c','-o',obj])
        run(kind+'-abi-inspect',[bindir/'llvm-readobj','--file-headers','--sections','--symbols',obj])
        if kind == 'elf':
            raw = OUT/'elf-constants.bin'
            run('elf-section',[bindir/'llvm-objcopy','--dump-section','.rodata='+str(raw),obj])
            layouts[kind] = struct.unpack('<10Q',raw.read_bytes())
        else:
            layouts[kind] = macho_constants(obj)
    assert layouts['elf'] == layouts['macho'] == (96,8,60,4,48,12,2,65544,65538,4096)
    report['target_layout'] = layouts
    pass_check('actual-ELF-MachO-module-compiles-and-independent-layout-reader')
    report['outcome'] = 'pass'
except Exception as error:
    report['error'] = repr(error)
finally:
    report['source_sha256'] = {str(p):digest(p) for p in sorted(SRC.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}
    report['review_inputs_sha256'] = {str(p):digest(p) for p in [HERE/'boundary_probe.c',Path(__file__)]}
    report['child_peak_rss_kib'] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    report['limits'] = ['Sequential compiler jobs; 45 seconds per command; no hardware I/O.',
       'Synthetic callback qualification only; no physical transport, provisioning or selected Apple frontend.',
       'Existing full checker not rerun because it writes into the implementation worktree and pins unavailable NDK28 tools.']
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    files = sorted(p for p in OUT.iterdir() if p.is_file())
    evidence = {k:report[k] for k in ['kind','origin','outcome','recorded_at','commit','commands','summary','device_executed']}
    evidence.update(artifacts=[relative(p) for p in files],sha256={relative(p):digest(p) for p in files})
    (OUT/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps(dict(outcome=report['outcome'],checks=checks,error=report.get('error'),evidence=relative(OUT/'evidence.json'),peak_rss_kib=report['child_peak_rss_kib']),indent=2))
sys.exit(0 if report['outcome'] == 'pass' else 1)
