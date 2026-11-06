"""Independent runtime-map parser controls; all map/image bytes are synthetic."""
import ast
from contextlib import ExitStack
import copy
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from types import ModuleType

MAIN=Path('/home/egor/dev/pet/s24-ios-exynos');BASE=Path(__file__).resolve().parent;OUT=BASE/'run-1'
AUTHOR=MAIN/'worktrees/vm-047-runtime-linkmap-20261106'
CORE=MAIN/'worktrees/vm-022-link-cursor-20261106/tools/build/avf_guest_link_inputs.py'
CORE_SHA='9f80e32305ce84e33ab27bcf37d589465a97c2d03c5eb6830fd3540f204400c5'
MODULE=AUTHOR/'tools/build/avf_guest_runtime_linkmap.py'
MODULE_SHA='380cdd4016cecbd7b86ec8338ddd39fe2468b1cc7b7f116f63cdfdba5ec99ce0'
ARCHIVE=MAIN/'worktrees/krn-025-20261105/artifacts/xnu-cc-kext/controls-session2/resource-positive/lib/darwin/libclang_rt.cc_kext_ios.a'
CATALOG=MAIN/'worktrees/krn-025-20261105/artifacts/xnu-cc-kext/controls-session2/archive-members.json'
checks=[];bindings={}


def sha(p):
    with Path(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()


def need(condition,message):
    if not condition:raise ValueError(message)


def check(name,condition=True):need(condition,name);checks.append(dict(name=name,passed=True))


def pin(p,h):
    p=Path(p);need(p.is_file()and not p.is_symlink()and sha(p)==h,'Changed regular input: '+str(p));bindings[str(p)]=h;return p


def read(p,h=None):
    p=Path(p);pin(p,h or sha(p));return json.loads(p.read_text())


def module(p,h,name):
    pin(p,h);b=p.read_bytes();need(hashlib.sha256(b).hexdigest()==h,'Source changed during capture')
    m=ModuleType(name);m.__file__=str(p);sys.modules[name]=m;exec(compile(b,str(p),'exec'),m.__dict__);return m


def save(p,d):p.write_text(json.dumps(d,indent=2)+'\n')


def reject(name,action):
    try:action()
    except (ValueError,OSError)as error:checks.append(dict(name=name,rejected=True,diagnostic=str(error)))
    else:raise ValueError('Negative accepted: '+name)


def run():
    core=module(CORE,CORE_SHA,'reviewed_cu_cursor');mod=module(MODULE,MODULE_SHA,'reviewed_runtime_map')
    producer=read(AUTHOR/'docs/procedures/avf-runtime-linkmap/evidence.json','f94143823a0847fb00f40d73e0696041e77524e3e34d9f98254cb4bf7913d977')
    for row in producer['artifact_bindings']:pin(MAIN/row['path'],row['sha256'])
    raw=read(MAIN/producer['artifacts'][0],producer['artifact_bindings'][0]['sha256'])
    check('completed-original65-controls-preserved',producer['outcome']=='pass'and len(producer['controls'])==65 and producer['core_source_sha256']=='0631a7d8f310e881d08105c4229c1e22ccb771eb52453648e0a1f1aae4c18464')
    # Keep original source and accepted runtime/reviewer evidence; no old suite.
    pin(MAIN/'worktrees/vm-022-link-correction-20261106/tools/build/avf_guest_link_inputs.py',producer['core_source_sha256'])
    pin(MAIN/'worktrees/rev-vm023-ex-20261106/docs/reviews/vm-023/evidence.json',mod.LINEAGE['review_evidence_sha256'])
    pin(MAIN/'worktrees/vm-023-20261106/docs/procedures/avf-guest-compiler-runtime/evidence.json',mod.LINEAGE['producer_evidence_sha256'])
    source_path=AUTHOR/'fixtures/public/avf-runtime-linkmap/source-contract.json'
    descriptor=read(source_path,mod.SOURCE_DESCRIPTOR_SHA256)
    with ExitStack()as stack:
        desc=stack.enter_context(core.CoherentFile(source_path))
        sources={row[key]:stack.enter_context(core.CoherentFile(pin(MAIN/row[key],row['sha256'])))for row in descriptor['files']for key in ['path','reference_path']}
        linker=stack.enter_context(core.CoherentFile(pin(MAIN/'artifacts/xnu-macho-tools/macho-session4/prefix/bin/aarch64-apple-darwin-ld',mod.LINEAGE['linker_sha256'])))
        facts=mod.qualify_sources(desc,sources,linker)
    save(OUT/'source-facts.json',facts)
    check('actual-source-pairs-and-linker-without-execution',facts['source_file_count']==8 and facts['execution_started']is False and facts['product_authority']is False)
    output=(MAIN/descriptor['files'][1]['path']).read_text();options=(MAIN/descriptor['files'][0]['path']).read_text();archive_source=(MAIN/descriptor['files'][2]['path']).read_text()
    check('pinned-map-grammar-headers-and-warning',all(s in output for s in ['# Object files:','# Sections:','# Symbols:','# Dead Stripped Symbols:','could not write map file:']))
    check('pinned-options-and-load-grammar',all(s in options for s in ['"-why_load"','"-map"'])and 'vprintf(format, list)'in archive_source)
    tree=ast.parse(MODULE.read_bytes());imports=[n for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom))]
    check('module-only-hash-json-regex-imports',all(isinstance(n,ast.Import)and all(a.name in ['hashlib','json','re']for a in n.names)for n in imports))
    catalog=read(CATALOG,mod.LINEAGE['runtime_members_sha256']);pin(ARCHIVE,mod.LINEAGE['runtime_archive_sha256'])
    with core.CoherentFile(ARCHIVE)as a,core.CoherentFile(CATALOG)as c:actual=mod.qualified_catalog(a,c)
    check('genuine287-physical-members-framing-order-hash',len(actual)==287 and actual==catalog)
    # Reuse just the tiny explicit synthetic image byte fixture, not controls.
    image_source=AUTHOR/'artifacts/avf-runtime-linkmap/controls-001/synthetic-positive-real287-archive/synthetic-image.macho'
    image_bytes=pin(image_source,sha(image_source)).read_bytes()
    controls=OUT/'controls';controls.mkdir()
    base_address=0xfffffff007004000;pc=base_address+496
    def case(label,change=None):
        directory=controls/label;directory.mkdir();image=directory/'synthetic.macho';image.write_bytes(image_bytes)
        mapfile=directory/'synthetic.map';objlist=directory/'objects.json'
        member=lambda n:str(ARCHIVE)+'('+catalog[n]['name']+')'
        rows=['# Path: '+str(image),'# Arch: arm64','# Object files:','[  0] linker synthesized','[  1] '+member(2),
            '# Sections:','# Address\tSize    \tSegment\tSection',f'0x{pc:08X}\t0x00000010\t__TEXT\t__text',
            '# Symbols:','# Address\tSize    \tFile  Name',f'0x{pc+4:08X}\t0x00000004\t[  1] ___divtc3']
        doc=dict(schema='avf-guest-link-object-list-v1',source_only=False,objects=[],archives=[dict(role='runtime',path=str(ARCHIVE),sha256=mod.LINEAGE['runtime_archive_sha256'],members=[dict(ordinal=i,name=r['name'],sha256=r['sha256'])for i,r in enumerate(catalog)])],actual_link_argv=['unexecuted-synthetic-linker','-o',str(image),str(ARCHIVE),'-map',str(mapfile),'-why_load'])
        contract=dict(schema='avf-runtime-linkmap-contract-v1',measurement_origin='synthetic-control',source_only=False,lineage=dict(mod.LINEAGE),source_descriptor_sha256=mod.SOURCE_DESCRIPTOR_SHA256,architecture='arm64',output_path=str(image),required_members=[2],diagnostic_argv=mod.diagnostic_options(str(mapfile)))
        state=dict(rows=rows,document=doc,contract=contract,archive=ARCHIVE,catalog=CATALOG)
        if change:change(state)
        mapfile.write_bytes(state.get('raw_map',('\n'.join(state['rows'])+'\n').encode()))
        objlist.write_bytes(state.get('raw_json',(json.dumps(doc)+'\n').encode()))
        paths=dict(image=image,map=mapfile,object_list=objlist,archive=state['archive'],catalog=state['catalog'])
        contract['bindings']={k:dict(path=str(p),sha256=sha(p))for k,p in paths.items()};save(directory/'contract.json',contract)
        before=len(list(Path('/proc/self/fd').iterdir()))
        with ExitStack()as stack:
            snapshot,view=stack.enter_context(core.macho_snapshot(image,image=True))
            external=view['external_symbols'];tempdir=Path(external.temporary.name)
            allsnaps={k:stack.enter_context(core.CoherentFile(p))for k,p in paths.items()if k!='image'}
            if 'view'in state:state['view'](view)
            result=mod.validate(snapshot,view,contract,map_snapshot=allsnaps['map'],archive_snapshot=allsnaps['archive'],object_list_snapshot=allsnaps['object_list'],catalog_snapshot=allsnaps['catalog'])
        save(directory/'result.json',result) # serialization after all borrowed closes
        need(len(list(Path('/proc/self/fd').iterdir()))==before and not tempdir.exists(),'Borrowed FD/symbol store leaked')
        need(all(result[k]is False for k in ['product_authority','actual_execution_authenticated','qualified_for_actual_selection','import_closure_measured','lto_retention_measured']),'Synthetic/caller data promoted to actual credit')
        return result
    result=case('positive-borrowed9f80')
    check('synthetic-positive-after-borrowed-context-close',result['selected_symbols'][0]['name']=='___divtc3'and result['members'][0]['ordinal']==2)
    check('only-JSON-primitives-no-lazy-resource-return',isinstance(json.loads(json.dumps(result)),dict))
    result=case('forged-actual-authority',lambda s:s['contract'].update(measurement_origin='actual-link',product_authority=True,qualified_for_actual_selection=True,actual_execution_authenticated=True))
    check('caller-actual-and-authority-labels-never-credit',result['actual_execution_authenticated']is False)
    # Focus fresh parser cases; old65-control suite is not repeated.
    changes=[
        ('duplicate-files',lambda s:s['rows'].insert(5,s['rows'][4])),
        ('unknown-file-number',lambda s:s['rows'].__setitem__(10,f'0x{pc+4:08X}\t0x00000004\t[99999] ___divtc3')),
        ('foreign-member',lambda s:s['rows'].__setitem__(4,'[  1] /foreign.a(foreign.o)')),
        ('negative-address',lambda s:s['rows'].__setitem__(10,'0x-0000001\t0x00000004\t[  1] ___divtc3')),
        ('u64-overflow',lambda s:s['rows'].__setitem__(10,'0xFFFFFFFFFFFFFFFF\t0x00000004\t[  1] ___divtc3')),
        ('outside-final-section',lambda s:s['rows'].__setitem__(10,f'0x{pc+15:08X}\t0x00000004\t[  1] ___divtc3')),
        ('noncatalog-provider',lambda s:s['rows'].__setitem__(10,f'0x{pc+4:08X}\t0x00000004\t[  1] unproved_label')),
        ('truncated-terminal-line',lambda s:s.update(raw_map=('\n'.join(s['rows'])).encode())),
        ('trailing-nonnewline',lambda s:s.update(raw_map=('\n'.join(s['rows'])+'\ntrailing').encode())),
        ('invalid-utf8',lambda s:s.update(raw_map=b'\xff\n')),
        ('oversized-line',lambda s:s.update(raw_map=b'Z'*65537+b'\n')),
        ('duplicate-JSON-key',lambda s:s.update(raw_json=b'{"source_only":false,"source_only":false}\n')),
        ('nonfinite-JSON',lambda s:s.update(raw_json=b'{"nan":NaN}\n')),
        ('dead-only-required-member',lambda s:s['contract'].update(required_members=[0])),
        ('bool-required-member',lambda s:s['contract'].update(required_members=[True])),
        ('wrong-producer',lambda s:s['contract']['lineage'].update(producer_implementation='0'*40)),
        ('wrong-source',lambda s:s['contract']['lineage'].update(linker_revision='0'*40)),
        ('wrong-compiler',lambda s:s['contract']['lineage'].update(compiler_sha256='0'*64)),
        ('wrong-map-source-descriptor',lambda s:s['contract'].update(source_descriptor_sha256='0'*64)),
        ('source-only-contract',lambda s:s['contract'].update(source_only=True)),
        ('unknown-origin',lambda s:s['contract'].update(measurement_origin='approved-by-caller')),
        ('guessed-linker-option',lambda s:s['contract']['diagnostic_argv'].append('-invented')),
        ('missing-map-operand',lambda s:s['document']['actual_link_argv'].__setitem__(-3,'-invented')),
        ('wrong-final-provider-section',lambda s:s.update(view=lambda v:v['external_symbols'].db.execute("UPDATE symbols SET section=0 WHERE name='___divtc3'"))),
    ]
    for label,change in changes:reject(label,lambda:case(label,change))
    def swap(s):
        member=lambda n:str(ARCHIVE)+'('+catalog[n]['name']+')'
        s['rows'][4:5]=['[  1] '+member(2),'[  2] '+member(0)]
    reject('physical-archive-member-order',lambda:case('physical-archive-member-order',swap))
    # Real fixed archive copies: honest digest-level rejection, never forged pins.
    def swap_pair(data):
        i=next(i for i in range(60,len(data)-1)if data[i]!=data[i+1])
        return data[:i]+data[i:i+2][::-1]+data[i+2:]
    for label,transform in [('archive-flip',lambda b:b[:-1]+bytes([b[-1]^1])),('archive-truncate',lambda b:b[:-1]),('archive-grow',lambda b:b+b'\n'),('archive-swapped-body',swap_pair)]:
        p=controls/(label+'.a');p.write_bytes(transform(ARCHIVE.read_bytes()))
        def corrupt():
            with core.CoherentFile(p)as a,core.CoherentFile(CATALOG)as c:mod.qualified_catalog(a,c)
        reject(label,corrupt)
    # Optional diagnostic grammar returns facts without selection authority.
    diag=controls/'load.txt';diag.write_text('___divtc3 forced load of '+str(ARCHIVE)+'('+catalog[2]['name']+')\n')
    with core.CoherentFile(diag)as s:facts=mod.parse_load_diagnostics(s,str(ARCHIVE),catalog)
    check('optional-load-diagnostic-no-retention-credit',facts['retention_credit']is False and facts['product_authority']is False)
    diag.write_text(diag.read_text()*2)
    def duplicate_diagnostic():
        with core.CoherentFile(diag)as s:mod.parse_load_diagnostics(s,str(ARCHIVE),catalog)
    reject('duplicated-runtime-load-diagnostic',duplicate_diagnostic)
    # Growth/replacement of actual retained FDs cannot become coherent evidence.
    for label in ['growth','replacement','symlink']:
        p=controls/('coherent-'+label);p.write_bytes(b'owned\n')
        def mutate():
            if label=='symlink':
                alias=controls/'fd-alias';alias.symlink_to(p)
                try:
                    with core.CoherentFile(alias):pass
                finally:alias.unlink()
            else:
                with core.CoherentFile(p)as s:
                    if label=='growth':
                        it=mod.lines(s);next(it)
                        with p.open('ab')as f:f.write(b'new\n')
                        list(it)
                    else:
                        old=p.with_suffix('.old');p.rename(old);p.write_bytes(old.read_bytes());s.check()
        reject('actual-FD-'+label,mutate)
    for p,h in list(bindings.items()):pin(p,h)
    check('all-direct-physical-witnesses-unchanged')
    return dict(core_sha256=CORE_SHA,module_sha256=MODULE_SHA,synthetic_map_and_image=True,
        actual_selected_runtime_credit=False,compiler_started=False,actual_link_started=False,
        archive_tool_started=False,source_corpus_replayed=False,producer_suite_repeated=False)


if __name__=='__main__':
    report=dict(kind='host-test',origin='local-host',recorded_at=datetime.now(timezone.utc).isoformat(),outcome='fail');code=1
    try:report.update(run());report['outcome']='pass';code=0
    except Exception as error:report.update(error_type=type(error).__name__,error=str(error))
    finally:
        report.update(checks=checks,checks_total=len(checks),negative_controls=sum(x.get('rejected',False)for x in checks),bindings=bindings,proc_status=[x for x in Path('/proc/self/status').read_text().splitlines()if x.startswith(('VmRSS:','VmHWM:'))]);save(OUT/'report.json',report);print(json.dumps({k:report[k]for k in ['outcome','checks_total','negative_controls']},indent=2))
    sys.exit(code)
