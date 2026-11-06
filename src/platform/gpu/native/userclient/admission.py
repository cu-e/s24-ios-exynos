#!/usr/bin/env python3
"""Plan/admit GPU's separate native and host phases; pending interfaces refuse."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
MAIN = ROOT.parent.parent
OWNER = "codex-gpu-userclient-20261106-eh"
PARENT = MAIN/"worktrees/gpu-012-current-20261106/artifacts/gpu-userclient/current-source-2/plan/plan.json"
PARENT_SHA = "a782839e46888e17e43acf17bd362971adea805eb1f36e091aa482417a0ee689"
POLICY_SHA = "df865b09a3aa883d5f6ea7ad4ca0c8485bf505c098e24fb0b511d091227f1add"
SCOPES = {"src/platform/gpu/native/userclient", "fixtures/public/gpu-userclient", "docs/procedures/gpu-userclient"}


class PendingInterface(ValueError):
    pass


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def path(value):
    result = Path(value).absolute()
    if result != result.resolve() or any(p.is_symlink() for p in [result, *result.parents]):
        raise ValueError("Canonical non-symlink ancestry required")
    return result


def load(filename, expected=None):
    filename = path(filename)
    fd = os.open(filename, os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if before.st_mode & 0o170000 != 0o100000:
            raise ValueError("Regular JSON input required")
        raw = stream.read(64*1024**2+1)
        after = os.fstat(stream.fileno())
    identity = lambda st: (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
    if len(raw)>64*1024**2 or identity(before)!=identity(after) or identity(after)!=identity(filename.stat()) or (expected and hashlib.sha256(raw).hexdigest()!=expected):
        raise ValueError("Changed or oversized same-byte JSON input")
    return json.loads(raw)


def module(item, name):
    filename = path(item["path"])
    with filename.open("rb") as stream:
        raw = stream.read(1024**2+1)
    if len(raw)>1024**2 or hashlib.sha256(raw).hexdigest()!=item["sha256"]:
        raise ValueError("Changed accepted executable Python boundary")
    result = ModuleType(name); result.__file__ = str(filename)
    exec(compile(raw, str(filename), "exec"), result.__dict__)
    return result


def policy():
    return load(ROOT/"fixtures/public/gpu-userclient/admission-policy.json", POLICY_SHA)


def authority(experiment):
    ledger = load(MAIN/"state/lab.json")
    task = next(t for t in ledger["tasks"] if t["id"]=="GPU-012")
    exp = next(e for e in ledger["experiments"] if e["id"]==experiment)
    if task["owner"]!=OWNER or task["status"]!="in_progress" or set(task["paths"])!=SCOPES:
        raise ValueError("Original active GPU owner/literal reservations required")
    if any(exp[k]!=v for k,v in [("task", "GPU-012"), ("owner", OWNER), ("status", "planned")]):
        raise ValueError("Original planned experiment required")


def owned_output(value):
    out = path(value); scope = ROOT/"artifacts/gpu-userclient"
    if not out.is_relative_to(scope) or out==scope or out.exists():
        raise ValueError("Fresh original GPU-owned output required")
    return out


def frozen_sources(parent):
    for name, digest in parent["source_freeze"]["files"].items():
        if sha(ROOT/name)!=digest or sha(Path(parent["source_freeze"]["worktree"])/name)!=digest:
            raise ValueError("Original provider/policy/fixture/dispatcher freeze changed")
    # Executable Python helpers cannot introduce a concrete kernel provider.
    expected = {str(ROOT/name) for name in parent["source_freeze"]["files"] if name.startswith("src/platform/gpu/native/userclient/")}
    actual = {str(p) for p in (ROOT/"src/platform/gpu/native/userclient").rglob("*") if p.is_file() and p.suffix in {".c", ".h", ".cpp", ".hpp", ".cc", ".cxx", ".mm"}}
    if actual!=expected:
        raise ValueError("Unreviewed native provider/type source added")


def commands(parent, phase, out):
    old = Path(parent["future_actual_output"])
    old_root = Path(parent["source_freeze"]["worktree"]).parent/"gpu-012-current-20261106"
    if phase=="native":
        result=[]
        for row in parent["target_commands"]:
            argv=list(row["argv"])
            source=ROOT/Path(row["source"]["path"]).relative_to(old_root)
            argv[argv.index(row["source"]["path"])]=str(source)
            argv[argv.index("-o")+1]=str(out/Path(row["object"]).name)
            argv[argv.index("-MF")+1]=str(out/Path(row["depfile"]).name)
            genuine=next(r for r in parent["genuine_recipes"] if r["id"]==row["derived_from"])
            template=genuine["next_owned_compile_argv_template"]
            permitted={template.index(genuine["bound_source"]),template.index("-o")+1,template.index("-MF")+1}
            if len(argv)!=len(template) or {i for i,(a,b) in enumerate(zip(argv,template)) if a!=b}!=permitted:
                raise ValueError("Native recipe changed outside source/object/dependency operands")
            result.append({"id":row["id"],"argv":argv,"cwd":row["cwd"],"timeout_seconds":120})
        return result
    if phase!="host-sanitizer": raise ValueError("Explicit separate native or host-sanitizer phase required")
    result=[]
    for i,row in enumerate(parent["prospective_host_commands"]):
        argv=[]
        for arg in row["argv"]:
            if arg.startswith(str(old_root)+"/"): arg=str(ROOT/Path(arg).relative_to(old_root))
            # Rewrite declared output operands after source-root relocation.
            relocated_old=ROOT/old.relative_to(old_root)
            if arg.startswith(str(relocated_old)+"/"): arg=str(out/Path(arg).relative_to(relocated_old))
            argv.append(arg)
        result.append({"id":["host-dispatcher","host-policy-link","host-policy-run"][i],"argv":argv,"cwd":str(out),"timeout_seconds":120})
    return result


def make_plan(phase, output, experiment):
    authority(experiment)
    out=owned_output(output)
    parent=load(PARENT,PARENT_SHA); frozen_sources(parent)
    spec=policy()
    return {"schema":"gpu-admission-plan-v1","resource_profile":"project-budget-v1","task":"GPU-012","owner":OWNER,
        "experiment":experiment,"shard":"gpu-userclient","phase":phase,"output":str(out),
        "parent_plan":{"path":str(PARENT),"sha256":PARENT_SHA},"policy_sha256":POLICY_SHA,
        "executor":{"path":str(Path(__file__).resolve()),"sha256":sha(__file__)},
        "launcher":{"path":str(ROOT/"src/platform/gpu/native/userclient/launcher.py"),"sha256":sha(ROOT/"src/platform/gpu/native/userclient/launcher.py")},
        "source_freeze":parent["source_freeze"],"commands":commands(parent,phase,out),"resource_contract":spec["resource_contract"],
        "native_inspector":parent["inspection_plan"]["tool"] if phase=="native" else None,
        "final_binding":spec["final_binding"],"execution_ready":False,"compiler_executed":False,"sanitizer_executed":False,
        "backend_ready":False,"hardware_result":False,"native_ABI_qualified":False}


def accepted_interface(spec, phase):
    binding=spec["final_binding"]
    if spec["execution_enabled"] is not True or binding is None:
        raise PendingInterface("Final accepted VM044/046 helper/profile and scoped input/runtime validator not pinned; no allocation or child")
    if binding["accepted"] is not True or binding["resource_profile"]!="project-budget-v1":
        raise PendingInterface("Final independent acceptance required")
    helper=module(binding["helper"],"gpu_final_helper")
    required="run_child" if phase=="native" else "run_child_rss_only"
    if not callable(getattr(helper,required,None)):
        raise PendingInterface("Accepted helper lacks required "+required+" interface; no fallback")
    validator=module(binding["input_validator"],"gpu_final_inputs")
    if not callable(getattr(validator,"validate",None)):
        raise PendingInterface("Accepted exact namespace/runtime input validator missing")
    return binding,helper,validator,required


def execute(plan_path, plan_sha, approval_path):
    proposed=load(plan_path,plan_sha)
    exact=make_plan(proposed["phase"],proposed["output"],proposed["experiment"])
    if proposed!=exact:
        raise ValueError("Source plan/argv/cwd/source/output/caller pins changed")
    binding,helper,validator,method=accepted_interface(policy(),exact["phase"])
    # No implementation of the future input/runtime validator is fabricated.
    # Its accepted exact source must bind complete namespace, tool ELF runtime,
    # output absence and all command inputs before reservation or child creation.
    if validator.validate(MAIN,exact,binding) is not True:
        raise ValueError("Final complete namespace/runtime validation refused")
    approval=helper.load_project(approval_path)
    args=SimpleNamespace(main=MAIN,out=Path(exact["output"]),task="GPU-012",owner=OWNER,experiment=exact["experiment"],shard="gpu-userclient")
    budget=helper.project_approval(args,approval,executor_path=__file__)
    if budget.source_plan!=proposed or approval["source_plan_sha256"]!=plan_sha:
        raise ValueError("Root slot does not bind exact source plan")
    if budget.rss_limit!=exact["resource_contract"]["max_owned_rss_bytes"]:
        raise ValueError("Root slot must match exact phase RSS contract")
    supervise=helper.supervisor(MAIN)
    if sha(MAIN/"tools/build/qemu_host.py")!=binding["supervisor_sha256"]:
        raise ValueError("Final accepted supervisor changed")
    budget.reserve()
    phase_record={"phase":exact["phase"],"outcome":"incomplete","hardware_result":False,"native_ABI_qualified":False}
    try:
        args.out.mkdir(parents=True,exist_ok=False)
        if exact["phase"]=="host-sanitizer": (args.out/"host").mkdir()
        for number,command in enumerate(exact["commands"]):
            if validator.validate(MAIN,exact,binding) is not True:
                raise ValueError("Inputs changed before next serial command")
            result=getattr(helper,method)(command["argv"],Path(command["cwd"]),args.out,"command-"+str(number),supervise,timeout=120,budget=budget)
            (args.out/("result-"+str(number)+".json")).write_text(json.dumps(result,indent=2)+"\n")
            if result.get("exit_code")!=0 or result.get("live_owned_after"):
                raise ValueError("Command failed or owned cleanup unresolved; preserve failure")
        if exact["phase"]=="native":
            inspector=module(exact["native_inspector"],"gpu_actual_object_inspector")
            previous=sys.argv
            try:
                sys.argv=[inspector.__file__,"--directory",str(args.out),"--output",str(args.out/"object-inspection.json")]
                inspector.main()  # Pure bounded parsing of actual objects; no linker or stubs.
            finally: sys.argv=previous
        phase_record["outcome"]="host-commands-pass"
    except BaseException as error:
        phase_record["error"]=repr(error)
        raise
    finally:
        # Shared release revalidates retained process/session identities and
        # refuses an unsafe release. Never substitute a local broker or kill.
        try:
            budget.release()
            phase_record["reservation_released"]=True
        except BaseException as error:
            phase_record["reservation_released"]=False
            phase_record["release_error"]=repr(error)
            raise
        finally:
            if args.out.is_dir():
                with (args.out/"phase-result.json").open("x") as stream:
                    json.dump(phase_record,stream,indent=2);stream.write("\n")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase",choices=["native","host-sanitizer"],required=True)
    parser.add_argument("--actual-output",type=Path,required=True)
    parser.add_argument("--experiment",required=True)
    parser.add_argument("--plan-output",type=Path,required=True)
    args=parser.parse_args()
    report=make_plan(args.phase,args.actual_output,args.experiment)
    target=path(args.plan_output)
    if not target.is_relative_to(ROOT/"artifacts/gpu-userclient") or target.exists() or target.is_relative_to(Path(report["output"])):
        parser.error("Fresh disjoint GPU-owned source-plan file required")
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open("x") as stream: json.dump(report,stream,indent=2);stream.write("\n")
    print(json.dumps({"outcome":"source-plan-only","plan":str(target),"sha256":sha(target),"execution_ready":False}))
    return 0


if __name__=="__main__":
    sys.exit(main())
