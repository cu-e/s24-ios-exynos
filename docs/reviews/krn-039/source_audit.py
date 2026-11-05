#!/usr/bin/env python3
"""Pinned initial source ownership audit only; no compiler, fixture or guest."""
import datetime,hashlib,json,os,re,subprocess,sys,traceback
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[3];MAIN=ROOT.parents[1];PIN='c54f35ca767986246321eb901baf8f5ff7923f6a'
ENV={**os.environ,'GIT_NO_LAZY_FETCH':'1','GIT_OPTIONAL_LOCKS':'0','PYTHONDONTWRITEBYTECODE':'1'}
OUT=ROOT/'artifacts/rev-kernel-des/20261106-source1';OUT.mkdir(parents=True,exist_ok=False)
(OUT/'executed-source-audit.py').write_bytes(Path(__file__).read_bytes());commands=[]
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def line(text,needle,start=0):
 at=text.index(needle,start);return text.count('\n',0,at)+1
report=dict(kind='source-review',origin='local-host',outcome='fail',recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),commit=PIN,experiment='REVKDES-001',summary='Initial pinned ESP caller/CBC ownership source audit only; frozen native integration is not yet available and is not accepted',commands=commands,compiler_executed=False,QEMU_executed=False,native_device=False,final_integration_review_complete=False)
try:
 ledger=json.loads((MAIN/'state/lab.json').read_text());experiments=ledger['experiments'];experiments=experiments.values() if isinstance(experiments,dict) else experiments
 plan=next(x for x in experiments if x['id']=='REVKDES-001');assert plan['task']=='REV-022' and plan['owner']=='codex-team-review-kernel-des-20261105-cl' and plan['status']=='planned'
 (OUT/'actual-plan.json').write_text(json.dumps(plan,indent=2)+'\n');sources={};texts={}
 names=['bsd/netinet6/esp_core.c','bsd/netinet6/esp_input.c','bsd/netinet6/esp_output.c','bsd/netinet6/esp.h','bsd/kern/uipc_mbuf.c','bsd/sys/mbuf.h','bsd/sys/errno.h','libkern/crypto/corecrypto_des.c','libkern/libkern/crypto/des.h','libkern/libkern/crypto/crypto_internal.h','EXTERNAL_HEADERS/corecrypto/ccmode.h','EXTERNAL_HEADERS/corecrypto/ccmode_impl.h','EXTERNAL_HEADERS/corecrypto/ccdes.h']
 for i,name in enumerate(names):
  a=OUT/('source-'+str(i)+'.stdout');b=OUT/('source-'+str(i)+'.stderr');argv=['git','-C',str(MAIN/'references/apple-xnu'),'show',PIN+':'+name]
  with a.open('xb') as f,b.open('xb') as g:r=subprocess.run(argv,cwd=ROOT,env=ENV,stdout=f,stderr=g,timeout=20)
  commands.append(dict(argv=argv,cwd=str(ROOT),exit_code=r.returncode,stdout=str(a.relative_to(MAIN)),stderr=str(b.relative_to(MAIN)),environment_overrides={k:ENV[k] for k in ['GIT_NO_LAZY_FETCH','GIT_OPTIONAL_LOCKS','PYTHONDONTWRITEBYTECODE']}));assert r.returncode==0,name
  raw=a.read_bytes();assert sha(MAIN/'references/apple-xnu'/name)==hashlib.sha256(raw).hexdigest();p=OUT/'selected-xnu'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw);texts[name]=raw.decode();sources[name]=dict(sha256=sha(p),bytes=len(raw))
 core=texts['bsd/netinet6/esp_core.c'];facts=[]
 for function,callback,next_function in [('esp_cbc_decrypt','blockdecrypt','esp_cbc_encrypt'),('esp_cbc_encrypt','blockencrypt','esp_auth')]:
  start=core.index('\n'+function+'(');end=core.index('\n'+next_function+'(',start+1);body=core[start:end];block='(*algo->'+callback+')(algo, sav, sp, mtod(d, u_int8_t *) + dn);'
  assert body.count(block)==1
  allocation='sbuf = (u_int8_t *)kalloc_data(blocklen, Z_NOWAIT);\n\tif (sbuf == NULL) {\n\t\treturn ENOBUFS;\n\t}'
  assert allocation in body
  assert 'm_freem(m);\n\t\t\t\tif (d0) {\n\t\t\t\t\tm_freem(d0);\n\t\t\t\t}' in body and 'result = ENOBUFS;\n\t\t\t\tgoto end;' in body
  assert body.index('bzero(iv, sizeof(iv));')<body.index('\nend:') and body.index('bzero(sbuf, blocklen);')<body.index('\nend:')
  assert 'm_freem(scut->m_next);\n\tscut->m_len = scutoff;\n\tscut->m_next = d0;' in body
  facts.append(dict(function=function,source='bsd/netinet6/esp_core.c',callback_ignored_line=line(core,block,start),sbuf_allocation_line=line(core,allocation,start),success_splice_line=line(core,'m_freem(scut->m_next);',start),scrub_line=line(core,'bzero(iv, sizeof(iv));',start),end_label_line=line(core,'\nend:',start)+1,nonzero_callback_observed=False,sbuf_null_consumes_input=False,destination_failure_scrubs_local_iv_and_sbuf=False))
 inp=texts['bsd/netinet6/esp_input.c'];out=texts['bsd/netinet6/esp_output.c'];mb=texts['bsd/kern/uipc_mbuf.c'];wrappers=texts['libkern/crypto/corecrypto_des.c']
 assert inp.count('/* m is already freed */\n\t\tm = NULL;')==2 and '/* m is already freed */' in out
 assert 'return ecb->ecb(ctx, 1, in, out);' in wrappers and 'return dec->init(dec, ks->dec, CCDES_KEY_SIZE, key);' in wrappers
 assert 'struct mbuf *n = m->m_next;' in mb and 'panic("m_free: freeing an already freed mbuf");' in mb and 'while (m != NULL) {\n\t\tm = m_free(m);\n\t}' in mb
 trace=[dict(id='original-sbuf-NULL-input-leak',severity='P2',status='baseline finding sent to producer; final candidate pending',steps=['Admit valid nonempty CBC packet, IV and block alignment.','Fail kalloc_data(blocklen,Z_NOWAIT) for sbuf after IV has been copied.','Both pinned CBC functions return ENOBUFS directly without m_freem(m).','IPv4/IPv6 ESP input explicitly set m=NULL because callback is expected to consume it on nonzero; their bad labels cannot free it. ESP output immediately returns through fail without an additional m free.','Original packet chain remains live and local IV bypasses the later scrub.'],runtime_executed=False),dict(id='original-CBC-destination-failure-scrub-bypass',severity='P2',status='baseline fact; producer had already identified common cleanup need',steps=['After allocating sbuf and reading IV, fail MGET/MCLGET destination admission.','Existing branch frees m and already allocated d0, sets ENOBUFS, then goto end.','Both local bzero calls precede end and are skipped; allocated scratch is passed to kfree_data without the intended scrub.'],runtime_executed=False)]
 (OUT/'source-traces.json').write_text(json.dumps(trace,indent=2)+'\n')
 report.update(outcome='pass',sources=sources,facts=facts,source_counterexamples=trace,ownership=dict(outer_input_consumes_on_error=True,outer_output_consumes_on_error=True,original_and_destination_chains_disjoint_until_success_splice=True,current_destination_can_alias_new_head=True,m_freem_walks_next_and_m_free_rejects_double_free=True,ivp_and_source_pointers_are_borrowed_aliases_not_separate_allocations=True,source_audit_does_not_execute_kernel_mbuf_or_network=True),checks=[dict(name=x,pass_check=True) for x in ['actual-existing-plan-before-audit-children','exact-complete-pinned-Git-source-and-reference-hashes','genuine-outer-consume-on-error-and-inner-status-propagation','specific-NULL-scratch-ownership-counterexample','specific-destination-failure-local-scrub-counterexample','successful-prefix-retention-and-disjoint-new-chain-splice']])
except Exception as error:report.update(error=repr(error),traceback=traceback.format_exc())
report['artifacts']=[str(p.relative_to(MAIN)) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='evidence.json'];report['sha256']={str(p.relative_to(MAIN)):sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='evidence.json'}
(OUT/'evidence.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report.get(k) for k in ['outcome','error','facts','final_integration_review_complete']}));raise SystemExit(report['outcome']!='pass')
