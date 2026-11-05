#!/usr/bin/env python3
"""Source-fact audit only. Restricted source bytes never reach logs or files."""
from __future__ import annotations
import argparse, base64, datetime, hashlib, http.client, json, os, re, subprocess, sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

XNU='c54f35ca767986246321eb901baf8f5ff7923f6a'
APPLE='9612a959abb6eac0aac3ee6a7245c46365c9d81b'
HEADER='EXTERNAL_HEADERS/corecrypto/ccchacha20poly1305.h'
CURRENT_PATHS=[
 'ccchacha20poly1305/corecrypto/ccchacha20poly1305.h',
 'ccchacha20poly1305/corecrypto/ccchacha20poly1305_priv.h',
 'ccchacha20poly1305/corecrypto/ccchacha20poly1305_internal.h',
 'ccchacha20poly1305/src/ccchacha20poly1305.c',
 'ccchacha20poly1305/crypto_test/crypto_test_chacha.c',
 'ccchacha20poly1305/crypto_test/crypto_test_chacha20poly1305_runner.c',
]
TAGS=['xnu-8796.101.5','xnu-8020.121.3','xnu-7195.141.2']

def sha(data):return hashlib.sha256(data).hexdigest()
def git_blob(data):return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
def dump(path,value):path.write_text(json.dumps(value,indent=2)+'\n')
def minimal_facts(data,path):
    """Only interface/availability facts. Never return a body, excerpt or nonce algorithm."""
    text=data.decode('utf-8');symbol='ccchacha20poly1305_incnonce'
    facts={'incnonce_token_occurrences':len(re.findall(r'\b'+symbol+r'\b',text)),
           'incnonce_named_documentation':bool(re.search(r'@function\s+'+symbol+r'\b',text))}
    if path.endswith('.h'):
        facts['mutable_nonce_parameter_declared']=bool(re.search(symbol+r'\([^;]*uint8_t\s*\*[^;]*nonce\s*\)',text,re.S))
        facts['nonce_macro_12_bytes']=bool(re.search(r'#define\s+CCCHACHA20_NONCE_NBYTES\s+12\b',text))
        facts['reset_named_documentation']=bool(re.search(r'@function\s+ccchacha20poly1305_reset\b',text))
        facts['setnonce_named_documentation']=bool(re.search(r'@function\s+ccchacha20poly1305_setnonce\b',text))
    if path.endswith('/src/ccchacha20poly1305.c'):
        match=re.search(r'\bint\s+'+symbol+r'\([^{}]*\)\s*\{',text)
        if match:
            start=match.end();depth=1;end=start
            while depth and end<len(text):
                depth+=(text[end]=='{')-(text[end]=='}');end+=1
            if depth:raise ValueError('Unterminated function; no semantic conclusion')
            body=text[start:end-1]
            body=re.sub(r'/\*.*?\*/|//[^\n]*','',body,flags=re.S)
            facts['incnonce_availability']={
                'function_line':text[:match.start()].count('\n')+1,
                'literal_return_only_body_shape':bool(re.fullmatch(r'\s*return\s+1\s*;\s*',body)),
                'explicit_return_literals':re.findall(r'\breturn\s+(\d+)\s*;',body),
                'only_explicit_return_is_one':re.findall(r'\breturn\s+([^;]+);',body)==['1'],
                'has_guard_macro_token':bool(re.search(r'\bCC_ENSURE_DIT_ENABLED\b',body)),
                'nonce_argument_access':bool(re.search(r'\bnonce\b',body)),
                'context_argument_access':bool(re.search(r'\bctx\b',body)),
            }
    return facts

class Audit:
    def __init__(self,args):
        self.main=args.main_root.resolve();self.wt=Path(__file__).resolve().parents[3]
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}',args.run):raise ValueError('Fresh plain run name')
        self.out=self.wt/'artifacts/chacha-nonce-contract'/args.run;self.out.mkdir(parents=True,exist_ok=False)
        self.env=dict(os.environ,GIT_NO_LAZY_FETCH='1',GIT_OPTIONAL_LOCKS='0',GIT_TERMINAL_PROMPT='0')
        self.report={'kind':'source-review','origin':'local-host','outcome':'fail','recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'summary':'Bounded primary historical ChaCha nonce contract source-availability audit; no implementation or compatibility promotion',
          'commands':[],'http':[],'sources':[],'checks':[],'negative_controls':[],
          'restricted_bodies_retained':False,'compiler_executed':False,'device_executed':False,'nonce_contract_qualified':False}
    def rel(self,p):return str(Path(p).resolve().relative_to(self.main))
    def check(self,name,value):
        self.report['checks'].append({'name':name,'passed':bool(value)})
        if not value:raise ValueError(name)
    def command(self,argv,label):
        """Metadata output only. Never use this path to display a restricted blob."""
        p=subprocess.run(list(map(str,argv)),cwd=self.wt,env=self.env,capture_output=True,timeout=45)
        record={'argv':list(map(str,argv)),'exit_code':p.returncode,'stdout_sha256':sha(p.stdout),'stderr_sha256':sha(p.stderr)}
        self.report['commands'].append(record)
        (self.out/(label+'.stdout.txt')).write_bytes(p.stdout);(self.out/(label+'.stderr.txt')).write_bytes(p.stderr)
        return p.stdout.decode('utf-8'),p.returncode
    def http(self,url,label,head=False):
        record={'url':url,'method':'HEAD' if head else 'GET'};self.report['http'].append(record)
        try:
            with urlopen(Request(url,headers={'User-Agent':'S24-source-fact-audit','Accept-Encoding':'identity'},method=record['method']),timeout=15) as response:
                record.update(status=response.status,final_url=response.url,content_length=response.headers.get('Content-Length'),content_type=response.headers.get('Content-Type'))
                if head:return b'',record
                length=record['content_length']
                if length is not None and int(length)>2*1024*1024:raise ValueError('Named read exceeds2MiB cap')
                data=response.read(2*1024*1024+1)
                if len(data)>2*1024*1024:raise ValueError('Named read exceeds2MiB cap')
                if length is not None and len(data)!=int(length):raise ValueError('Incomplete HTTP content length')
                record.update(bytes=len(data),sha256=sha(data),complete=True)
                return data,record
        except HTTPError as error:record.update(status=error.code,error='HTTPError')
        except (URLError,TimeoutError,http.client.IncompleteRead,OSError,ValueError) as error:record.update(error=type(error).__name__)
        return None,record
    def source(self,repo,revision,path,expected=None):
        # Ephemeral raw body only. Store its canonical identities and limited facts.
        url=f'https://raw.githubusercontent.com/{repo}/{revision}/{path}'
        attempts=[]
        for attempt in range(2):
            data,record=self.http(url+'?nonce-contract-facts='+str(attempt),path)
            attempts.append(record)
            if data is not None:
                blob=git_blob(data)
                if expected is not None and blob!=expected:
                    record.update(error='CanonicalBlobMismatch');continue
                facts=minimal_facts(data,path)
                observation={'repository':'https://github.com/'+repo,'revision':revision,'path':path,'url':url,
                    'git_blob':blob,'sha256':sha(data),'bytes':len(data),'facts':facts,'restricted_body_saved':False}
                self.report['sources'].append(observation)
                print(json.dumps({'source':path,'revision':revision,'bytes':len(data),'verified_blob':blob,'incnonce_occurrences':facts['incnonce_token_occurrences']}),flush=True)
                return observation
        self.report['sources'].append({'repository':'https://github.com/'+repo,'revision':revision,'path':path,'verified':False,'attempts':attempts,'restricted_body_saved':False})
        return None
    def run(self):
        try:
            selected=self.main/'artifacts/xnu-prepare/e1s-dependency-source-session1/xnu'/HEADER
            selected_data=selected.read_bytes()
            self.check('exact-selected-header',sha(selected_data)=='583085c5a52979eb28bdec94a69d00b4c3536034c8f9763de9de1bb1101e0a93')
            tree,code=self.command(['git','-C',self.main/'references/apple-xnu','ls-tree',XNU,HEADER],'selected-tree')
            self.check('selected-canonical-blob',code==0 and git_blob(selected_data) in tree)
            self.report['selected_header']={'repository':'https://github.com/apple-oss-distributions/xnu','revision':XNU,'path':HEADER,'git_blob':git_blob(selected_data),'sha256':sha(selected_data),'bytes':len(selected_data),'facts':minimal_facts(selected_data,HEADER)}
            primary=self.main/'worktrees/krn-034-20261105/artifacts/crypto-chacha/apple-primary.git'
            tree,code=self.command(['git','-C',primary,'ls-tree','-r',APPLE,'--','ccchacha20poly1305'],'current-primary-tree')
            self.check('current-primary-metadata',code==0)
            blobs={line.split('\t',1)[1]:line.split()[2] for line in tree.splitlines()}
            for path in CURRENT_PATHS:
                if path in blobs:self.source('apple/corecrypto',APPLE,path,blobs[path])
            refs,code=self.command(['git','ls-remote','--heads','--tags','https://github.com/apple/corecrypto.git'],'official-corecrypto-public-refs')
            self.report['official_public_refs']={'exit_code':code,'refs':[line.split() for line in refs.splitlines()]}
            # Commit metadata has no restricted bodies; keep only parents/tree/time.
            meta,record=self.http('https://api.github.com/repos/apple/corecrypto/git/commits/'+APPLE,'current-root-commit')
            if meta:
                value=json.loads(meta);self.report['official_current_commit']={k:value.get(k) for k in ['sha','tree','parents']}
            # Named historical official XNU tag references, including peeled commits.
            patterns=[f'refs/tags/{t}'+suffix for t in TAGS for suffix in ['', '^{}']]
            refs,code=self.command(['git','ls-remote','--tags','https://github.com/apple-oss-distributions/xnu.git',*patterns],'historical-xnu-tag-refs')
            mapping={name:commit for commit,name in (line.split() for line in refs.splitlines())}
            self.report['historical_tags']={'names':TAGS,'exit_code':code,'refs':mapping}
            for tag in TAGS:
                commit=mapping.get('refs/tags/'+tag+'^{}') or mapping.get('refs/tags/'+tag)
                if not commit:continue
                # API contents is decoded in memory; only scalar metadata is retained.
                url='https://api.github.com/repos/apple-oss-distributions/xnu/contents/'+HEADER+'?ref='+commit
                data,record=self.http(url,'historical-header-'+tag)
                if not data:continue
                value=json.loads(data)
                if value.get('encoding')!='base64':continue
                body=base64.b64decode(value['content']);self.check('historical-canonical-'+tag,git_blob(body)==value['sha'] and len(body)==value['size'])
                observation={'repository':'https://github.com/apple-oss-distributions/xnu','tag':tag,'revision':commit,'path':HEADER,'git_blob':git_blob(body),'sha256':sha(body),'bytes':len(body),'facts':minimal_facts(body,HEADER),'restricted_body_saved':False}
                self.report['sources'].append(observation)
                print(json.dumps({'historical_tag':tag,'revision':commit,'git_blob':git_blob(body),'incnonce_occurrences':observation['facts']['incnonce_token_occurrences']}),flush=True)
            # Named older official delivery endpoints: HEAD metadata only, no archives.
            for year in [2023,2022,2021]:
                for ext in ['tar.gz','zip']:
                    self.http(f'https://developer.apple.com/security/src/corecrypto/corecrypto-{year}.{ext}','historical-archive',head=True)
            self.http('https://api.github.com/repos/apple-oss-distributions/corecrypto','official-distributions-repository')
            page,record=self.http('https://developer.apple.com/security/','official-security-page')
            if page:
                text=page.decode('utf-8');links=re.findall(r'(?:href|action)=[\"\']([^\"\']+)',text)
                self.report['official_security_page']={'url':record['url'],'sha256':sha(page),'bytes':len(page),'corecrypto_links':[x for x in links if 'corecrypto' in x.lower()],'contains_current_github_link':'https://github.com/apple/corecrypto' in text,'incnonce_occurrences':text.count('ccchacha20poly1305_incnonce')}
            self.report['outcome']='pass'
        except Exception as error:self.report['error']=type(error).__name__+': '+str(error)
        self.report['commit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=self.wt,env=self.env,text=True).strip()
        self.report['tool_sha256']={str(Path(p).resolve()):sha(Path(p).resolve().read_bytes()) for p in [sys.executable,'/usr/bin/git']}
        self.report['audit_source_sha256']=sha(Path(__file__).read_bytes())
        dump(self.out/'facts.json',self.report)
        # This is acquisition/source coverage, not an incnonce contract qualification.
        evidence={k:self.report[k] for k in ['kind','origin','outcome','recorded_at','summary','commit','commands']}
        files=[p for p in self.out.iterdir() if p.is_file()]
        evidence.update(artifacts=[self.rel(p) for p in files],sha256={self.rel(p):sha(p.read_bytes()) for p in files},limitations=['No restricted implementation bodies retained or translated;facts only.','Nonce encoding/range/order/overflow/lifecycle remain unqualified unless separately supported by applicable primary evidence.'])
        dump(self.out/'evidence.json',evidence)
        print(json.dumps({'outcome':self.report['outcome'],'sources':len(self.report['sources']),'error':self.report.get('error'),'facts':self.rel(self.out/'facts.json')}),flush=True)
        return self.report['outcome']!='pass'

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--main-root',type=Path,required=True);p.add_argument('--run',required=True)
    return Audit(p.parse_args()).run()
if __name__=='__main__':sys.exit(main())
