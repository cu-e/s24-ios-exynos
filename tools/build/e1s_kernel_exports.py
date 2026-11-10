#!/usr/bin/env python3
"""KRN-043: the canonical export-checked E1S DEVELOPMENT kernel and its KPI set.

In a fresh artifacts/e1s-kernel-exports/RUN directory this:
  1. checks the pins and the STR-041 kernel, compile plan, pmap.c and patch hashes;
  2. applies KRN-041 0001 to the native pmap.c and compiles it under the recorded
     STR-023 recipe, adding only -ffile-prefix-map=RUN=/krn043 so the object does
     not embed the run directory;
  3. relinks the STR-041 link with that pmap.o, nothing else changed;
  4. applies KRN-041 0002 to Private.arm64.exports and generates all-kpi.exp;
  5. builds the genuine kextsymboltool and runs both check_all_exports passes and
     the seven per-component symbol sets against the relinked kernel;
  6. publishes kernel, export lists, all-kpi.exp, symbol sets and manifest.json
     under RUN/kpi-set.

The KRN-041 helpers are reused unchanged from docs/procedures/krn-041. Nothing
is booted, packaged or sent to a device. --compare OTHER_RUN checks that two
runs published byte-identical manifests.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import sys

MAIN = Path(__file__).resolve().parents[2]
HELPERS = MAIN/'docs/procedures/krn-041/missing_exports.py'
OUT_ROOT = MAIN/'artifacts/e1s-kernel-exports'
PREFIX = '/krn043'
RUN003_PATCHED_PMAP = MAIN/'artifacts/krn-041/run-003/compile/patched/pmap.o'


def load_helpers():
    spec = importlib.util.spec_from_file_location('krn041_missing_exports', HELPERS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def compile_patched_pmap(me, out):
    """me.compile_pmap(patched=True) plus one flag: the source prefix map."""
    plan = json.loads(me.COMPILE_PLAN.read_text())
    command = next(c for c in plan['commands'] if c['id'] == 'osfmk/pmap.o')
    me.require(command['source_sha256'] == me.PMAP_SOURCE_SHA256 == me.sha(command['source']), 'pmap.c source drifted')
    tree = out/'patched'
    (tree/'osfmk/arm/pmap').mkdir(parents=True)
    source = tree/'osfmk/arm/pmap/pmap.c'
    shutil.copy2(command['source'], source)
    me.apply_patch(me.PATCH_STUBS, tree, 'patch 0001 native pmap.c')
    cwd = out/'cwd'
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
    me.require(changed == 3, 'Expected to change exactly source, object and depfile')
    added = [f'-ffile-prefix-map={out}={PREFIX}']
    argv[1:1] = added
    home = out/'home'
    home.mkdir()
    me.run('compile pmap.o patched+prefix-map', argv, cwd=cwd, env=dict(HOME=str(home), TMPDIR=str(home)), timeout=1200)
    deps = Path(depfile).read_text().replace('\\\n', ' ').split()
    deps = sorted({d.replace(str(cwd), command['cwd']).replace(str(source), command['source']) for d in deps if not d.endswith(':')})
    original = sorted({d for d in Path(command['depfile']).read_text().replace('\\\n', ' ').split() if not d.endswith(':')})
    return obj, dict(object_sha256=me.sha(obj), source_sha256=me.sha(source), recipe=command['recipe'], added_flags=added,
                     depfile_matches_original=deps == original, embeds_run_directory=str(out).encode() in obj.read_bytes())


def manifest(directory):
    return {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(directory.rglob('*')) if p.is_file() and p.name != 'manifest.json'}


def build(run):
    me = load_helpers()
    out = OUT_ROOT/run
    out.mkdir(parents=True, exist_ok=False)
    checks, report = {}, dict(schema=1, task='KRN-043', run=run, started_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                              helpers=dict(path=str(HELPERS.relative_to(MAIN)), sha256=me.sha(HELPERS)), kernel_booted=False, device_used=False)

    def check(name, condition, detail=None):
        checks[name] = dict(ok=bool(condition), detail=detail)

    try:
        report['pins'] = {}
        for source_id, (path, expected) in me.PINS.items():
            head = me.git(path, 'rev-parse', 'HEAD').strip()
            report['pins'][source_id] = head
            check('pin '+source_id, head == expected, head)
        check('STR-041 kernel unchanged', me.sha(me.KERNEL) == me.KERNEL_SHA256)
        report['patches'] = {p.name: me.sha(p) for p in (me.PATCH_STUBS, me.PATCH_PROFILE)}

        # 2-3. patched pmap.o with the prefix map, then one relink
        pmap, compiled = compile_patched_pmap(me, out/'compile')
        report['compile'] = compiled
        check('pmap.o does not embed the run directory', not compiled['embeds_run_directory'])
        check('pmap.o used the original headers', compiled['depfile_matches_original'])
        words, addresses = me.text_words(pmap), me.symbol_addresses(pmap)
        bodies = {n: [words.get(addresses[n]), words.get(addresses[n]+4)] for n in me.STUBBED}
        check('stub machine code is mov w0,#0; ret', all(b == ['52800000', 'd65f03c0'] for b in bodies.values()), bodies)
        if RUN003_PATCHED_PMAP.is_file():
            check('pmap.o __text identical to KRN-041 run-003 patched object', words == me.text_words(RUN003_PATCHED_PMAP))
        else:
            check('pmap.o __text identical to KRN-041 run-003 patched object', False, 'run-003 object not present')
        kernel, link = me.relink(out/'relink', str(pmap))
        report['relink'] = link
        check('relink exit 0', link['exit_code'] == 0, link['stderr'])
        check('relinked kernel has no undefined symbols', not me.run('nm -u', [str(me.TOOLS)+'nm', '-u', kernel])[1].strip())
        summary, original = me.macho_summary(kernel), me.macho_summary(me.KERNEL)
        check('segment order and type kept', summary['segments'] == original['segments'] and summary['filetype'] == 2 and summary['cputype'] == '0x100000c')
        names = lambda lines: {line.split()[-1] for line in lines}
        before, after = me.external_symbols(me.KERNEL), me.external_symbols(kernel)
        check('exports = STR-041 set plus the two stubs', names(after) - names(before) == set(me.STUBBED) and not names(before) - names(after))

        # 4. export lists and all-kpi.exp
        files = [f'{c}.exports' for c in me.COMPONENTS] + [f'{c}.arm64.exports' for c in me.COMPONENTS]
        profile = out/'exports'
        profile.mkdir()
        for f in files:
            shutil.copy2(me.XNU/'config'/f, profile/f)
        root = out/'profile-root'
        (root/'config').mkdir(parents=True)
        shutil.copy2(me.XNU/'config/Private.arm64.exports', root/'config/Private.arm64.exports')
        me.apply_patch(me.PATCH_PROFILE, root, 'patch 0002 export profile')
        shutil.copy2(root/'config/Private.arm64.exports', profile/'Private.arm64.exports')
        removed = set((me.XNU/'config/Private.arm64.exports').read_text().splitlines()) - set((profile/'Private.arm64.exports').read_text().splitlines())
        check('0002 removes 35 names', len(removed) == 35, len(removed))
        (out/'kpi').mkdir()
        kpi = me.kpi_exp(profile, out/'kpi/all-kpi.exp')

        # 5. genuine tool
        tool, tool_info = me.build_kextsymboltool(out/'kextsymboltool')
        report['kextsymboltool'] = tool_info
        imports = out/'allsymbols'
        me.allsymbols(kernel, imports)
        passes = me.check_all_exports(tool, imports, profile, {}, out/'check')
        report['check_all_exports'] = passes
        check('check_all_exports: both passes exit 0 with nothing missing', all(p['exit_code'] == 0 and not p['missing'] for p in passes.values()),
              {k: (v['exit_code'], len(v['missing'])) for k, v in passes.items()})
        sets = me.symbol_sets(tool, imports, profile, out/'symbolsets')
        report['symbol_sets'] = sets
        check('all seven symbol sets build', len(sets) == 7 and all(r['exit_code'] == 0 for r in sets.values()))

        # 6. publish
        kpi_set = out/'kpi-set'
        (kpi_set/'exports').mkdir(parents=True)
        shutil.copy2(kernel, kpi_set/'kernel.unstripped')
        shutil.copy2(kpi, kpi_set/'all-kpi.exp')
        for f in files:
            shutil.copy2(profile/f, kpi_set/'exports'/f)
        shutil.copytree(out/'symbolsets', kpi_set/'symbolsets')
        published = manifest(kpi_set)
        (kpi_set/'manifest.json').write_text(json.dumps(published, indent=1, sort_keys=True)+'\n')
        report['manifest'] = published
        report['kernel'] = dict(summary, sha256=published['kernel.unstripped'])
    except Exception as error:  # keep what happened
        report['error'] = f'{type(error).__name__}: {error}'
    report['checks'] = checks
    report['commands'] = me.COMMANDS
    report['outcome'] = 'pass' if checks and all(c['ok'] for c in checks.values()) and 'error' not in report else 'fail'
    report['finished_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
    (out/'report.json').write_text(json.dumps(report, indent=1)+'\n')
    failed = [k for k, v in checks.items() if not v['ok']]
    print(json.dumps(dict(outcome=report['outcome'], checks=len(checks), failed=failed, error=report.get('error'),
                          kernel=report.get('kernel', {}).get('sha256'), report=str(out/'report.json')), indent=1))
    return 0 if report['outcome'] == 'pass' else 1


def compare(run, other):
    a, b = (json.loads((OUT_ROOT/r/'kpi-set/manifest.json').read_text()) for r in (run, other))
    differ = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
    print(json.dumps(dict(runs=[run, other], files=len(a), identical=not differ, differ=differ), indent=1))
    return 0 if not differ else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    parser.add_argument('--compare', help='compare the published manifest of --run with this run; builds nothing')
    args = parser.parse_args()
    for name in filter(None, (args.run, args.compare)):
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', name):
            raise SystemExit('Invalid run name')
    return compare(args.run, args.compare) if args.compare else build(args.run)


if __name__ == '__main__':
    sys.exit(main())
