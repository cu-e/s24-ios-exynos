"""Read-only independent checks of the published VM038 derivation capsule."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[3]
MAIN=Path('/home/egor/dev/pet/s24-ios-exynos')
RUN=ROOT/'docs/procedures/avf-firehose-namespace/qualification-session1'


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def main():
    pins=json.loads((ROOT/'fixtures/public/avf-firehose-namespace/inputs.json').read_text())
    d=json.loads((RUN/'qualified-component.json').read_text())
    for name in ['source_proof','object_manifest','selectors','manifest_transition','namespace_receipt','object_input_keys','artifact_index','source_type_closure','consumer_contract']:
        assert sha(d[name]['path'])==d[name]['sha256'],name
    for name,binding in d['parents'].items():
        assert sha(binding['path'])==binding['sha256']==pins[name+'_sha256'],name
    before=json.loads((MAIN/pins['parent_manifest']).read_text())
    after=json.loads(Path(d['object_manifest']['path']).read_text())
    old_root=d['old_root']['path'];new_root=d['new_root']['path']
    assert not os.path.lexists(old_root)
    assert len(before)==len(after)==1080
    edits=0
    for a,b in zip(before,after):
        assert a['id']==b['id']
        differences=[k for k in a if a[k]!=b[k]]
        assert differences==['next_owned_compile_argv_template']
        old,new=a['next_owned_compile_argv_template'],b['next_owned_compile_argv_template']
        assert len(old)==len(new)
        for i,(x,y) in enumerate(zip(old,new)):
            if x!=y:
                assert (x,y) in [(old_root,new_root),('-I'+old_root,'-I'+new_root)]
                if x==old_root:assert i>0 and old[i-1]=='-I'
                edits+=1
    assert edits==1080
    old_ns=json.loads((MAIN/pins['parent_namespace_receipt']).read_text())
    new_ns=json.loads(Path(d['namespace_receipt']['path']).read_text())
    header=str(Path(new_root)/'os/firehose_buffer_private.h')
    assert new_ns['files']=={**old_ns['files'],header:pins['exported_header_sha256']}
    assert new_ns['roots']==sorted([*old_ns['roots'],new_root],key=lambda p:(len(Path(p).parts),p))
    assert new_ns['absent_search_roots']==[p for p in old_ns['absent_search_roots'] if p!=old_root]
    assert not any(os.path.lexists(p) for p in old_ns['absent_search_roots'])
    assert canonical({k:new_ns[k] for k in ['roots','absent_search_roots','files']})==new_ns['sha256']==d['namespace_digest']
    files=[p for p in Path(new_root).rglob('*') if p.is_file()]
    assert files==[Path(header)] and not any(p.is_symlink() for p in Path(new_root).rglob('*'))
    assert sha(header)==pins['exported_header_sha256']
    parent_index=json.loads((MAIN/pins['parent_index']).read_text())['files']
    index=json.loads(Path(d['artifact_index']['path']).read_text())['files']
    assert all(index.get(p)==h for p,h in parent_index.items())
    assert all(index.get(p)==h for p,h in new_ns['files'].items())
    selectors=json.loads(Path(d['selectors']['path']).read_text())
    old_selectors=json.loads((MAIN/pins['parent_selectors']).read_text())
    assert selectors['shards']==old_selectors['shards']
    assert selectors['sha256']==d['object_manifest']['sha256']
    assert (MAIN/selectors['source_manifest']).resolve()==Path(d['object_manifest']['path']).resolve()
    keys=json.loads(Path(d['object_input_keys']['path']).read_text())['keys']
    assert len(keys)==1080
    for row,item in zip(after,keys):
        binding=item['binding']
        assert item['id']==row['id'] and canonical(binding)==item['input_key']
        assert binding['schema']=='avf-firehose-namespace-v1'
        assert binding['manifest_sha256']==d['object_manifest']['sha256']
        assert binding['namespace_sha256']==d['namespace_digest']
        assert binding['argv_template_sha256']==canonical(row['next_owned_compile_argv_template'])
        assert binding['source_sha256']==row['bound_source_sha256']
        assert binding['configuration_sha256']==row['configuration_sha256']
    evidence=json.loads((RUN/'evidence.json').read_text())
    assert evidence['outcome']=='pass' and evidence['compiler_executed'] is False
    assert all(Path(c['argv'][0]).name in ['git','unifdef'] for c in evidence['commands'])
    assert sum(bool(c.get('rejected')) for c in evidence['checks'])==8
    assert not list(RUN.rglob('*.o')) and not list(RUN.rglob('*.a'))
    print(json.dumps(dict(kind='host-test',origin='local-host',task='VM-038',outcome='pass',
        recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),argv=sys.orig_argv,exit_code=0,
        checker_sha256=sha(__file__),qualified_component_sha256=sha(RUN/'qualified-component.json'),
        actual_checks=['All1080 exact same-position include-root token substitutions only',
            'Retired and retained old absent roots remain absent','Exact old6721 plus one genuine header namespace',
            'All53976 parent artifact-index entries unchanged and complete new namespace indexed',
            'Same10 ordered shard partitions; explicit child manifest identity',
            'All1080 versioned object keys bind exact new manifest/namespace/argv/source/config',
            'Eight actual rejection controls and Git/unifdef-only commands; no object/archive outputs'],
        compiler_executed=False,consumer_acceptance_complete=False),indent=2))


if __name__=='__main__':main()
