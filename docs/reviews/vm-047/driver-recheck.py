"""Focused independent v2 correction; no actual driver, linker or target tool."""
from contextlib import ExitStack
import copy
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from types import ModuleType

MAIN=Path('/home/egor/dev/pet/s24-ios-exynos');BASE=Path(__file__).resolve().parent;OUT=BASE/'driver-run-1'
AUTHOR=MAIN/'worktrees/vm-047-driver-contract-20261106'
MODULE=AUTHOR/'tools/build/avf_guest_runtime_linkmap.py'
MODULE_SHA='e811f74e76e6a8e11741de731acad1eeaee2b393a9ea22fdd25664c88d650b67'
CORE=MAIN/'worktrees/vm-022-link-cursor-20261106/tools/build/avf_guest_link_inputs.py'
CORE_SHA='9f80e32305ce84e33ab27bcf37d589465a97c2d03c5eb6830fd3540f204400c5'
ARCHIVE=MAIN/'worktrees/krn-025-20261105/artifacts/xnu-cc-kext/controls-session2/resource-positive/lib/darwin/libclang_rt.cc_kext_ios.a'
CATALOG=ARCHIVE.parents[3]/'archive-members.json'
checks=[];bindings={}


def sha(p):
    with Path(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()


def need(ok,message):
    if not ok:raise ValueError(message)


def check(name,ok=True):need(ok,name);checks.append(dict(name=name,passed=True))


def pin(p,h):
    p=Path(p);need(p.is_file()and not p.is_symlink()and sha(p)==h,'Changed regular witness: '+str(p));bindings[str(p)]=h;return p


def read(p,h=None):
    p=Path(p);pin(p,h or sha(p));return json.loads(p.read_text())


def module(p,h,name):
    pin(p,h);b=p.read_bytes();need(hashlib.sha256(b).hexdigest()==h,'Capture changed')
    m=ModuleType(name);m.__file__=str(p);sys.modules[name]=m;exec(compile(b,str(p),'exec'),m.__dict__);return m


def save(p,d):p.write_text(json.dumps(d,indent=2)+'\n')


def reject(name,call):
    try:call()
    except (ValueError,OSError)as error:checks.append(dict(name=name,rejected=True,diagnostic=str(error)))
    else:raise ValueError('Negative accepted: '+name)


def run():
    mod=module(MODULE,MODULE_SHA,'rechecked_driver_map');core=module(CORE,CORE_SHA,'rechecked_cu')
    producer=read(AUTHOR/'docs/procedures/avf-runtime-linkmap/driver-evidence.json','6ecc17e0403b8cec3f1aa8160f11f600dd0e43d93de07387059ac851fa4cfbc8')
    for item in producer['artifact_bindings']:pin(MAIN/item['path'],item['sha256'])
    check('completed-producer42-preserved-without-replay',producer['outcome']=='pass'and len(producer['controls'])==42)
    pin(BASE/'evidence.json','b083d86733cb975a7effdb8cf64ebb4aa2d1d627fc365f376f837f1d7409dfc4')
    pin(BASE/'controls-evidence.json','5936f4b68e6ee59ed54a83f2d19b384ab814978f5ac218cbc3d8264eaa2a3921')
    pin(MAIN/'worktrees/vm-047-runtime-linkmap-20261106/tools/build/avf_guest_runtime_linkmap.py','380cdd4016cecbd7b86ec8338ddd39fe2468b1cc7b7f116f63cdfdba5ec99ce0')
    proof=AUTHOR/'fixtures/public/avf-runtime-linkmap/driver-forwarding-source.json';proofdoc=read(proof,mod.DRIVER_SOURCE_SHA256)
    compiler=MAIN/'artifacts/xnu-compiler-cxx-storage/source-build-session2/clang'
    with ExitStack()as stack:
        snapshots={r[k]:stack.enter_context(core.CoherentFile(pin(MAIN/r[k],r['sha256'])))for r in proofdoc['files']for k in ['path','reference_path']}
        result=mod.qualify_driver_sources(stack.enter_context(core.CoherentFile(proof)),snapshots,stack.enter_context(core.CoherentFile(pin(compiler,mod.LINEAGE['compiler_sha256']))))
    save(OUT/'driver-source-proof.json',result);check('14-source-reference-files-and-compiler-no-invocation',result['source_file_count']==14 and result['product_authority']is False and result['execution_started']is False)
    # Source grammar reviewed from the exact bytes that qualify the projection.
    option=(MAIN/proofdoc['files'][0]['path']).read_text();arg=(MAIN/proofdoc['files'][4]['path']).read_text();parse=(MAIN/proofdoc['files'][5]['path']).read_text()
    check('source-comma-separate-renderasinput-pinned',all(s in option for s in ['def Wl_COMMA','def Xlinker','RenderAsInput','def filelist'])and 'renderAsInput'in arg and 'CommaJoinedClass'in parse)
    template=read(MAIN/'worktrees/vm-022-20261106/artifacts/avf-guest-link-inputs/preparation-4/prepared-link-inputs.json','125a7627c1178d3812f3e618c8f8bcc125cb77520be100013cbcc710b84c9d3a')['next_owned_link_argv_template']
    map_path=str(OUT/'unexecuted-proposed.map')
    expanded=[re.sub(r'@[A-Z_]+@',str(OUT/'unexecuted-stage'),s)for s in template]
    projected=mod.driver_diagnostic_operands(expanded+['-Wl,-map,'+map_path,'-Wl,-why_load'],map_path)
    check('genuine125a-driver-template-diagnostic-subset',expanded[0]==str(compiler)and projected==['-map',map_path,'-why_load'])
    save(OUT/'source-template-projection.json',dict(source_template_sha256='125a7627c1178d3812f3e618c8f8bcc125cb77520be100013cbcc710b84c9d3a',kind='source-template-expansion-only-not-actual-child',diagnostic_projection=projected,execution_started=False))
    check('canonical-separate-forwarding-same-subset',mod.driver_diagnostic_operands([str(compiler),'-Xlinker','-map','-Xlinker',map_path,'-Xlinker','-why_load'],map_path)==projected)
    reject('projection-ambiguous-unrelated-tail',lambda:mod.driver_diagnostic_operands([str(compiler),'-Wl,-map,'+map_path+',-segprot','-Wl,-why_load'],map_path))
    reject('separate-nonadjacent-map-value',lambda:mod.driver_diagnostic_operands([str(compiler),'-Xlinker','-map','tail.o','-Xlinker',map_path,'-Wl,-why_load'],map_path))
    catalog=read(CATALOG,mod.LINEAGE['runtime_members_sha256']);pin(ARCHIVE,mod.LINEAGE['runtime_archive_sha256'])
    image_path=BASE/'run-1/controls/positive-borrowed9f80/synthetic.macho';image_bytes=pin(image_path,sha(image_path)).read_bytes()
    controls=OUT/'controls';controls.mkdir();pc=0xfffffff007004000+496
    def case(label,mutate=None,empty=False,both=False,matches=None,query_count=None):
        d=controls/label;d.mkdir();image=d/'synthetic.image';image.write_bytes(image_bytes);mapfile=d/'synthetic.map';objlist=d/'sealed-objects.json'
        a,b,tail=[d/n for n in ['filelist-a.o','filelist-b.o','direct-tail.o']]
        for p in [a,b,tail]:p.write_bytes(b'owned synthetic staged object, never compiled')
        fl1,fl2=d/'first.filelist',d/'second.filelist';fl1.write_text(str(a)+'\n');fl2.write_text(str(b)+'\n')
        member=lambda n:str(ARCHIVE)+'('+catalog[n]['name']+')'
        argv=[str(compiler),'-filelist',str(fl1),'-filelist',str(fl2),str(tail),'-resource-dir',str(d/'synthetic-resource'),'-lcc_kext','-o',str(image),'-Wl,-map,'+str(mapfile),'-Wl,-why_load']
        document=dict(schema='avf-guest-link-object-list-v2',command_kind='clang-driver',source_only=False,actual_driver_argv=argv,
            derived_linker_operands=dict(kind='forwarded-driver-operands-only',argv=mod.diagnostic_options(str(mapfile)),source_proof=dict(path=str(proof),sha256=mod.DRIVER_SOURCE_SHA256)),
            filelists=[dict(path=str(fl1),sha256=sha(fl1),ordered_object_paths=[str(a)]),dict(path=str(fl2),sha256=sha(fl2),ordered_object_paths=[str(b)])],
            objects=[dict(id=p.name,path=str(p),sha256=sha(p))for p in [a,b,tail]],
            archives=[dict(role='runtime',path=str(ARCHIVE),sha256=mod.LINEAGE['runtime_archive_sha256'],members=[dict(ordinal=i,name=r['name'],sha256=r['sha256'])for i,r in enumerate(catalog)])])
        rows=['# Path: '+str(image),'# Arch: arm64','# Object files:','[  0] linker synthesized','[  1] '+str(a),'[  2] '+member(0),'[  3] '+member(2),'# Sections:','# Address\tSize    \tSegment\tSection',f'0x{pc:08X}\t0x00000010\t__TEXT\t__text','# Symbols:','# Address\tSize    \tFile  Name',f'0x{pc:08X}\t0x00000004\t[  0] __start']
        if not empty:rows.append(f'0x{pc+4:08X}\t0x00000004\t[  3] ___divtc3')
        if both:rows.append(f'0x{pc:08X}\t0x00000004\t[  2] local_runtime_atom')
        if matches is None:rows.extend([f'0x{pc+8:08X}\t0x00000004\t[  1] owned_atom',f'0x{pc+12:08X}\t0x00000004\t[  1] owned_atom'])
        else:rows.extend([f'0x{pc+8:08X}\t0x00000000\t[  1] owned_atom']*matches)
        rows.extend(['','# Dead Stripped Symbols:','#        \tSize    \tFile  Name','<<dead>> \t0x00000004\t[  2] dead_runtime_atom','<<dead>> \t0x00000004\t[  1] owned_atom'])
        if empty:rows.append('<<dead>> \t0x00000004\t[  3] ___divtc3')
        contract=dict(schema='avf-runtime-linkmap-contract-v2',command_kind='clang-driver',selection_scope='all-observed-live-runtime-members',measurement_origin='synthetic-control',source_only=False,lineage=dict(mod.LINEAGE),source_descriptor_sha256=mod.SOURCE_DESCRIPTOR_SHA256,architecture='arm64',output_path=str(image),diagnostic_argv=mod.diagnostic_options(str(mapfile)),atom_queries=[dict(object_path=str(a),name='owned_atom'),dict(object_path=member(2),name='___divtc3')])
        if matches is not None:contract['atom_queries']=contract['atom_queries'][:1]
        if query_count is not None:contract['atom_queries']=[dict(object_path=str(a),name='no-match-'+str(i))for i in range(query_count)]
        if both:contract['required_members']=[2]
        state=dict(document=document,contract=contract,rows=rows,filelists=[fl1,fl2],inside=None,extra_snapshot=False)
        if mutate:mutate(state)
        mapfile.write_text('\n'.join(state['rows'])+'\n');save(objlist,document)
        paths=dict(image=image,map=mapfile,object_list=objlist,archive=ARCHIVE,catalog=CATALOG,driver_source=proof)
        contract['bindings']={k:dict(path=str(p),sha256=sha(p))for k,p in paths.items()};save(d/'contract.json',contract)
        before=len(list(Path('/proc/self/fd').iterdir()))
        with ExitStack()as stack:
            snap,view=stack.enter_context(core.macho_snapshot(image,image=True));temporary=Path(view['external_symbols'].temporary.name)
            borrowed={k:stack.enter_context(core.CoherentFile(p))for k,p in paths.items()if k!='image'}
            filelists={str(p):stack.enter_context(core.CoherentFile(p))for p in state['filelists']}
            if state['extra_snapshot']:filelists[str(tail)]=stack.enter_context(core.CoherentFile(tail))
            if state['inside']:state['inside']()
            result=mod.validate(snap,view,contract,map_snapshot=borrowed['map'],archive_snapshot=borrowed['archive'],object_list_snapshot=borrowed['object_list'],catalog_snapshot=borrowed['catalog'],driver_source_snapshot=borrowed['driver_source'],filelist_snapshots=filelists)
        save(d/'result.json',result)
        need(not temporary.exists()and len(list(Path('/proc/self/fd').iterdir()))==before,'Borrowed snapshot/store escaped')
        need(all(result[k]is False for k in ['product_authority','actual_execution_authenticated','qualified_for_actual_selection','observed_linker_child_argv_claimed','queried_atom_qualification','import_closure_measured','lto_retention_measured']),'Synthetic facts gained authority')
        return result,document
    result,doc=case('two-filelists-positive')
    check('two-coherent-filelists-plus-direct-tail',len(result['filelist_bindings'])==2 and result['selected_live_member_ordinals']==[2]and len(result['queried_live_atoms'])==3)
    check('raw-selected-member-externals-exact',result['selected_member_symbols']==[dict(ordinal=2,name=catalog[2]['name'],sha256=catalog[2]['sha256'],defined=catalog[2]['defined'],undefined=catalog[2]['undefined'])])
    check('projection-explicitly-not-observed-child',result['derived_linker_operands']['kind']=='forwarded-driver-operands-only'and result['driver_recipe_authentication_owned_by_controller']is True)
    result,doc=case('dead-only-runtime-empty',empty=True)
    check('dead-filetable-members-yield-honest-empty-selection',result['selected_live_member_ordinals']==[]and result['selected_member_symbols']==[]and result['empty_runtime_selection']is True and len(result['queried_live_atoms'])==2)
    result,doc=case('extra-observed-member',both=True)
    check('all-observed-not-caller-required-subset',result['required_members']==[2]and result['selected_live_member_ordinals']==[0,2]and [r['ordinal']for r in result['selected_member_symbols']]==[0,2])
    check('extra-member-raw-undefined-not-callsite-policy',result['selected_member_symbols'][0]['undefined']==catalog[0]['undefined']and result['import_closure_measured']is False)
    result,doc=case('maximum-4096-matches',matches=4096)
    check('actual4096-match-boundary-positive',len(result['queried_live_atoms'])==4096)
    reject('actual4097-matches-rejected',lambda:case('excess4097',matches=4097))
    result,doc=case('maximum512-queries',query_count=512)
    check('512-exact-query-boundary-positive',len(result['atom_queries'])==512 and result['queried_live_atoms']==[])
    reject('513-queries-rejected',lambda:case('excess513',query_count=513))
    mutations=[
        ('filelist-order',lambda s:s['document']['filelists'].reverse()),
        ('unbound-tail',lambda s:s['document']['actual_driver_argv'].__setitem__(5,'unadmitted-tail.o')),
        ('extra-snapshot',lambda s:s.update(extra_snapshot=True)),
        ('projection-labeled-observed',lambda s:s['document']['derived_linker_operands'].update(kind='actual-child-argv')),
        ('forged-forwarding-proof',lambda s:s['document']['derived_linker_operands']['source_proof'].update(sha256='0'*64)),
        ('claimed-actual-ld-field',lambda s:s['document'].update(actual_link_argv=['invented-ld'])),
        ('query-parent-directory-not-object',lambda s:s['contract'].update(atom_queries=[dict(object_path=str(controls),name='owned_atom')])),
    ]
    for label,change in mutations:reject(label,lambda:case(label,change))
    def duplicate_expansion(s):
        first=s['filelists'][0].read_text();second=s['filelists'][1];second.write_text(first)
        s['document']['filelists'][1].update(sha256=sha(second),ordered_object_paths=first.splitlines())
    reject('real-duplicate-cross-filelist-object',lambda:case('duplicate-expansion',duplicate_expansion))
    def growth(s):
        p=s['filelists'][0]
        def inside():
            with p.open('ab')as f:f.write(b'/late/object.o\n')
        s['inside']=inside
    reject('actual-late-filelist-FD-growth',lambda:case('late-filelist-growth',growth))
    for p,h in list(bindings.items()):pin(p,h)
    check('old-inconclusive-and-all-source-bindings-unchanged')
    return dict(module_sha256=MODULE_SHA,producer_final_commit='d9c4b5e4aab4c0e38c9b7dd8c76f86ded3f01983',historical_inconclusive_preserved=True,source_interface_gate_resolved=True,actual_driver_executed=False,actual_selected_runtime_credit=False,previous_matrices_repeated=False,compiler_started=False)


if __name__=='__main__':
    report=dict(kind='host-test',origin='local-host',recorded_at=datetime.now(timezone.utc).isoformat(),outcome='fail');code=1
    try:report.update(run());report['outcome']='pass';code=0
    except Exception as error:report.update(error_type=type(error).__name__,error=str(error))
    finally:
        report.update(checks=checks,checks_total=len(checks),negative_controls=sum(r.get('rejected',False)for r in checks),bindings=bindings,proc_status=[x for x in Path('/proc/self/status').read_text().splitlines()if x.startswith(('VmRSS:','VmHWM:'))]);save(OUT/'report.json',report);print(json.dumps({k:report[k]for k in ['outcome','checks_total','negative_controls']},indent=2))
    sys.exit(code)
