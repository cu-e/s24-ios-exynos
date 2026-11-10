#!/usr/bin/env python3
"""KRN-041: consumers, providers and a checked fix for the 37 missing kernel exports.

Runs, in a fresh artifacts/krn-041/RUN directory:
  1. pin and input checks (sources, export files, STR-041 kernel, KRN-026 names);
  2. a build of the genuine SETUP/kextsymboltool from apple-xnu c54f35ca for the host;
  3. a reference scan of every link input of the STR-041 kernel and of the
     project, HakiOS and S24-port driver sources;
  4. the 0001 stub patch compiled into pmap.o under the recorded STR-023 recipe,
     with an unpatched control compile;
  5. a relink of a copy of the STR-041 kernel with that object, nothing else changed;
  6. the genuine check_all_exports passes and per-component symbol sets for
     {STR-041 kernel, relinked kernel} x {genuine lists, 0002 profile lists}.

Every expectation is checked; the report records the outcome. It never runs a
kernel, writes no shared input and needs no device.
"""
import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shutil
import subprocess
import time

MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
HERE = Path(__file__).resolve().parent
PINS = {
    'apple-xnu': (MAIN/'references/apple-xnu', 'c54f35ca767986246321eb901baf8f5ff7923f6a'),
    'scion-avf': (MAIN/'references/hakios-scion-full', 'a6f4bc38aa244359cd365c976244a88c9d6b3304'),
    's24-port': (MAIN/'references/s24-port', 'c8860decc62c6d6180e609036d027a2997972420'),
    'hakios-e1s-tools': (MAIN/'references/hakios-e1s-tools', 'd82c64a3a31cd27a0a0afbf6e213e467e44b1b4c'),
}
XNU = PINS['apple-xnu'][0]
HAKIOS = PINS['scion-avf'][0]
S24 = PINS['s24-port'][0]
NATIVE_XNU = MAIN/'worktrees/str-014-e1s-native-source-ports-20261106/artifacts/e1s-native-source-ports/derive-001/xnu'
KRN040_XNU = MAIN/'artifacts/xnu-prepare/e1s-dependency-source-session1/xnu'
LINK = MAIN/'worktrees/str-041-e1s-native-link-image-20261110/artifacts/e1s-native-link/link-001'
KERNEL = LINK/'kernel/kernel.unstripped'
KERNEL_SHA256 = '4c9536d89b6ad61e49e8cc45e82820f00df4343c478d14685009ad504313595f'
COMPILE_PLAN = MAIN/'worktrees/str-023-e1s-native-osfmk-b-20261106/artifacts/e1s-native-compile/osfmk-b/execute-002/execution-plan.json'
PMAP_SOURCE_SHA256 = 'cc6d5d2ead6c40fa63c5e5d8d09169d0d8252abece33a8c1a75d2210475ca8bd'
KRN026_INPUTS = MAIN/'worktrees/krn-026-20261105/fixtures/public/kernel-export-gaps/inputs.json'
KRN026_INPUTS_SHA256 = '078f5dc1c3e99bbce9f0c678f4dd4a9660e87407b03aed2db27439983ac4b70d'
KRN040_REPORT = MAIN/'artifacts/krn-export-coverage/cover-003/report.json'
KRN024_REPORT = MAIN/'worktrees/krn-024-20261105/artifacts/kernel-provider-link/native-session2/report.json'
TOOLS = MAIN/'artifacts/xnu-macho-tools/macho-session4/prefix/bin/aarch64-apple-darwin-'
HOST_CC = Path('/home/egor/.local/bin/clang')
CC_KEXT = MAIN/'worktrees/krn-025-20261105/artifacts/xnu-cc-kext/controls-session2/resource-positive/lib/darwin/libclang_rt.cc_kext_ios.a'
COMPONENTS = ['BSDKernel', 'IOKit', 'Libkern', 'Mach', 'MACFramework', 'Unsupported', 'Private']
PATCH_STUBS = HERE/'0001-arm-pmap-unsupported-queries.patch'
PATCH_PROFILE = HERE/'0002-no-apple-soc-library-exports.patch'
DOSSIER = HERE/'dossier.json'
S24_0009 = S24/'xnu/legacy-sweet-patches/0009-sweet-drop-apple-soc-only-exports.patch'
STUBBED = ['_pmap_cs_configuration', '_pmap_has_iofilter_protected_write']
CODE_SUFFIXES = ('.c', '.cpp', '.cc', '.h', '.hpp', '.iig', '.s', '.S', '.m', '.mm')
CONSUMER_ROOTS = [
    ('project src', MAIN/'src'),
    ('HakiOS drivers', HAKIOS/'drivers'),
    ('HakiOS xnu/files', HAKIOS/'xnu/files'),
    ('HakiOS avf', HAKIOS/'avf'),
    ('HakiOS xnu-deps/iig-impl', HAKIOS/'xnu-deps/iig-impl'),
    ('S24-port xnu/hackios/files', S24/'xnu/hackios/files'),
    ('S24-port shim', S24/'shim'),
]
PATCH_ROOTS = [
    ('project patches', MAIN/'patches'),
    ('HakiOS xnu', HAKIOS/'xnu'),
    ('S24-port xnu', S24/'xnu'),
]
GIT_ENV = dict(GIT_NO_LAZY_FETCH='1', GIT_OPTIONAL_LOCKS='0', GIT_TERMINAL_PROMPT='0')
RLIMIT_AS = 6 << 30
COMMANDS = []


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(role, argv, cwd=None, env=None, timeout=900, stdin=None, check=True):
    """Run one child with an address-space cap; record argv, exit code, time and peak RSS."""
    started = time.monotonic()
    full_env = {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'LANG': 'C', **GIT_ENV, **(env or {})}

    def limit():
        resource.setrlimit(resource.RLIMIT_AS, (RLIMIT_AS, RLIMIT_AS))
    proc = subprocess.Popen([str(a) for a in argv], cwd=cwd, env=full_env, stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, preexec_fn=limit)
    try:
        out, err = proc.communicate(stdin.encode() if stdin is not None else None, timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
        raise RuntimeError(f'{role}: timed out after {timeout}s')
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    record = dict(role=role, argv=[str(a) for a in argv], cwd=str(cwd) if cwd else None, exit_code=proc.returncode,
                  seconds=round(time.monotonic()-started, 3), max_child_rss_kib_so_far=usage.ru_maxrss)
    COMMANDS.append(record)
    out, err = out.decode(errors='replace'), err.decode(errors='replace')
    if check and proc.returncode:
        raise RuntimeError(f'{role}: exit {proc.returncode}: {err[-800:]}')
    return proc.returncode, out, err


def git(repo, *args):
    return run('git', ['git', '-C', repo, *args])[1]


_LIBSTDCXX = ctypes.CDLL('libstdc++.so.6')
_LIBSTDCXX.__cxa_demangle.restype = ctypes.c_void_p
_LIBSTDCXX.__cxa_demangle.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)]
_LIBC = ctypes.CDLL('libc.so.6')


def demangle(symbol):
    """What kextsymboltool prints: __cxa_demangle(name + 1), or the name itself when that fails."""
    status = ctypes.c_int()
    ptr = _LIBSTDCXX.__cxa_demangle(symbol[1:].encode(), None, None, ctypes.byref(status))
    if not ptr or status.value:
        return symbol
    text = ctypes.cast(ptr, ctypes.c_char_p).value.decode()
    _LIBC.free(ctypes.c_void_p(ptr))
    return text


# ---- export-file parsing (only to locate lines; membership is decided by the genuine tool) ----

def export_lines(path):
    """Map each symbol name to its 1-based line number in an export file."""
    found = {}
    for number, line in enumerate(Path(path).read_text().splitlines(), 1):
        token = line.split('#', 1)[0].strip()
        if not token or token.startswith('.'):
            continue
        name = re.split(r'[\s:]', token, maxsplit=1)[0]
        found.setdefault(name, number)
    return found


# ---- nm scan ----

def nm_scan(files):
    """External symbols per input file: {name: {'defined': [...], 'undefined': [...]}}."""
    table = {}
    for start in range(0, len(files), 200):
        chunk = files[start:start+200]
        out = run('nm-scan', [str(TOOLS)+'nm', '-A', '-g', *chunk], timeout=600)[1]
        for line in out.splitlines():
            match = re.match(r'^(.*?):\s+(?:[0-9a-f]+\s+)?([A-Za-z])\s+(\S+)$', line)
            if not match:
                match = re.match(r'^(.*?): +([A-Za-z]) (\S+)$', line)
            require(match, 'Unparsed nm line: '+line)
            where, kind, name = match.groups()
            entry = table.setdefault(name, dict(defined=[], undefined=[]))
            entry['undefined' if kind == 'U' else 'defined'].append(where)
    return table


def external_symbols(path):
    """Sorted external symbol lines (type and name) of one object or image."""
    out = run('nm', [str(TOOLS)+'nm', '-g', path])[1]
    lines = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            lines.add(' '.join(parts[-2:]))
    return lines


def text_words(path):
    """__TEXT,__text of an object as {address: 32-bit word in hex}, from otool -t."""
    words = {}
    for line in run('otool -t', [str(TOOLS)+'otool', '-t', path])[1].splitlines():
        match = re.match(r'^([0-9a-f]{16})\s+(.*)$', line)
        if match:
            base = int(match.group(1), 16)
            for index, word in enumerate(match.group(2).split()):
                words[base+4*index] = word
    return words


def symbol_addresses(path):
    found = {}
    for line in run('nm', [str(TOOLS)+'nm', '-g', path])[1].splitlines():
        parts = line.split()
        if len(parts) == 3:
            found[parts[2]] = int(parts[0], 16)
    return found


def allsymbols(kernel, out):
    """The genuine recipe: $(NM) -gj kernel | sort -u > allsymbols."""
    text = run('allsymbols', [str(TOOLS)+'nm', '-gj', kernel])[1]
    names = sorted(set(n for n in text.split('\n') if n))
    out.write_text('\n'.join(names)+'\n')
    return set(names)


# ---- source scans ----

def xnu_identifier_hits(identifier):
    """git grep -w at the pinned XNU commit, outside config/*.exports."""
    code, out, _ = run('xnu-grep', ['git', '-C', XNU, 'grep', '-n', '-w', '-I', '-e', identifier, 'HEAD', '--', '.', ':!config/*.exports'], check=False)
    require(code in (0, 1), 'git grep failed')
    return [line.split(':', 1)[1] for line in out.splitlines()]


def code_hits(identifiers):
    """Occurrences in driver/code sources (consumers) and in lines patches add (not export lists)."""
    pattern = re.compile(r'\b(' + '|'.join(map(re.escape, identifiers)) + r')\b')
    hits = {i: [] for i in identifiers}
    for label, root in CONSUMER_ROOTS:
        if not root.exists():
            continue
        for path in sorted(root.rglob('*')):
            if path.is_file() and path.suffix in CODE_SUFFIXES and '.git' not in path.parts:
                for number, line in enumerate(path.read_text(errors='replace').splitlines(), 1):
                    for match in pattern.finditer(line):
                        hits[match.group(1)].append(f'{label}: {path.relative_to(root)}:{number}')
    for label, root in PATCH_ROOTS:
        if not root.exists():
            continue
        for path in sorted(root.rglob('*.patch')):
            target = None
            for number, line in enumerate(path.read_text(errors='replace').splitlines(), 1):
                if line.startswith('+++ '):
                    target = line[4:].strip()
                    continue
                if not line.startswith('+') or (target and target.endswith('.exports')):
                    continue
                for match in pattern.finditer(line):
                    hits[match.group(1)].append(f'{label}: {path.relative_to(root)}:{number} (added line in {target})')
    return hits


def identifier(symbol):
    """C identifier for a C symbol, the class name for a C++ class symbol."""
    if symbol.startswith('__Z'):
        match = re.match(r'__Z(?:N|TV)(\d+)', symbol)
        require(match, 'Unexpected C++ symbol '+symbol)
        length = int(match.group(1))
        return symbol[match.end():match.end()+length]
    return symbol[1:]


# ---- kextsymboltool ----

def build_kextsymboltool(out):
    include = out/'include'
    (include/'mach-o').mkdir(parents=True)
    for name in ['loader.h', 'nlist.h', 'fat.h']:
        shutil.copy2(XNU/'EXTERNAL_HEADERS/mach-o'/name, include/'mach-o'/name)
    hostinc = HAKIOS/'xnu-deps/hostinc'
    source = XNU/'SETUP/kextsymboltool/kextsymboltool.c'
    obj, binary = out/'kextsymboltool.o', out/'kextsymboltool'
    # SETUP/kextsymboltool/Makefile: $(HOST_CC) -Wall -g -O0 -I$(SOURCE) -I. -c; link with -lstdc++.
    # -isysroot/-mmacosx-version-min are macOS-only; HakiOS xnu-build.sh supplies the Linux compat includes.
    run('kextsymboltool-cc', [HOST_CC, '-include', hostinc/'hostcompat.h', '-I'+str(hostinc), '-I'+str(HERE/'compat'), '-I'+str(include),
                              '-Wall', '-g', '-O0', '-I'+str(source.parent), '-I.', '-c', '-o', obj, source], cwd=out)
    run('kextsymboltool-ld', [HOST_CC, '-o', binary, obj, '-lstdc++'], cwd=out)
    inputs = {str(p): sha(p) for p in [source, hostinc/'hostcompat.h', *sorted(hostinc.rglob('*.h')), HERE/'compat/uuid/uuid.h',
                                       *sorted((include/'mach-o').iterdir())]}
    return binary, dict(binary_sha256=sha(binary), compiler=str(HOST_CC.resolve()), compiler_sha256=sha(HOST_CC.resolve()), inputs_sha256=inputs)


def export_args(directory, components):
    args = []
    for component in components:
        args += ['-export', directory/f'{component}.exports', '-export', directory/f'{component}.arm64.exports']
    return args


def check_all_exports(tool, imports, directory, demangled_to_symbol, output_dir, output=None):
    """The two passes of config/Makefile check_all_exports with -arch arm64.

    The recipe writes to /dev/null. On Linux lseek() on /dev/null returns 0, so the tool's
    seekFile() check fails after the membership decision (kextsymboltool.c:707-710 decides
    before the output is opened). By default the output goes to a scratch file instead.
    """
    passes = {}
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, excluded in [('without-Private', 'Private'), ('without-Unsupported', 'Unsupported')]:
        components = [c for c in COMPONENTS if c != excluded]
        target = output or output_dir/f'{name}.symbolset'
        code, _, err = run('check_all_exports '+name, [tool, '-arch', 'arm64', '-import', imports, *export_args(directory, components), '-output', target], check=False)
        printed = re.findall(r'^exported name not in import list: (.*)$', err, re.M)
        passes[name] = dict(exit_code=code, missing=sorted(demangled_to_symbol.get(p, p) for p in printed), stderr_tail=err[-400:])
    return passes


def symbol_sets(tool, imports, directory, out):
    """config/Makefile symbol_set_template for each component (no arm64 iPhoneOS platform files exist)."""
    out.mkdir(parents=True)
    results = {}
    for component in COMPONENTS:
        target = out/f'{component}.symbolset'
        code, _, err = run('symbolset '+component, [tool, '-arch', 'arm64', '-import', imports, *export_args(directory, [component]), '-output', target], check=False)
        results[component] = dict(exit_code=code, missing=len(re.findall(r'^exported name not in import list:', err, re.M)),
                                  sha256=sha(target) if code == 0 and target.exists() else None)
    return results


# ---- patches, compile, link ----

def apply_patch(patch, root, role):
    run(role, ['patch', '-p1', '--no-backup-if-mismatch', '-i', patch], cwd=root)


def compile_pmap(out, patched):
    plan = json.loads(COMPILE_PLAN.read_text())
    command = next(c for c in plan['commands'] if c['id'] == 'osfmk/pmap.o')
    require(command['source_sha256'] == PMAP_SOURCE_SHA256 == sha(command['source']), 'pmap.c source drifted')
    tree = out/('patched' if patched else 'control')
    (tree/'osfmk/arm/pmap').mkdir(parents=True)
    source = tree/'osfmk/arm/pmap/pmap.c'
    shutil.copy2(command['source'], source)
    if patched:
        apply_patch(PATCH_STUBS, tree, 'patch 0001 native pmap.c')
    cwd = out/'cwd'
    if not cwd.exists():
        shutil.copytree(command['cwd'], cwd, symlinks=True)
    obj, depfile = tree/'pmap.o', tree/'pmap.o.d'
    argv, changed = list(command['argv']), 0
    for index, value in enumerate(argv):
        if value == command['source']:
            argv[index], changed = str(source), changed+1
        elif value == command['object'] and argv[index-1] == '-o':
            argv[index], changed = str(obj), changed+1
        elif value == command['depfile'] and argv[index-1] == '-MF':
            argv[index], changed = str(depfile), changed+1
    require(changed == 3, 'Expected to change exactly source, object and depfile')
    home = out/'home'
    home.mkdir(exist_ok=True)
    run('compile pmap.o '+('patched' if patched else 'control'), argv, cwd=cwd, env=dict(HOME=str(home), TMPDIR=str(home)), timeout=1200)
    deps = Path(depfile).read_text().replace('\\\n', ' ').split()
    deps = sorted({d.replace(str(cwd), command['cwd']).replace(str(source), command['source']) for d in deps if not d.endswith(':')})
    original = Path(command['depfile']).read_text().replace('\\\n', ' ').split()
    original = sorted({d for d in original if not d.endswith(':')})
    return dict(object=str(obj), object_sha256=sha(obj), source_sha256=sha(source), argv_changes=changed,
                depfile_matches_original=deps == original, recipe=command['recipe'], original_object=command['object'],
                original_object_sha256=sha(command['object']))


def relink(out, pmap_object, extra=(), check=True):
    evidence = json.loads((LINK/'evidence.json').read_text())
    command = next(c for c in evidence['commands'] if c.get('role') == 'native-driver-link')['process']
    original_filelist = (LINK/'kernel/link.filelist').read_text().splitlines()
    original_pmap = str(LINK/'objects/osfmk/pmap.o')
    require(original_filelist.count(original_pmap) == 1, 'pmap.o not listed exactly once')
    out.mkdir(parents=True)
    filelist = out/'link.filelist'
    filelist.write_text('\n'.join(pmap_object if line == original_pmap else line for line in original_filelist)+'\n')
    kernel = out/'kernel.unstripped'
    argv, changed = list(command['argv']), 0
    for index, value in enumerate(argv):
        if argv[index-1] == '-filelist' and value == str(LINK/'kernel/link.filelist'):
            argv[index], changed = str(filelist), changed+1
        elif argv[index-1] == '-o' and value == str(KERNEL):
            argv[index], changed = str(kernel), changed+1
    require(changed == 2, 'Expected to change exactly the filelist and the output')
    home = out/'home'
    home.mkdir(parents=True)
    env = dict(command['environment'])
    env.update(HOME=str(home), TMPDIR=str(home), TMP=str(home), TEMP=str(home))
    argv += list(extra)
    code, _, err = run('relink kernel '+out.name, argv, cwd=out, env=env, timeout=600, check=check)
    undefined = dict(re.findall(r'"(_[^"]+)", referenced from:\n\s+(.*)', err))
    return kernel, dict(argv_changes=changed, filelist_lines_changed=1, extra_args=list(extra), stderr=err[-600:], exit_code=code,
                        undefined=undefined)


def kpi_exp(directory, out):
    """config/Makefile all-kpi.exp: generate_linker_exports.sh over EXPORTS_FILES plus the Kasan/Kcov lists."""
    exports = [directory/f'{c}{arch}.exports' for c in COMPONENTS for arch in ('', '.arm64')]
    run('generate_linker_exports '+out.name, ['sh', XNU/'config/generate_linker_exports.sh', out, *exports, XNU/'config/Unused.exports',
                                             XNU/'config/Kasan_disabled.exports', XNU/'config/Kcov_disabled.exports'])
    return out


def macho_summary(path):
    import struct
    data = Path(path).read_bytes()
    magic, cpu, _sub, filetype, count, size, _flags, _res = struct.unpack_from('<IiiIIIII', data, 0)
    segments, at, entry = [], 32, None
    for _ in range(count):
        cmd, length = struct.unpack_from('<II', data, at)
        if cmd == 0x19:
            segments.append(data[at+8:at+24].rstrip(b'\0').decode())
        elif cmd == 0x5:
            entry = struct.unpack_from('<Q', data, at+16+32*8)[0]
        at += length
    return dict(magic=hex(magic), cputype=hex(cpu), filetype=filetype, segments=segments, entry=hex(entry) if entry else None, size=len(data))


# ---- main ----

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    parser.add_argument('--guest-kernel', help='optional extra kernel to check with the genuine and profile lists (read only, no assertions)')
    args = parser.parse_args()
    require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', args.run), 'Invalid run name')
    out = MAIN/'artifacts/krn-041'/args.run
    out.mkdir(parents=True, exist_ok=False)
    checks, report = {}, dict(schema=1, task='KRN-041', run=args.run, started_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                              kernel_booted=False, device_used=False)

    def check(name, condition, detail=None):
        checks[name] = dict(ok=bool(condition), detail=detail)

    # 1. pins and inputs
    report['pins'] = {}
    for source_id, (path, expected) in PINS.items():
        head = git(path, 'rev-parse', 'HEAD').strip()
        report['pins'][source_id] = head
        check('pin '+source_id, head == expected, head)
    require(sha(KERNEL) == KERNEL_SHA256, 'STR-041 kernel drifted')
    require(sha(KRN026_INPUTS) == KRN026_INPUTS_SHA256, 'KRN-026 inputs drifted')
    names = json.loads(KRN026_INPUTS.read_text())['observed_export_only_names']
    krn040 = json.loads(KRN040_REPORT.read_text())
    check('37 names = KRN-040 missing set', len(names) == 37 and sorted(names) == sorted(krn040['all_missing']))
    files = [f'{c}.exports' for c in COMPONENTS] + [f'{c}.arm64.exports' for c in COMPONENTS]
    report['export_files_sha256'] = {f: sha(XNU/'config'/f) for f in files}
    check('native E1S tree export files = upstream', all(sha(NATIVE_XNU/'config'/f) == report['export_files_sha256'][f] for f in files))
    check('KRN-040 tree export files = upstream', all(sha(KRN040_XNU/'config'/f) == report['export_files_sha256'][f] for f in files))
    check('no arm64 iPhoneOS platform export files', not list((XNU/'config').glob('*.arm64.iPhoneOS.exports')))
    dossier = json.loads(DOSSIER.read_text())
    dropped = [n for family in dossier['families'].values() if family['decision'] == 'remove-from-profile' for n in family['names']]
    stubbed = [n for family in dossier['families'].values() if family['decision'] == 'implement-stub' for n in family['names']]
    check('dossier covers exactly the 37 names', sorted(dropped+stubbed) == sorted(names) and not set(dropped) & set(stubbed))
    check('stubbed names', sorted(stubbed) == STUBBED)

    # 2. locations, demangling, the RELEASE link referrers recorded by KRN-024
    locations = {}
    for f in files:
        for symbol, line in export_lines(XNU/'config'/f).items():
            if symbol in names:
                locations.setdefault(symbol, []).append(f'config/{f}:{line}')
    demangled = {n: demangle(n) for n in names}
    krn024 = json.loads(KRN024_REPORT.read_text())['actual_link']
    referrers = dict(re.findall(r'"(_[^"]+)", referenced from:\n\s+(.*)', krn024.get('diagnostic', '')))
    check('RELEASE link: the only referrer of each name is the exported symbols list',
          sorted(referrers) == sorted(names) and set(referrers.values()) == {'-exported_symbol[s_list] command line option'},
          dict(output=krn024.get('output'), exit_code=krn024.get('exit_code')))

    # 3. reference scan of every link input and source scans
    filelist = (LINK/'kernel/link.filelist').read_text().split()
    extra = [LINK/'kernel'/n for n in ['version.o', 'lastkerneldataconst.o', 'lastkernelconstructor.o', 'nonlto.o']]
    archives = [LINK/'libraries/kernel/libfirehose_kernel.a', LINK/'libraries/kernel/libpthread_kext.a', CC_KEXT]
    inputs = [*filelist, *map(str, extra), *map(str, archives)]
    scan = nm_scan(inputs)
    report['link_inputs'] = dict(objects=len(filelist), extra_objects=len(extra), archives={str(a): sha(a) for a in archives})
    controls = ['_panic', '_ml_static_ptovirt', '_pmap_iofilter_protected_write', '_pmap_in_ppl']
    report['scan_controls'] = {c: dict(defined=len(scan.get(c, {}).get('defined', [])), referencing_inputs=len(scan.get(c, {}).get('undefined', []))) for c in controls}
    check('scanner control: _panic is referenced by link inputs', report['scan_controls']['_panic']['referencing_inputs'] > 100)
    image = external_symbols(KERNEL)
    identifiers = sorted({identifier(n) for n in names})
    consumer = code_hits(identifiers)
    xnu_hits = {i: xnu_identifier_hits(i) for i in identifiers}
    rows = {}
    for n in names:
        entry = scan.get(n, dict(defined=[], undefined=[]))
        rows[n] = dict(demangled=demangled[n], export_lines=locations.get(n, []), link_input_definitions=entry['defined'],
                       link_input_references=entry['undefined'], in_str041_image=any(line.endswith(' '+n) for line in image),
                       xnu_source_hits=xnu_hits[identifier(n)], consumer_source_hits=consumer[identifier(n)],
                       release_link_referrer=referrers.get(n), decision='implement-stub' if n in stubbed else 'remove-from-profile')
    check('every name has exactly one export-list line', all(len(r['export_lines']) == 1 for r in rows.values()))
    check('no link input defines or references any of the 37', all(not r['link_input_definitions'] and not r['link_input_references'] for r in rows.values()))
    check('no consumer in project/HakiOS/S24-port code', all(not r['consumer_source_hits'] for r in rows.values()),
          {i: h for i, h in consumer.items() if h})

    negative_names = ['_ml_static_ptovirt', '_pmap_cs_configuration', '_pmap_has_iofilter_protected_write']
    consumer.update(code_hits(sorted({identifier(n) for n in negative_names} - set(consumer))))
    for n in negative_names:
        xnu_hits.setdefault(identifier(n), xnu_identifier_hits(identifier(n)))

    def guard(symbol):
        """A name may leave the profile only with no provider, no reference and no public declaration."""
        entry = scan.get(symbol, dict(defined=[], undefined=[]))
        reasons = []
        if entry['defined'] or any(line.endswith(' '+symbol) for line in image):
            reasons.append('defined')
        if entry['undefined']:
            reasons.append('referenced by %d link inputs' % len(entry['undefined']))
        if xnu_hits[identifier(symbol)]:
            reasons.append('declared or used in public XNU source')
        if consumer[identifier(symbol)]:
            reasons.append('used by driver code')
        return reasons
    report['guard'] = {n: guard(n) for n in dropped}
    check('guard admits every profile removal', all(not r for r in report['guard'].values()), report['guard'])
    negative = {n: guard(n) for n in negative_names}
    report['guard_negative_controls'] = negative
    check('guard rejects names with a provider, references or a public declaration', all(negative.values()), negative)

    # 4. export sets: genuine copies and the 0002 profile
    genuine, profile = out/'exports/genuine', out/'exports/profile'
    for directory in (genuine, profile):
        directory.mkdir(parents=True)
        for f in files:
            shutil.copy2(XNU/'config'/f, directory/f)
    profile_root = out/'exports/profile-root'
    (profile_root/'config').mkdir(parents=True)
    shutil.copy2(XNU/'config/Private.arm64.exports', profile_root/'config/Private.arm64.exports')
    apply_patch(PATCH_PROFILE, profile_root, 'patch 0002 export profile')
    shutil.copy2(profile_root/'config/Private.arm64.exports', profile/'Private.arm64.exports')
    before = (XNU/'config/Private.arm64.exports').read_text().splitlines()
    after = (profile/'Private.arm64.exports').read_text().splitlines()
    removed = [line for line in before if line not in after]
    check('0002 removes exactly the dossier removals and nothing else',
          sorted(removed) == sorted(dropped) and [line for line in before if line not in removed] == after)
    check('profile changes only Private.arm64.exports', [f for f in files if sha(genuine/f) != sha(profile/f)] == ['Private.arm64.exports'])
    legacy = out/'exports/s24-0009-root'
    (legacy/'config').mkdir(parents=True)
    for f in ['Private.exports', 'Private.arm64.exports']:
        shutil.copy2(XNU/'config'/f, legacy/'config'/f)
    apply_patch(S24_0009, legacy, 'patch S24-port 0009 (comparison only)')
    check('0002 = S24-port 0009 for Private.arm64.exports', sha(legacy/'config/Private.arm64.exports') == sha(profile/'Private.arm64.exports'))
    legacy_private = (legacy/'config/Private.exports').read_text().splitlines()
    check('S24-port 0009 also removes the two stubbed names from Private.exports',
          sorted(set((XNU/'config/Private.exports').read_text().splitlines()) - set(legacy_private)) == STUBBED)

    # 5. the 0001 stub patch applies to upstream, then compile it into the native pmap.o and relink
    upstream_root = out/'patch-check/upstream'
    (upstream_root/'osfmk/arm/pmap').mkdir(parents=True)
    shutil.copy2(XNU/'osfmk/arm/pmap/pmap.c', upstream_root/'osfmk/arm/pmap/pmap.c')
    apply_patch(PATCH_STUBS, upstream_root, 'patch 0001 upstream pmap.c')
    control = compile_pmap(out/'compile', patched=False)
    patched = compile_pmap(out/'compile', patched=True)
    original_symbols = external_symbols(control['original_object'])
    control_symbols = external_symbols(control['object'])
    patched_symbols = external_symbols(patched['object'])
    check('control compile reproduces the original pmap.o external symbols', control_symbols == original_symbols)
    check('control compile used the original headers', control['depfile_matches_original'])
    check('patched pmap.o adds exactly the two stubs', patched_symbols - control_symbols == {'T '+n for n in STUBBED} and not control_symbols - patched_symbols,
          sorted(patched_symbols ^ control_symbols))
    check('control compile: __TEXT,__text byte-identical to the STR-023 pmap.o', text_words(control['object']) == text_words(control['original_object']))
    words, addresses = text_words(patched['object']), symbol_addresses(patched['object'])
    # AArch64: 52800000 = mov w0, #0; d65f03c0 = ret. Both stubs must return 0 (false) and do nothing else.
    bodies = {n: [words.get(addresses[n]), words.get(addresses[n]+4)] for n in STUBBED}
    check('stub machine code returns 0 and nothing else', all(b == ['52800000', 'd65f03c0'] for b in bodies.values()), bodies)
    patched['stub_words'] = bodies
    report['compile'] = dict(control=control, patched=patched)
    relinked, link = relink(out/'relink', patched['object'])
    report['relink'] = link
    before_image, after_image = macho_summary(KERNEL), macho_summary(relinked)
    report['images'] = dict(str041=dict(before_image, sha256=KERNEL_SHA256), relinked=dict(after_image, sha256=sha(relinked)))
    check('relinked image keeps segment order and type', before_image['segments'] == after_image['segments'] and after_image['filetype'] == 2 and after_image['cputype'] == '0x100000c')
    check('relinked image has no undefined symbols', not run('nm -u', [str(TOOLS)+'nm', '-u', relinked])[1].strip())
    relinked_symbols = external_symbols(relinked)
    names_of = lambda lines: {line.split()[-1] for line in lines}
    defined_of = lambda lines: {line.split()[-1] for line in lines if line.split()[0] != 'U'}
    check('relinked image exports exactly the STR-041 set plus the two stubs, defined',
          names_of(relinked_symbols) - names_of(image) == set(STUBBED) and not names_of(image) - names_of(relinked_symbols)
          and set(STUBBED) <= defined_of(relinked_symbols), sorted(relinked_symbols ^ image))

    # 5b. RELEASE arm64 adds -exported_symbols_list all-kpi.exp (makedefs/MakeInc.def:811-812). Same DEVELOPMENT objects:
    #     this tests only how ld64 resolves the export list, not a RELEASE kernel.
    (out/'kpi').mkdir()
    genuine_exp, profile_exp = kpi_exp(genuine, out/'kpi/genuine-all-kpi.exp'), kpi_exp(profile, out/'kpi/profile-all-kpi.exp')
    check('all-kpi.exp from the genuine lists = STR-041 bytes', sha(genuine_exp) == sha(LINK/'kernel/all-kpi.exp'))
    _, release_genuine = relink(out/'release-style-genuine', patched['object'], ['-Wl,-exported_symbols_list,'+str(genuine_exp)], check=False)
    release_kernel, release_profile = relink(out/'release-style-profile', patched['object'], ['-Wl,-exported_symbols_list,'+str(profile_exp)], check=False)
    report['release_style_links'] = dict(genuine=release_genuine, profile=release_profile)
    check('RELEASE-style link, genuine lists: fails on exactly the 35, referenced only by the export list',
          release_genuine['exit_code'] != 0 and sorted(release_genuine['undefined']) == sorted(dropped)
          and set(release_genuine['undefined'].values()) == {'-exported_symbol[s_list] command line option'}, release_genuine['stderr'])
    check('RELEASE-style link, profile lists: links with no undefined symbol',
          release_profile['exit_code'] == 0 and not release_profile['undefined'] and not run('nm -u', [str(TOOLS)+'nm', '-u', release_kernel])[1].strip(),
          release_profile['stderr'])

    # 6. the genuine tool
    tool, tool_info = build_kextsymboltool(out/'kextsymboltool')
    report['kextsymboltool'] = tool_info
    demangled_to_symbol = {v: k for k, v in demangled.items()}
    kernels = {'str041': KERNEL, 'relinked': relinked}
    imports = {}
    for label, kernel in kernels.items():
        imports[label] = out/f'allsymbols.{label}'
        allsymbols(kernel, imports[label])
    matrix = {}
    for label in kernels:
        for exports, directory in [('genuine', genuine), ('profile', profile)]:
            matrix[f'{label}+{exports}'] = check_all_exports(tool, imports[label], directory, demangled_to_symbol, out/f'check/{label}-{exports}')
    report['check_all_exports'] = matrix
    fd = os.open('/dev/null', os.O_WRONLY)
    devnull_seek = os.lseek(fd, 4096, os.SEEK_SET)
    os.close(fd)
    literal = check_all_exports(tool, imports['relinked'], profile, demangled_to_symbol, out/'check/relinked-profile-devnull', output='/dev/null')
    report['devnull_control'] = dict(lseek_4096_returns=devnull_seek, passes=literal)
    check('host control: literal -output /dev/null fails only in seekFile, with no missing name',
          devnull_seek == 0 and all(r['exit_code'] == 1 and not r['missing'] and "couldn't write output" in r['stderr_tail'] for r in literal.values()))
    expect = {'str041+genuine': names, 'str041+profile': STUBBED, 'relinked+genuine': dropped, 'relinked+profile': []}
    for key, missing in expect.items():
        result = matrix[key]
        ok = result['without-Private']['exit_code'] == 0 and result['without-Private']['missing'] == [] and \
            result['without-Unsupported']['missing'] == sorted(missing) and (result['without-Unsupported']['exit_code'] == 0) == (not missing)
        check(f'check_all_exports {key}: second pass misses exactly {len(missing)}', ok,
              {p: (r['exit_code'], len(r['missing'])) for p, r in result.items()})
    report['symbol_sets'] = {'str041+genuine': symbol_sets(tool, imports['str041'], genuine, out/'symbolsets/str041-genuine'),
                             'relinked+profile': symbol_sets(tool, imports['relinked'], profile, out/'symbolsets/relinked-profile')}
    check('genuine lists: only the Private symbol set fails, on all 37',
          all((r['exit_code'] == 0) == (c != 'Private') for c, r in report['symbol_sets']['str041+genuine'].items()) and
          report['symbol_sets']['str041+genuine']['Private']['missing'] == 37)
    check('profile + stubs: all seven symbol sets build', all(r['exit_code'] == 0 for r in report['symbol_sets']['relinked+profile'].values()))
    if args.guest_kernel:
        guest = out/'allsymbols.guest'
        allsymbols(Path(args.guest_kernel), guest)
        guest_report = dict(kernel=args.guest_kernel, sha256=sha(args.guest_kernel),
                            genuine=check_all_exports(tool, guest, genuine, demangled_to_symbol, out/'check/guest-genuine'),
                            profile=check_all_exports(tool, guest, profile, demangled_to_symbol, out/'check/guest-profile'))
        for key in ('genuine', 'profile'):
            missing = guest_report[key]['without-Unsupported']['missing'] + guest_report[key]['without-Private']['missing']
            guest_report[key+'_summary'] = dict(of_the_37=sorted(set(missing) & set(names)), others=sorted(set(missing) - set(names)))
        report['guest'] = guest_report

    report['rows'] = rows
    report['checks'] = checks
    report['commands'] = COMMANDS
    report['outcome'] = 'pass' if all(c['ok'] for c in checks.values()) else 'fail'
    report['finished_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
    path = out/'report.json'
    path.write_text(json.dumps(report, indent=1)+'\n')
    failed = [k for k, v in checks.items() if not v['ok']]
    print(json.dumps(dict(outcome=report['outcome'], checks=len(checks), failed=failed, report=str(path), sha256=sha(path)), indent=1))
    return 0 if not failed else 1


if __name__ == '__main__':
    raise SystemExit(main())
