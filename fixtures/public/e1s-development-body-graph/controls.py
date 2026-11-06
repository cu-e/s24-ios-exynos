#!/usr/bin/env python3
"""Finite logical mutation controls over actual retained graph identities."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
from compose import Composition, destination


def validate(g):
    if (g['machine'], g['architecture'], g['kernel'], g['platform']) != ('E1S','ARM64','DEVELOPMENT','iPhoneOS'):
        raise ValueError('Wrong native context')
    rows = g['objects']
    expected = [(c+'/'+target, i) for c, info in g['components'].items()
                for i, target in enumerate(info['ordered_OBJS'])]
    if [(r['id'],r['selection_index']) for r in rows] != expected or len({r['id'] for r in rows}) != len(rows):
        raise ValueError('Missing, duplicate, reordered or wrong-index object')
    if len(rows) != g['selected_component_objects'] or g['feature_decision']['BOUND_CHECKS'] != 0:
        raise ValueError('Selection/actual feature decision differs')
    source_root = Path(g['source_root'])
    for r in rows:
        if r['source_kind']=='actual-native-derived-source' and not Path(r['source']).is_relative_to(source_root):
            raise ValueError('Source silently changed to original/foreign context')
    if len(g['direct_tails']) != 4 or len({r['target'] for r in g['direct_tails']}) != 4:
        raise ValueError('Incomplete direct tails')
    constructor = next(r for r in g['direct_tails'] if r['target']=='lastkernelconstructor.o')
    if not constructor['postprocess_tool_binding'] or not any('__LASTDATA_CONST' in x for x in constructor['selected_expanded_steps'].values()):
        raise ValueError('Constructor transformation dropped')


def run(graph):
    g=json.loads(Path(graph).read_text()); validate(g)
    result=[{'case':'actual-native-graph','outcome':'pass'}]
    mutations={
        'wrong-machine':lambda d:d.update(machine='BCM2837'),
        'missing-object':lambda d:d['objects'].pop(),
        'duplicate-object':lambda d:d['objects'].__setitem__(1,d['objects'][0]),
        'wrong-selection-index':lambda d:d['objects'][0].update(selection_index=1),
        'wrong-body-source-root':lambda d:next(r for r in d['objects'] if r['source_kind']=='actual-native-derived-source').update(source='/tmp/original-source.c'),
        'unmeasured-feature-override':lambda d:d['feature_decision'].update(BOUND_CHECKS=1),
        'missing-tail':lambda d:d['direct_tails'].pop(),
        'lost-constructor-transform':lambda d:next(r for r in d['direct_tails'] if r['target']=='lastkernelconstructor.o').update(postprocess_tool_binding=None),
    }
    for name, mutate in mutations.items():
        d=copy.deepcopy(g);mutate(d)
        try:validate(d)
        except ValueError:result.append({'case':name,'outcome':'rejected'})
        else:raise AssertionError('Mutation admitted: '+name)
    with tempfile.TemporaryDirectory(prefix='native-context-controls-') as tmp:
        root=Path(tmp)/'root';root.mkdir();src=Path(tmp)/'source';src.write_bytes(b'actual-owned-byte-witness\n')
        digest=hashlib.sha256(src.read_bytes()).hexdigest();c=Composition(root)
        c.copy(src,digest,'internal/mach/same.h','MIG','internal')
        c.copy(src,digest,'export/mach/same.h','MIG','export')
        assert len(c.files)==2 and {r['mode'] for r in c.files.values()}=={'internal','export'}
        result.append({'case':'same-name-distinct-internal-export-placement','outcome':'pass'})
        cases=[('parent-output-escape',lambda:destination(root,'../escape')),
               ('absolute-output-escape',lambda:destination(root,str(src))),
               ('duplicate-placement',lambda:c.copy(src,digest,'internal/mach/same.h','MIG','internal')),
               ('wrong-producer-bytes',lambda:c.copy(src,'0'*64,'wrong.h','MIG'))]
        (root/'escape').symlink_to(Path(tmp),target_is_directory=True)
        cases.append(('symlink-output-escape',lambda:c.copy(src,digest,'escape/out.h','MIG')))
        for name, fn in cases:
            try:fn()
            except ValueError:result.append({'case':name,'outcome':'rejected'})
            else:raise AssertionError('Mutation admitted: '+name)
        assert not (Path(tmp)/'out.h').exists()
    return {'outcome':'pass','checks':len(result),'cases':result,
            'target_tools_or_queries_executed':False}


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--graph',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();r=run(a.graph);Path(a.out).write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'outcome':r['outcome'],'checks':r['checks']}))
