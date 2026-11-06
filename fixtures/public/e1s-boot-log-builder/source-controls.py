#!/usr/bin/env python3
"""Exercise the exact new Python hook on owned source copies; never compile."""
import argparse
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--donor',type=Path,required=True)
    p.add_argument('--patch',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    tree=ast.parse(args.candidate.read_text());build=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='build')
    report=next(n.value for n in build.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='report' for t in n.targets))
    metadata=ast.literal_eval(next(v for k,v in zip(report.keys,report.values) if isinstance(k,ast.Constant) and k.value=='boot_log_source_patch'))
    trial=next(n for n in build.body if isinstance(n,ast.Try))
    begin=next(i for i,n in enumerate(trial.body) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='log_patch' for t in n.targets))
    end=next(i for i,n in enumerate(trial.body[begin:],begin) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='products' for t in n.targets))
    nodes=trial.body[begin:end]
    code=compile(ast.Module(body=nodes,type_ignores=[]),str(args.candidate),'exec')
    segment='\n'.join(ast.get_source_segment(args.candidate.read_text(),n) for n in nodes)
    spec=importlib.util.spec_from_file_location('actual_e1s_log_hook_candidate',args.candidate)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    assert sha(args.patch)==metadata['expected_sha256']
    for relative,digest in metadata['expected_preimages'].items(): assert sha(args.baseline/relative)==digest
    result=[]
    cases=[('actual-source-hook',None,None),('missing-RAM-overlay','missing_ram','must precede'),
           ('missing-framebuffer-overlay','missing_fb','must precede'),
           ('changed-log-patch','patch','patch identity changed'),
           ('changed-loader-preimage','preimage','preimage/order changed'),
           ('omitted-framebuffer-body','body','preimage/order changed'),
           ('changed-postimage','postimage','postimage changed'),
           ('source-race-at-apply','race','Command failed')]
    for name,fault,expected in cases:
        case=args.out/name;case.mkdir();work=case/'source';directory=case/'run';directory.mkdir()
        for relative in metadata['expected_preimages']:
            target=work/relative;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(args.baseline/relative,target)
        patch=case/metadata['path'];patch.parent.mkdir(parents=True);shutil.copyfile(args.patch,patch)
        if fault=='patch':patch.write_bytes(patch.read_bytes()+b'\n')
        if fault=='preimage':
            file=work/'shim/e1s-xnu/loader.c';file.write_bytes(file.read_bytes()+b'\n')
        if fault=='body':shutil.copyfile(args.donor/'shim/e1s-xnu/ui.c',work/'shim/e1s-xnu/ui.c')
        commands=[]
        def actual_run(argv,cwd,log):
            assert list(map(str,argv))[:2]==['git','apply'],'control cannot invoke a compiler/target tool'
            if fault=='race' and '--check' in argv:
                file=work/'shim/e1s-xnu/loader.c';file.write_text('deliberately invalid source input\n')
            value=module.run(argv,cwd,log)
            if fault=='postimage' and '--check' not in argv:
                file=work/'shim/e1s-xnu/loader.c';file.write_bytes(file.read_bytes()+b'\n')
            return value
        state={'report':{'boot_log_source_patch':copy.deepcopy(metadata)},'patch':{'applied':fault!='missing_ram'},
               'display_patch':{'applied':fault!='missing_fb'},'root':case,'directory':directory,'work':work,
               'commands':commands,'hashlib':hashlib,'run':actual_run}
        error=None
        try:exec(code,state)
        except RuntimeError as problem:error=str(problem)
        if expected:
            assert error and expected in error,(name,error)
            assert not state['report']['boot_log_source_patch']['applied']
        else:
            assert not error and state['report']['boot_log_source_patch']['applied']
            assert len(commands)==2 and all(c['exit_code']==0 for c in commands)
            for rel,digest in metadata['expected_postimages'].items():assert sha(work/rel)==digest
        result.append(dict(id=name,outcome='expected-rejected' if expected else 'source-hook-pass',
                           error=error,commands=commands,target_or_compiler_executed=False))
    evidence=dict(kind='host-test',origin='local-host',outcome='pass',source_controls=len(result),
                  exact_hook_source_sha256=hashlib.sha256(segment.encode()).hexdigest(),
                  candidate_sha256=sha(args.candidate),cases=result,target_or_compiler_executed=False,
                  limitations=['Actual Python hook and Git patch operations only; no valid target or C behavior credit.'])
    (args.out/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps(dict(outcome='pass',source_controls=len(result),compiler_executed=False)))

if __name__=='__main__':main()
