#!/usr/bin/env python3
"""Qualify bounded source facts, not nonce increment semantics or an implementation."""
import argparse, copy, datetime, hashlib, json, os, re, subprocess, sys
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
import http.client
from audit import APPLE,XNU,HEADER,minimal_facts,git_blob,sha

UNKNOWN=['byte_encoding','incremented_byte_range','increment_byte_order','overflow_result',
         'overflow_nonce_mutation','permitted_lifecycle_states','state_after_increment','selected_success_behavior']
EXPECTED_SELECTED='583085c5a52979eb28bdec94a69d00b4c3536034c8f9763de9de1bb1101e0a93'
CURRENT_SOURCE='ccchacha20poly1305/src/ccchacha20poly1305.c'

def dump(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def verify_manifest(m):
    if m['selected_profile']['revision']!=XNU or m['selected_profile']['header_sha256']!=EXPECTED_SELECTED:
        raise ValueError('Wrong selected source/profile identity')
    if m['method']!='ccchacha20poly1305_incnonce':raise ValueError('Different API cannot establish this method contract')
    if m['nonce_bytes']!=12:raise ValueError('Changed selected declaration fact')
    if m['qualified_nonce_contract'] is not False or any(m['increment_contract'][key] is not None for key in UNKNOWN):
        raise ValueError('No applicable primary increment evidence supports promoting unknown facts')
    if m['current_official_placeholder']['revision']!=APPLE or m['current_official_placeholder']['git_blob']!='96e59142ea805fc98b297b83dbd9c20dd502486e':
        raise ValueError('Changed official availability source identity')
    if not m['current_official_placeholder']['only_explicit_return_is_one']:
        raise ValueError('Unavailable placeholder cannot become a working increment contract')
    if m['selected_version_compatibility_established'] is not False:raise ValueError('Historical/newer signature equality is not selected implementation compatibility')
    return True

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--main-root',type=Path,required=True);p.add_argument('--acquisition',type=Path);p.add_argument('--run');p.add_argument('--verify',type=Path)
    a=p.parse_args()
    if a.verify:
        value=json.loads(a.verify.read_text());verify_manifest(value);print(json.dumps({'manifest_verified':True,'qualified_nonce_contract':False}));return 0
    if not a.run or not a.acquisition or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}',a.run):p.error('fresh --run and --acquisition required')
    mainroot=a.main_root.resolve();wt=Path(__file__).resolve().parents[3];out=wt/'artifacts/chacha-nonce-contract'/a.run;out.mkdir(parents=True,exist_ok=False)
    env=dict(os.environ,GIT_NO_LAZY_FETCH='1',GIT_OPTIONAL_LOCKS='0')
    rel=lambda path:str(Path(path).resolve().relative_to(mainroot))
    report={'kind':'source-review','origin':'local-host','outcome':'fail','recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'summary':'Source-qualified bounded missing ChaCha nonce increment contract; no implementation or compatibility guess',
            'commands':[],'http':[],'checks':[],'controls':[],'restricted_bodies_retained':False,'compiler_executed':False,'device_executed':False}
    def check(n,b):
        report['checks'].append({'name':n,'passed':bool(b)})
        if not b:raise ValueError(n)
    try:
        base=json.loads(a.acquisition.read_text());check('passing-exact-acquisition',base['outcome']=='pass' and base['restricted_bodies_retained'] is False)
        report['acquisition']={'path':rel(a.acquisition),'sha256':sha(a.acquisition.read_bytes())}
        expected={s['path']:s for s in base['sources'] if s['revision']==APPLE}
        refreshed=[]
        for path in [CURRENT_SOURCE,'ccchacha20poly1305/crypto_test/crypto_test_chacha.c','ccchacha20poly1305/crypto_test/crypto_test_chacha20poly1305_runner.c']:
            wanted=expected[path];url=wanted['url']+'?availability-correction=complete';record={'url':url,'method':'GET'};report['http'].append(record)
            # Canonical identities are mandatory; no raw body is persisted.
            with urlopen(Request(url,headers={'User-Agent':'S24-nonce-contract-facts','Accept-Encoding':'identity'}),timeout=20) as response:
                data=response.read(2*1024*1024+1);length=response.headers.get('Content-Length')
                check('complete-response-'+path,len(data)<=2*1024*1024 and (length is None or int(length)==len(data)))
                check('exact-canonical-source-'+path,git_blob(data)==wanted['git_blob'] and sha(data)==wanted['sha256'])
                facts=minimal_facts(data,path);facts['all_incnonce_substring_occurrences']=data.decode('utf-8').count('incnonce')
                record.update(status=response.status,bytes=len(data),content_length=length,git_blob=git_blob(data),sha256=sha(data))
                refreshed.append({'path':path,'revision':APPLE,'git_blob':git_blob(data),'sha256':sha(data),'bytes':len(data),'facts':facts})
        availability=refreshed[0]['facts']['incnonce_availability']
        check('actual-only-explicit-return-one-no-nonce-context-access',availability['only_explicit_return_is_one'] and not availability['context_argument_access'] and not availability['nonce_argument_access'])
        check('both-named-tests-have-no-increment-reference',all(s['facts']['all_incnonce_substring_occurrences']==0 for s in refreshed[1:]))
        report['refreshed_minimal_facts']=refreshed
        # Selected named source surfaces only; all original bytes remain read-only.
        paths=[HEADER,'libkern/crypto/corecrypto_chacha20poly1305.c','libkern/libkern/crypto/chacha20poly1305.h','libkern/libkern/crypto/register_crypto.h','bsd/netinet6/esp_chachapoly.c']
        surfaces=[]
        for path in paths:
            source=mainroot/'artifacts/xnu-prepare/e1s-dependency-source-session1/xnu'/path;data=source.read_bytes();text=data.decode()
            argv=['git','-C',str(mainroot/'references/apple-xnu'),'ls-tree',XNU,path]
            result=subprocess.run(argv,env=env,capture_output=True,timeout=10)
            record={'argv':argv,'exit_code':result.returncode,'stdout_sha256':sha(result.stdout),'stderr_sha256':sha(result.stderr)}
            report['commands'].append(record)
            check('selected-named-tree-'+path,result.returncode==0 and git_blob(data) in result.stdout.decode())
            surfaces.append({'path':path,'revision':XNU,'git_blob':git_blob(data),'sha256':sha(data),'bytes':len(data),
                             'incnonce_substring_occurrences':text.count('incnonce'),'setnonce_substring_occurrences':text.count('setnonce'),
                             'incnonce_named_documentation':bool(re.search(r'@function\s+ccchacha20poly1305_incnonce\b',text))})
        report['selected_surfaces']=surfaces
        check('selected-esp-does-not-use-increment-method',surfaces[-1]['incnonce_substring_occurrences']==0 and surfaces[-1]['setnonce_substring_occurrences']>0)
        historical=[s for s in base['sources'] if 'tag' in s]
        check('three-named-historical-official-headers',len(historical)==3 and all(s['facts']['incnonce_token_occurrences']==1 and not s['facts']['incnonce_named_documentation'] and s['facts']['nonce_macro_12_bytes'] for s in historical))
        check('official-published-refs-are-one-current-root',base['official_public_refs']['exit_code']==0 and {line[0] for line in base['official_public_refs']['refs']}=={APPLE} and base['official_current_commit']['sha']==APPLE and base['official_current_commit']['parents']==[])
        manifest={'schema_version':1,'task':'KRN-037','method':'ccchacha20poly1305_incnonce',
                  'selected_profile':{'revision':XNU,'header_path':HEADER,'header_sha256':EXPECTED_SELECTED},
                  'nonce_bytes':12,'mutable_nonce_parameter_declared':True,'int_result_declared':True,
                  'qualified_nonce_contract':False,'selected_version_compatibility_established':False,
                  'increment_contract':{key:None for key in UNKNOWN},
                  'current_official_placeholder':{'revision':APPLE,'path':CURRENT_SOURCE,'git_blob':refreshed[0]['git_blob'],'sha256':refreshed[0]['sha256'],'only_explicit_return_is_one':True,'unconditional_guard_semantics_claimed':False,'context_or_nonce_argument_access':False},
                  'primary_sources':[base['selected_header'],*base['sources']],
                  'selected_surfaces':surfaces,'official_public_refs':base['official_public_refs'],
                  'official_current_parent_count':0,'historical_official_header_tags':[s['tag'] for s in historical],
                  'named_historical_archive_attempts':[r for r in base['http'] if r['method']=='HEAD'],
                  'noncoverage':['No claim of exhaustive historical Apple delivery archive availability.','No archive download or agreement submission.','No third-party mirror implementation treated as authoritative.','No GCM/RFC/high-level CryptoKit analogy establishes the private increment method.'],
                  'missing_external_contract':'Applicable primary selected-version evidence for incremented bytes/order,overflow/error/mutation and permitted state transition semantics;or a provenance-qualified implementation/test contract usable within project restrictions.',
                  'restricted_bodies_retained':False,'implementation_authored':False,'all_ten_callback_acceptance_qualified':False}
        # Replace only the availability classifier observation with corrected facts;
        # retain original acquisition JSON/bytes and correction provenance separately.
        for s in manifest['primary_sources']:
            if s['revision']==APPLE and s['path']==CURRENT_SOURCE:s['facts']=refreshed[0]['facts']
        verify_manifest(manifest);dump(out/'contract-facts.json',manifest)
        def control(name,change):
            altered=copy.deepcopy(manifest);change(altered)
            try:verify_manifest(altered)
            except ValueError as error:report['controls'].append({'name':name,'rejected':True,'reason':str(error)})
            else:raise ValueError('Unsupported promotion accepted:'+name)
        control('changed-selected-source-sha',lambda m:m['selected_profile'].update(header_sha256='0'*64))
        control('newer-official-profile-is-not-selected',lambda m:m['selected_profile'].update(revision=APPLE))
        control('historical-header-is-not-selected',lambda m:m['selected_profile'].update(revision=historical[0]['revision']))
        control('different-GCM-method-cannot-supply-contract',lambda m:m.update(method='ccgcm_inc_iv'))
        control('matching-signature-cannot-imply-compatibility',lambda m:m.update(selected_version_compatibility_established=True))
        control('guessed-little-endian-rejected',lambda m:m['increment_contract'].update(byte_encoding='little-endian'))
        control('guessed-full-nonce-range-rejected',lambda m:m['increment_contract'].update(incremented_byte_range=[0,11]))
        control('guessed-overflow-success-rejected',lambda m:m['increment_contract'].update(overflow_result=0))
        control('borrowed-reset-lifecycle-rejected',lambda m:m['increment_contract'].update(state_after_increment='reset'))
        control('placeholder-cannot-claim-working-contract',lambda m:m.update(qualified_nonce_contract=True))
        control('changed-official-source-blob-rejected',lambda m:m['current_official_placeholder'].update(git_blob='0'*40))
        check('eleven-source-profile-unknown-controls',len(report['controls'])==11)
        report['outcome']='pass';report['nonce_contract_qualified']=False
    except Exception as error:
        # Do not render restricted response contents or implementation excerpts.
        report['error']=type(error).__name__+': '+str(error)
    report['commit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=wt,env=env,text=True).strip()
    report['tools_sha256']={str(Path(p).resolve()):sha(Path(p).resolve().read_bytes()) for p in [sys.executable,'/usr/bin/git']}
    report['owned_sources_sha256']={rel(Path(__file__)):sha(Path(__file__).read_bytes()),rel(Path(__file__).with_name('audit.py')):sha(Path(__file__).with_name('audit.py').read_bytes())}
    dump(out/'report.json',report)
    files=[p for p in out.iterdir() if p.is_file()]
    evidence={k:report[k] for k in ['kind','origin','outcome','recorded_at','summary','commit','commands']}
    evidence.update(artifacts=[rel(p) for p in files],sha256={rel(p):sha(p.read_bytes()) for p in files},limitations=['Bounded source facts only;no selected increment contract or all-ten callback acceptance established.','No restricted implementation body retained,compiled,copied or translated.'])
    dump(out/'evidence.json',evidence)
    print(json.dumps({'outcome':report['outcome'],'checks':len(report['checks']),'controls':len(report['controls']),'error':report.get('error'),'evidence':rel(out/'evidence.json')}))
    return report['outcome']!='pass'
if __name__=='__main__':sys.exit(main())
