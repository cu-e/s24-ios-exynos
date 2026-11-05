#!/usr/bin/env python3
"""Build emulator-only instrumentation; unchanged target APK/key remain local."""
import argparse
from pathlib import Path
import json
import hashlib
import subprocess
import zipfile
import shutil
from datetime import datetime, timezone

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',required=True)
    p.add_argument('--target-build',type=Path,required=True)
    p.add_argument('--sdk',type=Path,default=Path('/home/egor/Android/Sdk'))
    args=p.parse_args()
    if not args.run.replace('-','').replace('_','').isalnum() or len(args.run)>80:raise ValueError('Invalid run')
    target=args.target_build.resolve()
    if not target.is_relative_to(ROOT/'artifacts'):raise ValueError('Target build must be a local project artifact')
    original=json.loads((target/'build-report.json').read_text());apk=target/'s24-vulkan-probe.apk'
    if hashlib.sha256(apk.read_bytes()).hexdigest()!=original['apk']['sha256']:raise ValueError('Target APK changed')
    key=target/'development.jks'
    if key.stat().st_mode&0o077:raise ValueError('Target development key must remain private')
    out=ROOT/'artifacts/android-probe'/args.run
    if out.resolve()!=out:raise ValueError('Run must not use symlinks')
    out.mkdir(parents=True,exist_ok=False);(out/'classes').mkdir();(out/'dex').mkdir()
    tools=args.sdk/'build-tools/35.0.0';jar=args.sdk/'platforms/android-35/android.jar'
    report=dict(kind='host-test',origin='local-host',outcome='inconclusive',recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),commands=[],target_apk_sha256=original['apk']['sha256'],source_sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [HERE/'Qualifier.java',HERE/'AndroidManifest.xml',Path(__file__)]})
    (out/'source').mkdir()
    for f in [HERE/'Qualifier.java',HERE/'AndroidManifest.xml',Path(__file__)]:shutil.copyfile(f,out/'source'/f.name)
    def run(argv):
        argv=[str(a) for a in argv];r=subprocess.run(argv,capture_output=True,text=True,timeout=60,cwd=ROOT)
        report['commands'].append(dict(argv=argv,exit_code=r.returncode,stdout=r.stdout,stderr=r.stderr))
        if r.returncode:raise RuntimeError(r.stderr)
    try:
        run(['javac','--release','8','-classpath',jar,'-d',out/'classes',HERE/'Qualifier.java'])
        run([tools/'d8','--lib',jar,'--min-api','29','--output',out/'dex',*sorted((out/'classes').rglob('*.class'))])
        run([tools/'aapt2','link','-o',out/'unsigned.apk','--manifest',HERE/'AndroidManifest.xml','-I',jar])
        with zipfile.ZipFile(out/'unsigned.apk','a',compression=zipfile.ZIP_STORED) as z:z.write(out/'dex/classes.dex','classes.dex')
        run([tools/'zipalign','-P','16','-f','4',out/'unsigned.apk',out/'aligned.apk'])
        run([tools/'apksigner','sign','--ks',key,'--ks-key-alias','development','--ks-pass','pass:android','--key-pass','pass:android','--out',out/'qualifier.apk',out/'aligned.apk'])
        run([tools/'apksigner','verify','--verbose',out/'qualifier.apk'])
        report.update(outcome='pass',apk_sha256=hashlib.sha256((out/'qualifier.apk').read_bytes()).hexdigest())
    except Exception as error:report.update(outcome='fail',error=str(error))
    (out/'build-report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report.get(k) for k in ['outcome','error','apk_sha256']},indent=2))
    return 0 if report['outcome']=='pass' else 1


if __name__=='__main__':raise SystemExit(main())
