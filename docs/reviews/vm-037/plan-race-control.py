#!/usr/bin/env python3
"""Schedule one real atomic plan replacement between checksum and JSON parse."""
import importlib.util,json,os,sys,tempfile
from pathlib import Path
from unittest.mock import patch
sys.dont_write_bytecode=True
here=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('frozen_budget_race',here/'original-helper-39f68b5.py');e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)
with tempfile.TemporaryDirectory(prefix='plan-race-',dir=here) as directory:
 root=Path(directory);plan=root/'plan.json';replacement=root/'replacement.json'
 old={'resource_profile':e.PROJECT_PROFILE,'source_plan_identity':'approved-original'}
 new={'resource_profile':e.PROJECT_PROFILE,'source_plan_identity':'unapproved-replacement'}
 plan.write_text(json.dumps(old));replacement.write_text(json.dumps(new));expected=e.sha(plan);original=e.sha
 def checksum(path):
  digest=original(path)
  if Path(path)==plan:os.replace(replacement,plan)
  return digest
 with patch.object(e,'sha',side_effect=checksum):parsed=e.load(plan,expected)
 report={'kind':'host-test','origin':'synthetic-local-resource-controls','outcome':'pass' if parsed==old else 'fail','helper_sha256':e.sha(e.__file__),'expected_sha256':expected,'parsed_json':parsed,'approved_json':old,'actual_file_sha256_after':e.sha(plan),'method':'Mocked checksum callback only schedules actual atomic os.replace after genuine checksum; actual production load function parses the path afterward.','compiler_guest_common_started':False}
 (here/'initial-plan-race-control.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report))
sys.exit(0 if report['outcome']=='pass' else 1)
