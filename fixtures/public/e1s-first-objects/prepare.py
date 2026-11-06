#!/usr/bin/env python3
"""Stage source-matched E1S inputs and query genuine Make C_RULEs; never compile."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess


def sha(p):
    with Path(p).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def bound(p, digest):
    assert sha(p) == digest, str(p)
    return json.loads(p.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--main', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--only', choices=['pe_bootargs.o','pe_identify_machine.o'])
    a = parser.parse_args(); m = a.main.resolve(); out = a.out.absolute()
    assert out == out.resolve() and not out.exists()
    parent = m/'worktrees/str-004-e1s-profile-20261106'
    descriptor_path = parent/'fixtures/public/e1s-profile/generated-development.json'
    descriptor = bound(descriptor_path, '4b7e2c665daa36bfe2ae2c4984b2900340b796f0b5e2f884d363cd361e2c210d')
    source = Path(descriptor['source_root'])
    manifest_path = source.parent/'prepared-source-manifest.json'
    manifest = bound(manifest_path, 'f884bf7fa08afdffd2f4ba0840ae44d666f1b9848700aaa8f5f88e4dcbe42ba2')
    raw_path = Path(descriptor['actual_raw'])
    raw = bound(raw_path, 'ed95a677c2392b9b893aad8e5d6c7d73b94814231ee3c7e3b5e0f1495ad41afc')
    proof_path = m/'worktrees/int-e1s-profile-20261106/artifacts/integration-gate/e1s-source-review-20261106/native-first-slice.json'
    proof = bound(proof_path, '9633755252cb27596ca59634c1991ca1a2e0d9a1e3816393d468a99e83b30ffc')
    assert descriptor['machine']=='E1S' and descriptor['kernel']=='DEVELOPMENT'
    assert raw['outcome']=='pass' and not raw['owned_survivors'] and len(raw['output_sha256'])==63
    compiler = m/'artifacts/xnu-compiler-cxx-storage/source-build-session2/clang'
    assert sha(compiler)=='7972eb2820ae25b5bedff1ea954cef9e9a0e4a15c7a8e440628e8b6540fafc82'
    # These already-qualified Linux query definitions contain no board/SDK flags.
    oldshim = m/'artifacts/xnu-kernel-objects/compile-session2/host-commands.mk'
    assert oldshim.read_text()=='''# Explicit standalone Linux query inputs; no SDK contents.
TR = tr
BASH = bash
ECHO = echo
PRINTF = printf
SUPPORTED_EMBEDDED_PLATFORMS = iPhoneOS AppleTVOS WatchOS tvOS BridgeOS
_v =
'''
    out.mkdir(parents=True)
    inputs = {str(p):sha(p) for p in [descriptor_path,manifest_path,raw_path,proof_path,compiler,oldshim,Path(__file__)]}
    copied = []
    for p, digest in raw['output_sha256'].items():
        p=Path(p); assert sha(p)==digest
        rel=p.relative_to(Path(descriptor['components'][p.parts[-3]]['root']).parents[1])
        target=out/'configuration'/rel
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
        assert sha(target)==digest;inputs[str(p)]=digest;inputs[str(target)]=digest
    exports = {}
    for unit in proof['units']:
        for row in unit['source_export_copy_map']:
            assert manifest[row['source']]==row['sha256']
            assert manifest[row['declaration']]==row['declaration_sha256']
            assert exports.setdefault(row['destination'],row)==row
    extra_path=Path(__file__).with_name('development-exports.json')
    extra=json.loads(extra_path.read_text());inputs[str(extra_path)]=sha(extra_path)
    for row in extra['rows']:
        assert manifest[row['source']]==row['sha256'] and manifest[row['declaration']]==row['declaration_sha256']
        declaration=(source/row['declaration']).read_text().replace('\\\n',' ')
        listed=re.findall(r'^'+row['list_variable']+r'\s*=\s*(.*)$',declaration,re.M)
        assert len(listed)==1 and Path(row['source']).name in shlex.split(listed[0])
        assert re.search(r'^EXPORT_'+row['export_kind']+r'_DIR\s*=\s*'+row['export_directory']+r'\s*$',declaration,re.M)
        assert row['source']=='osfmk/'+row['export_directory']+'/'+Path(row['source']).name
        assert row['destination']=='EXPORT_HDRS/'+row['source']
        assert exports.setdefault(row['destination'],row)==row
    for relative,row in exports.items():
        for rel,digest in [(row['source'],row['sha256']),(row['declaration'],row['declaration_sha256'])]:
            assert sha(source/rel)==digest;inputs[str(source/rel)]=digest
        target=out/relative;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source/row['source'],target);assert sha(target)==row['sha256'];inputs[str(target)]=row['sha256']
    # Preserve the genuine mandatory sanitizer setup rule and input order.
    san_make=source/'san/memory/Makefile'
    assert '$(SOURCE)/kasan-blacklist $(SOURCE)/ubsan-blacklist $(SOURCE)/kasan-blacklist-%' in san_make.read_text()
    inputs[str(san_make)]=sha(san_make)
    lists=[source/'san/memory'/n for n in ['kasan-blacklist','ubsan-blacklist','kasan-blacklist-arm64']]
    validator=source/'san/tools/validate_blacklist.sh'
    for file in [*lists,validator]:
        assert sha(file)==manifest[str(file.relative_to(source))];inputs[str(file)]=sha(file)
    blacklist=out/'san/kasan-blacklist-arm64';blacklist.parent.mkdir()
    sed=['/usr/bin/sed','-e','s,^src:\\./,src:'+str(source)+'/,',*[str(f) for f in lists]]
    generated=subprocess.run(sed,capture_output=True,timeout=10);assert generated.returncode==0
    blacklist.write_bytes(generated.stdout)
    checked=subprocess.run(['/bin/bash',str(validator),str(blacklist)],cwd=out,capture_output=True,timeout=10,env={'PATH':'/usr/bin:/bin'})
    (out/'blacklist-validation.log').write_bytes(checked.stdout+checked.stderr)
    assert checked.returncode==0,checked.stderr
    for file in [blacklist,Path('/usr/bin/sed').resolve(),Path('/bin/bash').resolve()]:inputs[str(file)]=sha(file)
    (out/'blacklist-commands.json').write_text(json.dumps([{'argv':sed,'exit_code':generated.returncode},{'argv':['/bin/bash',str(validator),str(blacklist)],'cwd':str(out),'env':{'PATH':'/usr/bin:/bin'},'exit_code':checked.returncode}],indent=2)+'\n')
    shim=out/'host-commands.mk';shutil.copyfile(oldshim,shim);inputs[str(shim)]=sha(shim)
    cfg=out/'configuration/pexpert/DEVELOPMENT';mk=cfg/'Makefile'
    text=mk.read_text();flags=re.findall(r'^export CONFIG_DEFINES = (.*)$',text,re.M);assert len(flags)==1
    assert '-DDEVELOPMENT' in shlex.split(flags[0]) and '-DMACH_ASSERT' in shlex.split(flags[0])
    # Native donor's existing BUILD_LTO=0 / BUILD_WERROR=0 policy, not a new repair.
    donor_build=m/'references/hakios-e1s-tools/xnu-build.sh'
    assert all(x in donor_build.read_text() for x in ['BUILD_LTO=0','BUILD_WERROR=0','ARCH_STRING_FOR_CURRENT_MACHINE_CONFIG=arm64'])
    inputs[str(donor_build)]=sha(donor_build)
    args=['SRCROOT='+str(source),'OBJROOT='+str(out),'OBJPATH='+str(out/'build'),'TARGET='+str(cfg),
          'SOURCE='+str(source/'pexpert')+'/', 'RELATIVE_SOURCE_PATH=pexpert',
          'CURRENT_ARCH_CONFIG=ARM64','CURRENT_ARCH_CONFIG_LC=arm64',
          'CURRENT_KERNEL_CONFIG=DEVELOPMENT','CURRENT_KERNEL_CONFIG_LC=development',
          'CURRENT_MACHINE_CONFIG=E1S','CURRENT_MACHINE_CONFIG_LC=e1s','PLATFORM=iPhoneOS',
          'SDKROOT='+str(out/'unavailable-sdk'),'CC='+str(compiler),'CXX='+str(compiler),
          'MakeInc_cmd='+str(shim),'ARCH_STRING_FOR_CURRENT_MACHINE_CONFIG=arm64',
          'BUILD_WERROR=0','BUILD_LTO=0','DEPLOYMENT_TARGET_FLAGS=-target arm64-apple-ios16.5 -DXNU_TARGET_OS_IOS',
          'SEED_DEFINES=-DXNU_NO_TYPE_BUILTINS=0','SHELL=/bin/bash','LOGCOLORS=n','CONFIG_DEFINES='+flags[0]]
    recipes={};current=None
    for line in text.splitlines():
        match=re.match(r'^([^\s:]+\.o):',line)
        if match:current=match[1]
        if current in ['pe_bootargs.o','pe_identify_machine.o'] and re.match(r'^\s*\$[({]C_RULE_1A',line):recipes[current]=line.strip()
    assert len(recipes)==2
    query=out/'query-pexpert.mk'
    extra=''
    for target,recipe in recipes.items():
        name=target[:-1]+'c';recipe=re.sub(r'\$[({]C_RULE_1B[)}]',name,recipe)
        extra+='$(eval @ := '+target+')\n$(eval <F := '+name+')\n$(info E1SCMD|'+target+'|'+recipe+')\n'
    query.write_text('include '+str(mk)+'\n'+extra+'\n.PHONY: e1s_query\ne1s_query: ;\n')
    command=['make','--no-print-directory','-rR','-f',str(query),*args,'e1s_query']
    p=subprocess.run(command,cwd=cfg,capture_output=True,text=True,timeout=30)
    (out/'make-query.stdout.txt').write_text(p.stdout);(out/'make-query.stderr.txt').write_text(p.stderr)
    (out/'make-query-command.json').write_text(json.dumps({'argv':command,'cwd':str(cfg),'exit_code':p.returncode},indent=2)+'\n')
    assert p.returncode==0,p.stderr
    commands=[]
    for line in p.stdout.splitlines():
        if not line.startswith('E1SCMD|'):continue
        if a.only and line.split('|',2)[1]!=a.only:continue
        _,target,expanded=line.split('|',2);argv=shlex.split(expanded)
        assert argv[0]==str(compiler) and '-c' in argv and '-DARM64_BOARD_CONFIG_E1S' in argv
        assert not any('BCM2837' in word for word in argv)
        assert '-DDEVELOPMENT' in argv and '-DMACH_ASSERT' in argv
        src=source/'pexpert/arm'/target.replace('.o','.c');assert str(src) in argv
        assert sha(src)==manifest[str(src.relative_to(source))];inputs[str(src)]=sha(src)
        commands.append({'id':'pexpert/'+target,'argv':argv,'cwd':str(cfg),'object':str(cfg/target),
                         'depfile':str(cfg/target.replace('.o','.d')),'genuine_expanded_recipe':expanded})
    assert len(commands)==(1 if a.only else 2)
    if a.only:assert commands[0]['id']=='pexpert/'+a.only
    for p in [source/'makedefs/MakeInc.def',source/'makedefs/MakeInc.rule',source/'makedefs/MakeInc.cmd',query]:inputs[str(p)]=sha(p)
    for c in commands:assert not Path(c['object']).exists() and not Path(c['depfile']).exists()
    plan={'schema':'e1s-first-native-objects-plan-v1','task':'STR-007','owner':'codex-e1s-first-objects-20261106-sr7',
          'phase':'planned-not-compiled','source_root':str(source),'configuration':'DEVELOPMENT','machine':'E1S',
          'source_manifest_sha256':sha(manifest_path),'actual_config_raw_sha256':sha(raw_path),
          'source_exports':list(exports.values()),'copied_configurations':63,'commands':commands,
          'input_sha256':inputs,'max_jobs':1,'max_owned_rss_bytes':256*1024**2,'child_timeout_seconds':120,'whole_timeout_seconds':600,
          'native_donor_policy':{'BUILD_LTO':0,'BUILD_WERROR':0,'same_source_policy_as_actual_native_receipt':True},
          'SDK_provided':False,'SDKROOT_is_absent':not (out/'unavailable-sdk').exists(),'compiler_execution':False,'hardware_execution':False}
    if a.only:
        prior_path=Path(__file__).resolve().parents[3]/'docs/procedures/e1s-first-objects/actual-001-evidence.json'
        prior=json.loads(prior_path.read_text());product=prior['successful_product']
        assert prior['commands'][0]['exit_code']==0
        assert sha(product['path'])==product['sha256'] and sha(product['depfile'])==product['depfile_sha256']
        plan['previous_successful_product']={'path':product['path'],'sha256':product['sha256'],
            'depfile':product['depfile'],'depfile_sha256':product['depfile_sha256'],
            'actual_dependency_count':len(product['actual_dependencies']),
            'receipt':str(prior_path),'receipt_sha256':sha(prior_path),
            'recompiled':False}
        for path in [prior_path,Path(product['path']),Path(product['depfile'])]:inputs[str(path)]=sha(path)
    (out/'compile-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    print(json.dumps({'plan':str(out/'compile-plan.json'),'sha256':sha(out/'compile-plan.json'),'commands':len(commands),'exports':len(exports)}))


if __name__=='__main__':main()
