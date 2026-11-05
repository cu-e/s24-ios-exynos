#!/usr/bin/env python3
"""Read-only independent MISC-001 source provenance reproduction."""
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import sys

HERE = Path(__file__).resolve().parent
WT = HERE.parents[2]
MAIN = WT.parents[1]
IMPL = MAIN/'worktrees/misc-001-20261105'
SRC = IMPL/'src/platform/misc'
TIP = 'bf54dcdc4a92111f20b7a05b6ba435b2674d8251'
OUT = WT/'artifacts/rev-misc-001'/sys.argv[1]
OUT.mkdir(parents=True,exist_ok=False)
ENV = dict(os.environ,GIT_NO_LAZY_FETCH='1',GIT_OPTIONAL_LOCKS='0',PYTHONDONTWRITEBYTECODE='1')
commands, checks = [], []
resource.setrlimit(resource.RLIMIT_CORE,(0,0))

def sha(p):
    with Path(p).open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()

def rel(p):
    return str(Path(p).relative_to(MAIN))

def run(label,argv,codes=(0,)):
    argv = [str(a) for a in argv]
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    p = subprocess.run(argv,cwd=WT,env=ENV,capture_output=True,timeout=45)
    stdout,stderr = OUT/(label+'.stdout'),OUT/(label+'.stderr')
    stdout.write_bytes(p.stdout); stderr.write_bytes(p.stderr)
    commands.append(dict(argv=argv,cwd=str(WT),started_at=started,
       ended_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),exit_code=p.returncode,
       stdout=rel(stdout),stderr=rel(stderr),timed_out=False,
       environment={'GIT_NO_LAZY_FETCH':'1','GIT_OPTIONAL_LOCKS':'0','PYTHONDONTWRITEBYTECODE':'1'}))
    assert p.returncode in codes,(label,p.returncode,p.stderr.decode(errors='replace'))
    return p.stdout

def passed(name,**kw):
    checks.append(dict(name=name,pass_check=True,**kw))

report = dict(kind='source-review',origin='local-host',outcome='fail',commit=TIP,
   recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),commands=commands,
   checks=checks,device_executed=False,native_qualified=False,
   summary='Independent exact MISC-001 source specification and provenance review')
try:
    assert run('implementation-head',['git','-C',IMPL,'rev-parse','HEAD']).decode().strip() == TIP
    assert not run('implementation-clean',['git','-C',IMPL,'status','--porcelain','--untracked-files=no'])
    report['review_base_commit'] = run('review-base',['git','rev-parse','HEAD']).decode().strip()
    run('python-version',[sys.executable,'--version']); run('git-version',['git','--version'])
    report['tool_sha256'] = {str(Path(sys.executable).resolve()):sha(Path(sys.executable).resolve()),
       '/usr/bin/git':sha('/usr/bin/git')}
    manifest = json.loads((SRC/'sources.json').read_text())
    repo,comparison = MAIN/'references/s24-linux',MAIN/'references/s24-bsp-reference'
    args = [sys.executable,SRC/'check_sources.py','--repo',repo,'--comparison-repo',comparison]
    original = json.loads(run('original-checker',[*args,'--negative-controls']))
    assert original['files_verified'] == 22 and original['anchors_verified'] == 81
    assert len(original['negative_controls']) == 7 and all(x['rejected'] for x in original['negative_controls'])
    passed('actual-original-checker-22-files-81-anchors-seven-controls')
    counts = {'same':0,'different':0}; source_records = []; texts = {}
    for i,item in enumerate(manifest['files']):
        data = run(f'current-{i:02d}',['git','-C',repo,'cat-file','blob',manifest['source']['revision']+':'+item['path']])
        old = run(f'comparison-{i:02d}',['git','-C',comparison,'cat-file','blob',manifest['source']['comparison_revision']+':'+item['path']])
        assert len(data) == item['bytes'] and hashlib.sha256(data).hexdigest() == item['sha256']
        assert hashlib.sha256(old).hexdigest() == item['comparison_sha256']
        status = 'same' if old == data else 'different'
        assert status == item['comparison_status']; counts[status] += 1
        text = data.decode(); texts[item['path']] = text
        for anchor in item['anchors']:
            assert anchor['text'] in text.splitlines()[anchor['line']-1]
        source_records.append(dict(path=item['path'],artifact=rel(OUT/f'current-{i:02d}.stdout'),
                                   sha256=hashlib.sha256(data).hexdigest(),comparison=status))
    assert counts == {'same':16,'different':6}
    report['source_records'] = source_records
    passed('independent-full-Git-blob-hash-anchor-comparison',classification=counts)
    old_evidence_path = IMPL/'artifacts/misc-001/2026-11-05-source-audit/evidence.json'
    old = json.loads(old_evidence_path.read_text())
    assert old['commit'] == TIP
    for p,digest in old['hashes'].items():
        assert sha(MAIN/p) == digest,p
    prior_checks = json.loads((IMPL/'artifacts/misc-001/2026-11-05-source-audit/checks.json').read_text())
    for p,digest in prior_checks['source_files'].items():
        assert sha(IMPL/p) == digest,p
        committed = run('committed-'+Path(p).name.replace('.','-'),['git','-C',IMPL,'cat-file','blob',TIP+':'+p])
        assert hashlib.sha256(committed).hexdigest() == digest
    report['original_evidence_sha256'] = sha(old_evidence_path)
    passed('original-evidence-artifact-hashes-and-precommit-source-binding',artifacts=len(old['hashes']))
    mutations = {}
    def mutated(name,fn):
        m = copy.deepcopy(manifest); fn(m); mutations[name] = m
    mutated('duplicate-path',lambda m:m['files'].append(copy.deepcopy(m['files'][0])))
    mutated('absolute-path',lambda m:m['files'][0].update(path='/tmp/outside'))
    mutated('dot-segment',lambda m:m['files'][0].update(path='arch/./arm64/configs/e1s_defconfig'))
    mutated('zero-anchor-line',lambda m:m['files'][0]['anchors'][0].update(line=0))
    mutated('bool-anchor-line',lambda m:m['files'][0]['anchors'][0].update(line=True))
    mutated('empty-anchor-list',lambda m:m['files'][0].update(anchors=[]))
    mutated('wrong-byte-size',lambda m:m['files'][0].update(bytes=m['files'][0]['bytes']+1))
    mutated('wrong-classification',lambda m:m['files'][0].update(comparison_status='same'))
    mutated('missing-commit',lambda m:m['source'].update(revision='0'*40))
    mutated('missing-native-flag',lambda m:m.pop('native_qualified'))
    mutated('numeric-native-flag',lambda m:m.update(native_qualified=0))
    mutated('empty-file-list',lambda m:m.update(files=[]))
    controls = []
    for name,m in mutations.items():
        path = OUT/(name+'.json'); path.write_text(json.dumps(m))
        result = json.loads(run('reject-'+name,[*args,'--manifest',path],codes=(1,)))
        assert result['outcome'] == 'fail' and result['native_qualified'] is False
        controls.append(dict(control=name,rejected=True,error=result['error']))
    passed('twelve-additional-real-checker-rejection-controls',controls=controls)
    # Independent full-file contextual checks supplement the manifest anchors.
    nfc = texts['drivers/nfc/lsi/sec_nfc.c']; header = texts['drivers/nfc/lsi/sec_nfc.h']
    ioctl = nfc[nfc.index('static long sec_nfc_ioctl'):]
    ioctl = ioctl[:ioctl.index('static const struct file_operations')]
    assert 'unsigned int new = (unsigned int)arg;' in ioctl
    assert 'case SEC_NFC_GET_MODE:' not in ioctl and 'case SEC_NFC_SET_MODE:' in ioctl
    assert 'SEC_NFC_SHUTDOWN' not in header and 'SEC_NFC_SHUTDOWN' in texts['drivers/nfc/samsung/sec_nfc.h']
    assert 'defined(CONFIG_FINGERPRINT_SECURE) && !defined(CONFIG_SEC_FACTORY)' in texts['drivers/fingerprint/fingerprint.h']
    assert '#if defined(CONFIG_SEC_FACTORY) || !1' in texts['arch/arm64/boot/dts/samsung/fingerprint_qfs4008.dtsi']
    assert 'plz modify after implementation' in texts['arch/arm64/boot/dts/samsung/e1s/s5e9945-e1s_common.dtsi']
    assert 'dma_bit_mask = <36>;' in texts['arch/arm64/boot/dts/exynos/s5e9945-mfc.dtsi']
    passed('independent-context-checks-NFC-ioctl-biometric-gates-DP-warning-MFC-DMA')
    report['outcome'] = 'pass'
except Exception as error:
    report['error'] = repr(error)
finally:
    report['source_sha256'] = {str(p):sha(p) for p in sorted(SRC.iterdir()) if p.is_file()}
    report['review_runner_sha256'] = sha(__file__)
    report['max_child_rss_kib'] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    report['limitations'] = ['Source-object provenance and contextual review only; not DTS preprocessing or a complete vendor build.',
       'No native/firmware/secure-world/Apple compatibility qualification; no phone, ADB or peripheral operations.',
       'No compiler jobs, upstream script execution, shared reference hydration or implementation writes.']
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    files = sorted(p for p in OUT.iterdir() if p.is_file())
    evidence = {k:report[k] for k in ['kind','origin','outcome','commit','recorded_at','commands','summary','device_executed']}
    evidence.update(artifacts=[rel(p) for p in files],sha256={rel(p):sha(p) for p in files})
    (OUT/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps(dict(outcome=report['outcome'],checks=checks,error=report.get('error'),
       commands=len(commands),max_child_rss_kib=report['max_child_rss_kib'],evidence=rel(OUT/'evidence.json')),indent=2))
sys.exit(0 if report['outcome'] == 'pass' else 1)
