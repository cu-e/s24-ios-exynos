"""Independent bounded read-only STR036 source facts; never imports the caller."""
import ast
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import resource
resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,256*1024**2))
MAIN=Path('/home/egor/dev/pet/s24-ios-exynos')
AUTHOR=MAIN/'worktrees/str-036-e1s-native-link-source-fix1-20261106'
BASE=Path(__file__).resolve().parent
bindings={}
def pin(path,expected):
    path=Path(path)
    assert path.is_file() and not path.is_symlink() and path.resolve(strict=True)==path
    with path.open('rb')as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
    assert actual==expected,(str(path),actual)
    bindings[str(path)]=actual
    return path

def load(binding):
    return json.loads(pin(binding['path'],binding['sha256']).read_text())

def tree_functions(path):
    return {n.name:ast.dump(n,include_attributes=False)for n in ast.parse(path.read_text()).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}

source=pin(AUTHOR/'fixtures/public/e1s-native-link/native_link.py','bdb23b9481e5ecae7a050b1262c095dd37afc3c1a6cde7a7d7d798e8694169a3')
prior=pin(MAIN/'worktrees/str-036-e1s-native-link-source-20261106/fixtures/public/e1s-native-link/native_link.py','b3b8beaf07ab6fa88126964ba7b5d917ea95604f384da404c612e1343c41df12')
policy=load(dict(path=str(AUTHOR/'fixtures/public/e1s-native-link/policy.json'),sha256='136f4c7885d81320e8ea5f7a1cf4032a71f81eee786cf4415e7280cfcf866098'))
contract=load(policy['contract']);graph=load(policy['body_graph']);pin(policy['graph']['path'],policy['graph']['sha256']);pin(policy['context']['path'],policy['context']['sha256']);pin(policy['profile']['path'],policy['profile']['sha256']);overrides=load(policy['overrides'])
metadata=load(policy['metadata'])
old=load(dict(path=str(MAIN/'worktrees/str-036-e1s-native-link-source-20261106/docs/procedures/e1s-native-link/evidence.json'),sha256='f1c66ac43a2489316f5f2742ee7cbd5f86c7b0a8b938f25694f9f6e6c9e01a3b'))
correction_path=AUTHOR/'docs/procedures/e1s-native-link/correction-evidence.json'
with correction_path.open('rb')as stream:correction_sha=hashlib.file_digest(stream,'sha256').hexdigest()
correction=load(dict(path=str(correction_path),sha256=correction_sha))
assert correction_sha.startswith('3f96')
for name,sha in correction['artifact_sha256'].items():pin(name,sha)
# Inspect exact common/native/core API bytes, never execute imports or target tools.
parsed=ast.parse(source.read_text())
constants={n.targets[0].id:ast.literal_eval(n.value) for n in parsed.body if isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='POLICY_SHA'}
assert constants['POLICY_SHA']=='136f4c7885d81320e8ea5f7a1cf4032a71f81eee786cf4415e7280cfcf866098'
helpers={
'common':(MAIN/'tools/build/avf_kernel_objects.py','9929a7d6f1e748770f54abf3e101350648092027a18c419a242d0348f620f755'),
'core':(MAIN/'worktrees/vm-022-link-cursor-20261106/tools/build/avf_guest_link_inputs.py','9f80e32305ce84e33ab27bcf37d589465a97c2d03c5eb6830fd3540f204400c5'),
'archive':(MAIN/'tools/build/avf_guest_components.py','e62d7592fc35cdc3c011eac2ee537bdcfa09e3ab9308cf17d422e0b7f39e29aa'),
'native':(MAIN/'worktrees/str-030-e1s-native-compile-fix2-20261106/fixtures/public/e1s-native-compile/native_compile.py','2676a8edb31b0136aa7195d37523549d9c77edee7ac140a7f476ebf5064b178f'),
'supervise':(MAIN/'tools/build/qemu_host.py','faaa9b707a8bb48b1ee502a2c58c9b876eb7859ad5b0ff6541bae27c20ed9f99')}
for name,(path,sha)in helpers.items():pin(path,sha)
oldf,newf=tree_functions(prior),tree_functions(source)
changed=[k for k in newf if newf[k]!=oldf.get(k)]
assert changed==['make_plan','execute']
ids=[x['id']for x in graph['objects']]
assert len(ids)==len(set(ids))==1042
assert [x['id']for x in overrides['overrides']]==['osfmk/start.o','bsd/e1s_log.o']
filelists=contract['ordered_filelist_templates']
assert [x['component']for x in filelists]==policy['component_order']==['osfmk','bsd','libkern','iokit','pexpert','libsa','security','san']
assert all(f['ordered_object_ids']==[x['id']for x in graph['objects']if x['component']==f['component']]for f in filelists)
assert sum(len(f['ordered_object_ids'])for f in filelists)==1042
assert contract['concatenation']['component_filelist_order']==[f['filelist_template']for f in filelists]
assert len(contract['owned_copy_transforms'][0]['ordered_object_ids'])==14 and contract['owned_copy_transforms'][1]['ordered_object_ids']==['libsa/bootstrap.cpo']
assert len(metadata['metadata'])==22 and metadata['outcome']=='pass'
assert [t['name']for t in contract['tail_order']]==['version.o','lastkerneldataconst.o','lastkernelconstructor.o','nonlto.o']
assert all(t['depfile']['path']in correction['artifact_sha256']for t in contract['tail_order'])
argv=contract['native_driver']['original_shell_argv']
assert hashlib.sha256(json.dumps(argv,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()==policy['original_argv_sha256']
assert [a for a in argv if a in ['-lcc_kext','-lfirehose_kernel','-lpthread_kext']]==['-lcc_kext','-lfirehose_kernel','-lpthread_kext']
assert not any('-undefined' in a or '-exported_symbols_list' in a for a in argv)
assert argv.count('-nostdlib')==2
assert old['actual']['check_count']==20 and old['actual']['target_tools_started']==0 and correction['source_delta']['original_source_controls_repeated']is False
result=dict(kind='source-review',origin='local-host',recorded_at=datetime.now(timezone.utc).isoformat(),outcome='pass',summary='Independent static STR036 final native caller source/authority/interface audit; no target tools, control replay, staging or complete plan',reviewed_final_commit='fafc8b390979e2e5f81f65bba8afae0c6710436a',reviewed_caller_sha256=bindings[str(source)],source_correction_sha256=correction_sha,changed_function_ASTs=changed,source_count=1042,native_component_filelists=8,graph_index_order_is_distinct_from_native_component_concatenation=True,per_component_genuine_order_exact=True,overrides=['osfmk/start.o','bsd/e1s_log.o'],transform_operations=16,tails=4,metadata_products=22,helpers={n:sha for n,(p,sha)in helpers.items()},bindings=bindings,original20_controls_repeated=False,source_imports_executed=False,target_tools_started=0,complete_plan_or_staging_created=False,actual_future_lifecycle_qualified=False,proc_status=[x for x in Path('/proc/self/status').read_text().splitlines()if x.startswith(('VmRSS:','VmHWM:'))])
(BASE/'source-facts.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:result[k]for k in ['outcome','reviewed_caller_sha256','source_correction_sha256','source_count','transform_operations','target_tools_started','proc_status']},indent=2))
