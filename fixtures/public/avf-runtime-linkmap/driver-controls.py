#!/usr/bin/env python3
"""Focused v2 driver/filelist/observed-selection controls, no target execution."""
import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import resource
import sys
import time
import traceback

sys.path.insert(0, str(Path(__file__).parent))
from controls import digest, image_bytes, load_module, save, PC

CORE_SHA = '9f80e32305ce84e33ab27bcf37d589465a97c2d03c5eb6830fd3540f204400c5'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--main', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    started, observations, samples = time.monotonic(), [], []
    resource.setrlimit(resource.RLIMIT_AS, (256*1024**2, 256*1024**2))
    evidence = {'kind':'host-test','origin':'local-host','outcome':'fail',
        'task':'VM-047','owner':'codex-guest-linkmap-witness-20261106-fb',
        'recorded_at':datetime.now(timezone.utc).isoformat(),
        'summary':'Driver contract focused controls did not complete',
        'synthetic_maps_images_and_staged_objects':True,
        'actual_driver_started':False,'compiler_started':False,'linker_started':False,
        'actual_selected_runtime_success_measured':False,'controls':observations,
        'commands':[{'argv':sys.argv,'exit_code':None}]}
    exit_code = 1
    try:
        for number in range(3):
            available = next(int(line.split()[1])*1024 for line in
                Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))
            samples.append(available)
            if available < 4*1024**3:
                raise RuntimeError('Stable4GiB floor unavailable')
            if number < 2:time.sleep(1)
        wt = Path(__file__).resolve().parents[3]
        core_path = args.main/'worktrees/vm-022-link-cursor-20261106/tools/build/avf_guest_link_inputs.py'
        assert digest(core_path) == CORE_SHA
        sys.path.insert(0, str(core_path.parent))
        core = load_module('vm047_driver_borrowed_core', core_path)
        source = wt/'tools/build/avf_guest_runtime_linkmap.py'
        mod = load_module('vm047_driver_runtime', source)
        proof = Path(__file__).with_name('driver-forwarding-source.json').resolve()
        proof_doc = json.loads(proof.read_text())
        compiler = args.main/'artifacts/xnu-compiler-cxx-storage/source-build-session2/clang'
        with ExitStack() as stack:
            source_snaps = {row[key]:stack.enter_context(core.CoherentFile(args.main/row[key]))
                           for row in proof_doc['files'] for key in ('path','reference_path')}
            result = mod.qualify_driver_sources(stack.enter_context(core.CoherentFile(proof)),
                source_snaps, stack.enter_context(core.CoherentFile(compiler)))
            save(args.out/'driver-source-witness.json',result)
        observations.append({'name':'actual-reference-forwarding-source-and-compiler-pins','outcome':'pass'})
        map_name = '/owned/synthetic-link.map'
        for name, argv in [
            ('canonical-wl',['clang','-Wl,-map,'+map_name,'-Wl,-why_load']),
            ('canonical-xlinker',['clang','-Xlinker','-map','-Xlinker',map_name,'-Xlinker','-why_load']),
            ('mixed-canonical',['clang','-Wl,-map,'+map_name,'-Xlinker','-why_load']),
            ('unrelated-forwarding',['clang','-Wl,-alias_list,/owned/alias.exp','-Wl,-map,'+map_name,'-Wl,-why_load']),
        ]:
            assert mod.driver_diagnostic_operands(argv,map_name) == ['-map',map_name,'-why_load']
            observations.append({'name':name,'outcome':'pass','expected':'source-derived-subset-only'})
        for name, argv in [
            ('missing-map',['clang','-Wl,-why_load']),
            ('missing-why',['clang','-Wl,-map,'+map_name]),
            ('duplicate-map',['clang','-Wl,-map,'+map_name,'-Wl,-map,'+map_name,'-Wl,-why_load']),
            ('duplicate-why',['clang','-Wl,-map,'+map_name,'-Wl,-why_load','-Wl,-why_load']),
            ('reordered',['clang','-Wl,-why_load','-Wl,-map,'+map_name]),
            ('wrong-map',['clang','-Wl,-map,/forged','-Wl,-why_load']),
            ('comma-in-map',['clang','-Wl,-map,'+map_name+',forged','-Wl,-why_load']),
            ('coalesced-diagnostics',['clang','-Wl,-map,'+map_name+',-why_load']),
            ('native-map',['clang','-map',map_name,'-Wl,-why_load']),
            ('native-why',['clang','-Wl,-map,'+map_name,'-why_load']),
            ('response-file',['clang','@unmeasured.rsp','-Wl,-map,'+map_name,'-Wl,-why_load']),
            ('xlinker-missing-value',['clang','-Xlinker']),
            ('xlinker-nonadjacent',['clang','-Xlinker','-map','unmeasured.o','-Xlinker',map_name,'-Wl,-why_load']),
            ('xlinker-wrong-path',['clang','-Xlinker','-map','-Xlinker','forged','-Wl,-why_load']),
            ('no-demangle-rewrite',['clang','-Wl,--no-demangle,-map,'+map_name,'-Wl,-why_load']),
        ]:
            try:mod.driver_diagnostic_operands(argv,map_name)
            except ValueError as exc:
                observations.append({'name':name,'outcome':'pass','expected':'reject','reason':str(exc)})
            else:raise AssertionError('Expected forwarding rejection: '+name)
        archive = args.main/'worktrees/krn-025-20261105/artifacts/xnu-cc-kext/controls-session2/resource-positive/lib/darwin/libclang_rt.cc_kext_ios.a'
        catalog_path = archive.parents[3]/'archive-members.json'
        catalog = json.loads(catalog_path.read_text())
        def case(name, mutation=None, rejected=False, empty=False):
            directory=args.out/name;directory.mkdir()
            image=directory/'synthetic-image';image.write_bytes(image_bytes())
            map_path=directory/'synthetic-map';objects_path=directory/'synthetic-objects.json'
            filelist=directory/'synthetic-filelist';obj=directory/'synthetic-filelist.o';tail=directory/'synthetic-tail.o'
            obj.write_bytes(b'synthetic staged object; no actual build credit')
            tail.write_bytes(b'synthetic direct tail; no actual build credit')
            filelist.write_text(str(obj)+'\n')
            rows=[f'# Path: {image}','# Arch: arm64','# Object files:','[  0] linker synthesized',
                '[  1] '+(str(obj) if empty else str(archive)+'('+catalog[2]['name']+')'),
                '# Sections:','# Address\tSize    \tSegment\tSection',
                f'0x{PC:08X}\t0x00000010\t__TEXT\t__text','# Symbols:',
                '# Address\tSize    \tFile  Name',f'0x{PC:08X}\t0x00000004\t[  0] __start',
                f'0x{PC+4:08X}\t0x00000004\t[  1] ___divtc3']
            argv=[str(compiler),'-filelist',str(filelist),str(tail),'-resource-dir',str(archive.parents[2]),
                  '-lcc_kext','-o',str(image),'-Wl,-map,'+str(map_path),'-Wl,-why_load']
            document={'schema':'avf-guest-link-object-list-v2','command_kind':'clang-driver',
                'source_only':False,'actual_driver_argv':argv,
                'derived_linker_operands':{'kind':'forwarded-driver-operands-only',
                    'argv':mod.diagnostic_options(str(map_path)),
                    'source_proof':{'path':str(proof),'sha256':mod.DRIVER_SOURCE_SHA256}},
                'filelists':[{'path':str(filelist),'sha256':digest(filelist),'ordered_object_paths':[str(obj)]}],
                'objects':[{'id':'control/filelist.o','path':str(obj),'sha256':digest(obj)},
                           {'id':'control/tail.o','path':str(tail),'sha256':digest(tail)}],
                'archives':[{'role':'runtime','path':str(archive),'sha256':mod.LINEAGE['runtime_archive_sha256'],
                    'members':[dict(ordinal=n,name=r['name'],sha256=r['sha256']) for n,r in enumerate(catalog)]}]}
            contract={'schema':'avf-runtime-linkmap-contract-v2','command_kind':'clang-driver',
                'selection_scope':'all-observed-live-runtime-members','measurement_origin':'synthetic-control',
                'source_only':False,'lineage':dict(mod.LINEAGE),
                'source_descriptor_sha256':mod.SOURCE_DESCRIPTOR_SHA256,
                'architecture':'arm64','output_path':str(image),'diagnostic_argv':mod.diagnostic_options(str(map_path))}
            if empty:
                contract['atom_queries']=[{'object_path':str(obj),'name':'___divtc3'}]
            state={'contract':contract,'document':document,'rows':rows,'filelist':filelist,'omit_source':False,'omit_filelist':False}
            if mutation:mutation(state)
            map_path.write_text('\n'.join(state['rows'])+'\n');save(objects_path,document)
            paths={'image':image,'map':map_path,'archive':archive,'catalog':catalog_path,
                   'object_list':objects_path,'driver_source':proof}
            contract['bindings']={key:{'path':str(path),'sha256':digest(path)} for key,path in paths.items()}
            save(directory/'contract.json',contract)
            try:
                with ExitStack() as stack:
                    image_snap,view=stack.enter_context(core.macho_snapshot(image,image=True))
                    snaps={key:stack.enter_context(core.CoherentFile(path)) for key,path in paths.items() if key!='image'}
                    file_snap=stack.enter_context(core.CoherentFile(filelist))
                    result=mod.validate(image_snap,view,contract,map_snapshot=snaps['map'],
                        archive_snapshot=snaps['archive'],catalog_snapshot=snaps['catalog'],
                        object_list_snapshot=snaps['object_list'],
                        driver_source_snapshot=None if state['omit_source'] else snaps['driver_source'],
                        filelist_snapshots={} if state['omit_filelist'] else {str(filelist):file_snap})
                if rejected:raise AssertionError('Expected driver contract rejection: '+name)
                assert result['schema']=='avf-runtime-linkmap-witness-v2'
                assert not result['product_authority'] and not result['observed_linker_child_argv_claimed']
                assert not result['actual_execution_authenticated'] and not result['qualified_for_actual_selection']
                assert result['selected_live_member_ordinals']==([] if empty else [2])
                assert result['empty_runtime_selection'] is empty
                if empty:
                    assert result['queried_live_atoms']==[{'query_index':0,'object_path':str(obj),
                        'file_id':1,'name':'___divtc3','address':PC+4,'size':4}]
                    assert result['queried_atom_qualification'] is False
                if not empty:
                    assert result['selected_member_symbols'][0]==dict(ordinal=2,name=catalog[2]['name'],
                        sha256=catalog[2]['sha256'],defined=catalog[2]['defined'],undefined=catalog[2]['undefined'])
                save(directory/'witness.json',result)
                observations.append({'name':name,'outcome':'pass','expected':'unqualified-driver-byte-facts'})
            except ValueError as exc:
                if not rejected:raise
                observations.append({'name':name,'outcome':'pass','expected':'reject','reason':str(exc)})
        case('synthetic-driver-real287-all-selected')
        case('synthetic-driver-legally-empty-selection',empty=True)
        for name, mutation in [
            ('claimed-observed-ld-argv',lambda s:s['document'].update(actual_link_argv=['forged-ld'])),
            ('wrong-command-kind',lambda s:s['document'].update(command_kind='direct-linker')),
            ('caller-convenient-selection',lambda s:s['contract'].update(selection_scope='caller-selected-subset')),
            ('optional-required-missing',lambda s:s['contract'].update(required_members=[286])),
            ('wrong-driver-proof',lambda s:s['document']['derived_linker_operands']['source_proof'].update(sha256='0'*64)),
            ('projection-labeled-actual',lambda s:s['document']['derived_linker_operands'].update(kind='observed-child-argv')),
            ('forged-projection',lambda s:s['document']['derived_linker_operands']['argv'].append('-invented')),
            ('missing-driver-source-snapshot',lambda s:s.update(omit_source=True)),
            ('missing-filelist-snapshot',lambda s:s.update(omit_filelist=True)),
            ('forged-filelist-hash',lambda s:s['document']['filelists'][0].update(sha256='0'*64)),
            ('forged-filelist-expansion',lambda s:s['document']['filelists'][0].update(ordered_object_paths=['/forged.o'])),
            ('duplicate-filelist',lambda s:s['document']['filelists'].append(s['document']['filelists'][0])),
            ('object-order',lambda s:s['document']['objects'].reverse()),
            ('unbound-direct-tail',lambda s:s['document']['actual_driver_argv'].__setitem__(3,'/unmeasured.o')),
            ('wrong-actual-filelist-operand',lambda s:s['document']['actual_driver_argv'].__setitem__(2,'/forged-filelist')),
            ('unknown-atom-query',lambda s:s['contract'].update(atom_queries=[{'object_path':'/unadmitted.o','name':'local'}])),
            ('duplicate-atom-query',lambda s:s['contract'].update(atom_queries=[{'object_path':s['document']['objects'][0]['path'],'name':'local'}]*2)),
            ('excess-atom-queries',lambda s:s['contract'].update(atom_queries=[{'object_path':s['document']['objects'][0]['path'],'name':'local'+str(i)} for i in range(513)])),
        ]:case(name,mutation,True)
        evidence.update(outcome='pass',summary=f'PASS {len(observations)} focused driver/filelist/all-observed runtime selection controls; no target invocation or actual runtime credit',
            source_sha256=digest(source),core_source_sha256=digest(core_path),
            control_source_sha256=digest(Path(__file__)),driver_source_descriptor_sha256=digest(proof))
        exit_code=0
    except BaseException as exc:
        evidence['failure']=str(exc);(args.out/'failure.txt').write_text(traceback.format_exc())
    finally:
        evidence.update(elapsed_seconds=time.monotonic()-started,mem_available_samples=samples,
            vmhwm_bytes=next(int(line.split()[1])*1024 for line in Path('/proc/self/status').read_text().splitlines() if line.startswith('VmHWM:')),
            children_after=Path('/proc/self/task/'+str(os.getpid())+'/children').read_text().strip())
        evidence['commands'][0]['exit_code']=exit_code
        paths=sorted(p for p in args.out.rglob('*') if p.is_file())
        evidence['artifacts']=[str(p.relative_to(args.main)) for p in paths]
        evidence['artifact_bindings']=[{'path':str(p.relative_to(args.main)),'sha256':digest(p)} for p in paths]
        save(args.out/'evidence.json',evidence)
        print(json.dumps({'outcome':evidence['outcome'],'controls':len(observations),
            'vmhwm_bytes':evidence['vmhwm_bytes'],'failure':evidence.get('failure')}))
    return exit_code


if __name__=='__main__':sys.exit(main())
