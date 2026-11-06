"""Bind serializer-only continuation to actual root92 outputs. No tools run."""
import copy
import hashlib
import json
from pathlib import Path
W=Path(__file__).resolve().parents[3];M=W.parents[1];A=W/'artifacts/e1s-development-link-metadata';B=W/'fixtures/public/e1s-development-link-metadata'
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def prepare():
 oldpath=A/'prepare-1/execution-plan.json'
 if sha(oldpath)!='6ba4e3f893d2bcdeddb2577ed88c3ffe21d56c8375ded8ff422b7df92cc07bf7':raise ValueError('Changed original plan')
 plan=json.loads(oldpath.read_text());old=Path(plan['actual_output']);out=A/'generate-2'
 assessment=A/'review-001/assessment.json'
 if sha(assessment)!='9392f5e75383e72e2074fe6697dec6095f4fff447a841f4401db5f83c1594771':raise ValueError('Changed actual partial assessment')
 observed=json.loads(assessment.read_text())
 if observed['actual_whole_outcome']!='fail' or observed['scoped_generation_outcome']!='pass':raise ValueError('Actual wholeFAIL scope required')
 pins=plan['input_sha256']
 def pin(p,expected=None):
  p=Path(p);digest=sha(p)
  if expected is not None and digest!=expected:raise ValueError('Changed actual input: '+str(p))
  pins[str(p)]=digest
 pin(oldpath);pin(assessment);pin(observed['actual_raw']['path'],observed['actual_raw']['sha256'])
 partial=B/'partial-generated-001.json';pin(partial,'daa5a924bf3dc77bba52f93d0eeb5ec36eebb56b452202f74c5c0b7d7a01190c')
 actual=json.loads(partial.read_text());adopted={}
 for row in actual['genuine_source_products'].values():pin(row['path'],row['sha256']);adopted[row['path']]=row['sha256']
 for row in actual['positive_control_products']:pin(row['path'],row['sha256']);adopted[row['path']]=row['sha256']
 source=A/'libplist-source-2.6.0';sources=json.loads((source/'sources.json').read_text())
 if sources['upstream_commit']!='2117b8fdb6b4096455bd2041a63e59a028120136':raise ValueError('Changed exact libplist source')
 pin(source/'sources.json')
 for row in sources['files']:pin(row['path'],row['sha256'])
 def rebase(value):
  return value if value in adopted else value.replace(str(old),str(out))
 commands=copy.deepcopy(plan['commands'][23:])
 for c in commands:
  c['argv']=[rebase(v) for v in c['argv']];c['cwd']=str(out);c['outputs']=[rebase(v) for v in c['outputs']]
  c['phase']='serializer';c['expected_rejection']=c['id'].startswith('reject-')
  if c['expected_rejection']:
   c['rejected_output']=c['argv'][c['argv'].index('-o')+1]
   if c['id']=='reject-unknown-format':
    c['accepted_exit_codes']=[0];c['rejection_kind']='argument-rejected'
    c['required_log_prefix']='ERROR: Unsupported output format\nUsage: plistutil [OPTIONS] [-i FILE] [-o FILE]\n'
    c['required_usage_lines']=['Convert a plist FILE between binary, XML, JSON, and OpenStep format.','  -f, --format FORMAT  Force output format, regardless of input type']
   else:
    c['accepted_exit_codes']=[3];c['rejection_kind']='parse-rejected'
    c['required_log_exact']='ERROR: Could not parse plist data (-3)\n'
 plan.update(schema='e1s-development-link-metadata-serializer-plan-v1',actual_output=str(out),commands=commands,setup=[],
  expected_products=[p for c in commands for p in c['outputs']],typed_tree_equalities=[[rebase(p) for p in row] for row in plan['typed_tree_equalities']],
  phases={'serializer':14},binary_products=[str(old/'serializer-controls/types.bin'),str(out/'kernel/symbolsets.plist')],
  adopted=dict(actual_experiment='STR032META-001',whole_parent_outcome='fail',raw=observed['actual_raw'],scoped_assessment=dict(path=str(assessment),sha256=sha(assessment)),
   genuine_products=actual['genuine_source_products'],positive_control_products=actual['positive_control_products'],no_successful_prefix_replay=True),
  forbidden_generator_scripts=['generate_linker_exports.sh','generate_linker_aliases.sh','newvers.pl','generate_symbolset_plist.sh','generate_combined_symbolsets_plist.sh'])
 plan['serializer']['negative_policy']='Parse: exact exit3+exact diagnostic+no output. Unknown format: exact rawexit0+argument diagnostic/usage+no output; explicit expected_rejection, never conversion success.'
 for p,d in pins.items():
  if sha(p)!=d:raise ValueError('Changed input: '+p)
 if len(commands)!=14 or len(plan['expected_products'])!=11 or len(adopted)!=23:raise ValueError('Unexpected continuation shape')
 if any(any(v.endswith(s) for v in c['argv'] for s in plan['forbidden_generator_scripts']) for c in commands):raise ValueError('Generator replay forbidden')
 return plan
if __name__=='__main__':
 p=A/'prepare-3/execution-plan.json'
 with p.open('x') as f:f.write(json.dumps(prepare(),indent=2)+'\n')
 print(json.dumps(dict(plan=str(p),sha256=sha(p))))
