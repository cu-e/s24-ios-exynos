#!/usr/bin/env python3
"""Once-only STR036 source refusal controls; no target subprocesses."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True

here = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('native_link',here/'native_link.py')
link = importlib.util.module_from_spec(spec); spec.loader.exec_module(link)
out = Path(sys.argv[1]); out.mkdir(exist_ok=False)
checks = []

def reject(name,call):
    try:call()
    except (ValueError,FileNotFoundError,KeyError) as error:
        checks.append(dict(name=name,outcome='pass',rejection=repr(error)))
    else:raise AssertionError('Accepted '+name)

def altered(name,mutate):
    changed = copy.deepcopy(index); mutate(changed)
    reject(name,lambda:link.validate_index(changed,policy,graph,context,overrides))

policy,contract,graph,context,overrides = link.references()
index = link.read(policy['current_reference_index'],True)
actual = link.inspect(policy['current_reference_index'])
assert actual['baseline_accepted'] == 739 and actual['selected_actual_count'] == 740 and len(actual['missing_ids']) == 302
assert actual['ready'] is False and actual['executable_argv'] is None and actual['staging_or_filelists_created'] is False
checks.append(dict(name='Genuine sealed739 snapshot remains incomplete740/302',outcome='pass'))
altered('Duplicate body ID',lambda x:x['rows'].append(copy.deepcopy(x['rows'][0])))
altered('Reordered bodies',lambda x:x['rows'].reverse())
altered('Missing counter/inventory lie',lambda x:x['ABSENT_ids'].pop())
altered('Wrong profile',lambda x:x['portable_compiler_profile'].update(sha256='0'*64))
altered('Source plan is not object authority',lambda x:x['rows'][0]['actual_tuple_authority'].update(format='source-plan'))
altered('Unqualified resources',lambda x:x['rows'][0].update(actual_object_input_resource_qualification='inconclusive'))
altered('Escaped object',lambda x:x['rows'][0]['object'].update(path='/tmp/unowned.o'))
altered('Wrong recipe',lambda x:x['rows'][0]['recipe'].update(sha256='0'*64))
altered('Wrong original source',lambda x:x['rows'][0]['source'].update(sha256='0'*64))
altered('False final override count',lambda x:x.update(final_available_slots_with_overrides=741))
changed = copy.deepcopy(overrides); changed['overrides'].append(changed['overrides'][0])
reject('Duplicate035 overrides',lambda:link.validate_index(index,policy,graph,context,changed))
changed = copy.deepcopy(overrides); changed['overrides'][0]['qualifications']['storage_qualification'] = 'inconclusive'
reject('Unqualified035 storage',lambda:link.validate_index(index,policy,graph,context,changed))
file = out/'binding.json'; file.write_text('{"source":"actual own temporary file"}\n')
sha = hashlib.sha256(file.read_bytes()).hexdigest(); b = dict(path=str(file),sha256=sha)
assert link.read(b,True) == {'source':'actual own temporary file'}
checks.append(dict(name='Same-FD actual temporary JSON positive',outcome='pass'))
reject('Wrong actual file hash',lambda:link.read(dict(b,sha256='0'*64),True))
file.write_text('{"source":"replaced bytes"}\n')
reject('Changed actual bytes',lambda:link.read(b,True))
symlink = out/'alias.json'; symlink.symlink_to(file)
reject('Actual symlink binding',lambda:link.read(dict(path=str(symlink),sha256=hashlib.sha256(file.read_bytes()).hexdigest()),True))
reject('Actual absent file',lambda:link.read(dict(path=str(out/'absent.json'),sha256='0'*64),True))
request = dict(schema='e1s-native-link-request-v1',task='STR-037',owner='unclaimed-not-authority',experiment='not-planned',out='artifacts/forbidden-link-stage',whole_seconds=600,index=policy['current_reference_index'],input_review=b,runtime=b)
p = out/'incomplete-request.json'; p.write_text(json.dumps(request))
reject('Incomplete actual selection refuses BEFORE runtime/owner/staging',lambda:link.make_plan(dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())))
reject('Source task cannot own actual output',lambda:link.own(dict(request,task='STR-036')))
assert not (link.MAIN/'artifacts/forbidden-link-stage').exists()
assert not list(out.rglob('*.filelist'))
report = dict(kind='source-review',outcome='pass',checks=checks,count=len(checks),sealed_snapshot=policy['current_reference_index'],selected_count=740,missing_count=302,executable_argv=None,target_processes_started=0,staging_or_filelists_created=False,source_sha256=hashlib.sha256((here/'native_link.py').read_bytes()).hexdigest(),private37_ABI='OPEN',actual_lifecycle='UNQUALIFIED')
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
