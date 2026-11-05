#!/usr/bin/env python3
"""Complete recorded console checks after exact unchanged native-source audit."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import time
sys.dont_write_bytecode=True
from intake import HERE, MAIN, OWNER, sha, must, load, rooted, unpack


def main():
    name=sys.argv[1];must(re.fullmatch(r'[A-Za-z0-9_-]+',name),'Invalid run')
    out=HERE/'runs'/name;out.mkdir(parents=True,exist_ok=False)
    parent=HERE/'runs/source1/evidence.json';old=load(parent)
    r=dict(kind='source-review',origin='local-host',outcome='fail',task='INT-003',component='KRN-039',
           recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
           parent=dict(path=str(parent),sha256=sha(parent)),bindings={},admission=[],runtime_controls=[],
           compiler_executed=False,algorithm_replayed=False,guest_executed=False,registry_mutated=False,
           main_published=False,full_kernel_qualified=False,CTS3_native_memory_gate_closed=False)
    try:
        must(old['outcome']=='fail' and old['error']=="ValueError('Missing real caller console')" and
             len(old['actual_strong_selected_providers'])==28 and len(old['runtime_controls'])==1,
             'Exact completed-native/payload-console deferral required')
        for i in range(3):
            n=int(re.search(r'^MemAvailable:\s+(\d+)',Path('/proc/meminfo').read_text(),re.M)[1])
            r['admission'].append(dict(at=datetime.now(timezone.utc).isoformat(),MemAvailable_KiB=n))
            must(n>=4194304,'Readonly continuation deferred below4GiB')
            if i<2:time.sleep(1)
        for path,digest in old['bindings'].items():
            must(sha(path)==digest,'Native/source-stage identity changed: '+path)
        r['revalidated_parent_bindings']=len(old['bindings'])
        r['bindings']={str(parent):sha(parent),str(Path(__file__)):sha(__file__)}
        guest_path=OWNER/'artifacts/kernel-des/caller-guest4/evidence.json'
        guest=load(guest_path);must(sha(guest_path)=='99cb37b8eba4980fecafa596caffbabbd14663d61d0e8ae9327120187892aff4','Actual CPU receipt changed')
        locations=guest['negative_expected_locations'];files={}
        for path,digest in guest['sha256'].items():files.setdefault(digest,[]).append(rooted(path))
        supervisors=[]
        for case in guest['guest_cases']:
            image=rooted(case['image'])
            payload=next(p for p in files[case['payload_sha256']] if p.suffix=='.xnup')
            console=next(p for p in files[case['console_sha256']] if p.suffix=='.log')
            must(unpack(payload)['kernel']==image.read_bytes(),'Actual payload/image changed')
            text=console.read_text(errors='replace');label=case['case']
            mapped='KDES MAPPED' in text;off='XTS SYNTHETIC PSCI_SYSTEM_OFF' in text
            passed=re.search(r'KDES CALLER PASS vectors=(0x[0-9a-f]+) esp_cases=(0x[0-9a-f]+) checks=(0x[0-9a-f]+) line=0x0',text)
            failed=re.search(r'KDES CALLER FAIL vectors=(0x[0-9a-f]+) esp_cases=(0x[0-9a-f]+) checks=(0x[0-9a-f]+) line=(0x[0-9a-f]+)',text)
            if label=='positive':
                ok=mapped and off and passed and not failed and tuple(int(passed[i],16)for i in [1,2,3])==(1964,120,47520)
            elif label=='wrong-cookie':
                ok=not mapped and not passed and off and 'XTS SYNTHETIC REJECT command-cookie' in text
            elif label=='corrupt-answer':
                ok=mapped and off and not passed and failed and tuple(int(failed[i],16)for i in [1,2,3,4])==(1,0,16,locations['corrupt_answer_source_line'])
            elif label=='original-caller':
                ok=mapped and off and not passed and 'KDES ESP BASELINE SUCCESS cases=0xc' in text and ('KDES ESP ASSERT line='+hex(locations['original_error_source_line'])+' case=0xd') in text
            elif label=='panic':
                ok=mapped and off and not passed and 'KDES SYNTHETIC PANIC' in text and 'KDES ESP ASSERT' not in text
            elif label=='spin':
                ok=mapped and not off and not passed and 'KDES SPIN CONTROL' in text and case['result']=='timeout'
            else:ok=False
            must(bool(ok) and case['accepted'],'Actual conditional console control failed: '+label)
            r['runtime_controls'].append(dict(case=label,passed=True,console_sha256=sha(console),payload_sha256=sha(payload),image_sha256=sha(image)))
        for raw in guest['sha256']:
            path=rooted(raw)
            if path.suffix=='.json':
                data=load(path)
                if isinstance(data,dict) and 'after' in data and 'argv' in data and 'outcome' in data:
                    after=data['after'];must(after['owned_processes']==[] and after['owned_tree_rss_bytes']==0,'Recorded CPU survivor')
                    supervisors.append(dict(path=str(path),outcome=data['outcome'],elapsed_seconds=data['elapsed_seconds']))
        must(len(supervisors)==6 and len(r['runtime_controls'])==6,'Six complete controls/receipts required')
        q=load(OWNER/'docs/procedures/kernel-des/qualified-evidence.json')
        for key in ['full_provider_startup_executed','full_kernel_qualified','full_crypto_qualified','private_Apple_ABI_qualified','FIPS_qualified','side_channels_qualified','native_device_qualified','kernel_MMU_qualified']:
            must(q[key] is False,'Unqualified promotion: '+key)
        r['actual_strong_selected_providers']=old['actual_strong_selected_providers']
        r['native_contract']=q['native_contract'];r['supervisor_records']=supervisors
        r['outcome']='pass';r['summary']='039 frozen source/object/strong-provider prefix retained with all identities rechecked; all six existing exact payload/console/supervisor contracts pass, no runtime replay'
    except Exception as e:r['error']=repr(e);r['summary']='Read-only039 continuation failed/deferred; no integration acceptance'
    finally:
        r['process_memory']=[x for x in Path('/proc/self/status').read_text().splitlines() if x.startswith(('VmHWM:','VmRSS:'))]
        r['finished_at']=datetime.now(timezone.utc).isoformat(timespec='seconds')
        r['artifacts']=[str(parent.relative_to(MAIN))]
        (out/'evidence.json').write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps({k:r.get(k)for k in ['outcome','summary','error','revalidated_parent_bindings','process_memory']},indent=2))
    return r['outcome']!='pass'


if __name__=='__main__':raise SystemExit(main())
