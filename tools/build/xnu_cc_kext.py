#!/usr/bin/env python3
"""Qualify genuine public Darwin ARM64 cc_kext, without installing a toolchain."""
from __future__ import annotations
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import io
import http.client
import json
import os
import posixpath
from pathlib import Path
import resource
import re
import signal
import shutil
import subprocess
import struct
import shlex
import sys
import tarfile
import time
import urllib.request
import urllib.error

REVISION='6009708b4367171ccdbf4b5905cb6a803753fe18'
DRIVER_REVISION='fa9443738c1a18accef4244732ec6d6ee97a8133'
MAIN=Path('/home/egor/dev/pet/s24-ios-exynos')
WORK=Path(__file__).resolve().parents[2]
COMPILER=MAIN/'artifacts/xnu-compiler-cxx-storage/source-build-session2/clang'
COMPILER_SHA='7972eb2820ae25b5bedff1ea954cef9e9a0e4a15c7a8e440628e8b6540fafc82'
NDK=Path('/home/egor/Android/Sdk/ndk/28.2.13676358/toolchains/llvm/prebuilt/linux-x86_64/bin')


def sha(p):
    with Path(p).open('rb') as stream: return hashlib.file_digest(stream,'sha256').hexdigest()
def dump(p,d): p.write_text(json.dumps(d,indent=2)+'\n')
def relative(p):
    p=Path(p)
    return str(p.relative_to(MAIN)) if p.is_relative_to(MAIN) else str(p)


def pressure():
    memory={line.split(':')[0]:int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith(('MemAvailable:','SwapFree:'))}
    return dict(**memory,psi=Path('/proc/pressure/memory').read_text().strip())


def group_rss(pgid):
    total=0
    for p in Path('/proc').iterdir():
        if not p.name.isdigit(): continue
        try:
            fields=(p/'stat').read_text().rsplit(')',1)[1].split()
            if int(fields[2])==pgid: total+=int(fields[21])*os.sysconf('SC_PAGE_SIZE')
        except (FileNotFoundError,ProcessLookupError,PermissionError,ValueError,IndexError): pass
    return total


def live_group(pgid):
    result=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdigit(): continue
        try:
            fields=(p/'stat').read_text().rsplit(')',1)[1].split()
            if int(fields[2])==pgid and fields[0]!='Z': result.append(int(p.name))
        except (FileNotFoundError,ProcessLookupError,PermissionError,ValueError,IndexError): pass
    return result


def archive_members(data):
    if data[:8]!=b'!<arch>\n': raise ValueError('Not a real ar archive')
    offset=8;members=[]
    while offset<len(data):
        h=data[offset:offset+60]
        if len(h)!=60 or h[58:]!=b'`\n' or not h[48:58].strip().isdigit(): raise ValueError('Invalid ar header')
        size=int(h[48:58]);start=offset+60
        if size>len(data)-start: raise ValueError('Truncated ar member')
        name=h[:16].decode('ascii').strip();body=data[start:start+size]
        if name.startswith('#1/'):
            extent=int(name[3:])
            if extent>len(body): raise ValueError('Truncated BSD ar member name')
            name=body[:extent].rstrip(b'\0').decode();body=body[extent:]
        else: name=name.rstrip('/')
        if not name.startswith('__.SYMDEF') and name not in {'','/'}: members.append((name,body))
        offset=start+size+(size%2)
    if offset!=len(data) or not members: raise ValueError('Empty or invalid ar archive')
    return members


def object_symbols(data):
    if len(data)<32: raise ValueError('Truncated Mach-O object')
    magic,cpu,sub,kind,count,extent,_,_=struct.unpack_from('<8I',data)
    if (magic,cpu,sub,kind)!=(0xfeedfacf,0x100000c,0,1): raise ValueError('Actual plain ARM64 Mach-O object required')
    if extent>len(data)-32 or count>extent//8: raise ValueError('Invalid Mach-O load commands')
    at=32;table=None;platform=[]
    for _ in range(count):
        if at+8>32+extent: raise ValueError('Truncated load command')
        command,size=struct.unpack_from('<II',data,at)
        if size<8 or size>32+extent-at: raise ValueError('Invalid load command size')
        if command==0x32:
            if size<24: raise ValueError('Truncated build version')
            platform.append(struct.unpack_from('<II',data,at+8))
        elif command==0x25:
            if size<16: raise ValueError('Truncated iOS min version')
            platform.append((2,struct.unpack_from('<I',data,at+8)[0]))
        elif command==2:
            if size<24 or table is not None: raise ValueError('Invalid symbol table command')
            table=struct.unpack_from('<4I',data,at+8)
        at+=size
    if at!=32+extent or platform!=[(2,0x00100500)]: raise ValueError('Exact selected iOS16.5 object platform required')
    defined=set();undefined=set()
    if table:
        symoff,nsyms,stroff,strsize=table
        if symoff>len(data) or nsyms>(len(data)-symoff)//16 or stroff>len(data) or strsize>len(data)-stroff: raise ValueError('Symbol table outside object')
        for index in range(nsyms):
            name,typ,_,_,value=struct.unpack_from('<IBBHQ',data,symoff+16*index)
            if typ&0xe0 or not typ&1: continue
            if name>=strsize: raise ValueError('Symbol name outside string table')
            end=data.find(b'\0',stroff+name,stroff+strsize)
            if end<0: raise ValueError('Unterminated symbol')
            symbol=data[stroff+name:end].decode('utf-8')
            if typ&0x0e or value: defined.add(symbol)
            else: undefined.add(symbol)
    return defined,undefined


class Runner:
    def __init__(self,args):
        self.args=args;self.deadline=time.monotonic()+1500;self.out=WORK/'artifacts/xnu-cc-kext'/args.run
        self.out.mkdir(parents=True,exist_ok=False)
        shutil.copyfile(__file__,self.out/'builder.py')
        self.fixture_root=self.out/'fixture-inputs'
        shutil.copytree(WORK/'fixtures/public/xnu-cc-kext',self.fixture_root,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        self.report=dict(mode=args.mode,kind='host-test',origin='local-host',outcome='fail',recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),commands=[],checks=[],device_executed=False,sdk_used=False,global_install=False,full_kernel_qualified=False,full_crypto_qualified=False,apple_private_abi_qualified=False,arm64_runtime_executed=False,source_revision=REVISION,commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=WORK,text=True).strip())
        self.env=os.environ.copy();self.env.update(GIT_NO_LAZY_FETCH='1',GIT_OPTIONAL_LOCKS='0',ZERO_AR_DATE='1')
        self.report['environment']={k:self.env[k] for k in ['GIT_NO_LAZY_FETCH','GIT_OPTIONAL_LOCKS','ZERO_AR_DATE']}

    def qualified_parent(self,name,outcomes=('pass',)):
        ledger=json.loads((MAIN/'state/lab.json').read_text())
        by_id=[e for e in ledger['experiments'] if e['id']==name]
        parent=(MAIN/by_id[0]['evidence']).parent if len(by_id)==1 and by_id[0].get('evidence') else WORK/'artifacts/xnu-cc-kext'/name
        evidence=parent/'evidence.json'
        candidates=[e for e in ledger['experiments'] if e.get('evidence')==relative(evidence)]
        if len(candidates)!=1 or candidates[0].get('status')!='recorded' or candidates[0].get('outcome') not in outcomes or candidates[0]['evidence_sha256']!=sha(evidence):
            raise ValueError('One registered immutable passing source/component parent required')
        doc=json.loads(evidence.read_text())
        for path,digest in doc['sha256'].items():
            actual=MAIN/path
            if not actual.resolve().is_relative_to(MAIN) or sha(actual)!=digest: raise ValueError('Changed recorded parent artifact: '+path)
        self.check('registered-immutable-parent-'+name,True)
        return parent,json.loads((parent/'report.json').read_text())

    def check(self,name,value):
        self.report['checks'].append(dict(name=name,pass_check=bool(value)))
        if not value: raise ValueError(name)

    def run(self,argv,label,timeout=120,allowed=(0,),cwd=None):
        timeout=min(timeout,max(0,self.deadline-time.monotonic()))
        if timeout<=0: raise TimeoutError('Finite whole-run deadline reached')
        argv=[str(x) for x in argv]
        executable=Path(shutil.which(argv[0]) or argv[0]).resolve()
        if str(executable) not in self.report.setdefault('tools_sha256',{}): self.report['tools_sha256'][str(executable)]=sha(executable)
        before=pressure()
        if before['MemAvailable']<4*1024**3: raise RuntimeError('MemAvailable floor prevents '+label)
        out=self.out/(label+'.stdout.txt');err=self.out/(label+'.stderr.txt');start=time.monotonic();peak=0;stop=None;samples=[];escalated=False
        with out.open('w') as stdout,err.open('w') as stderr:
            p=subprocess.Popen(argv,cwd=cwd or WORK,env=self.env,stdout=stdout,stderr=stderr,start_new_session=True)
            while p.poll() is None:
                sample=pressure();rss=group_rss(p.pid);peak=max(peak,rss)
                if len(samples)<1200: samples.append(dict(elapsed=round(time.monotonic()-start,2),owned_rss=rss,**sample))
                if time.monotonic()-start>timeout: stop='timeout'
                elif rss>2*1024**3: stop='owned-RSS-limit'
                elif sample['MemAvailable']<4*1024**3: stop='MemAvailable-floor'
                if stop:
                    os.killpg(p.pid,signal.SIGTERM)
                    try: p.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        escalated=True;os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=3)
                    break
                time.sleep(.1)
            code=p.wait(timeout=3)
        remaining=live_group(p.pid)
        if remaining:
            os.killpg(p.pid,signal.SIGKILL)
            for _ in range(30):
                if not live_group(p.pid): break
                time.sleep(.1)
            remaining=live_group(p.pid)
            if remaining: stop='owned-descendants-not-quiesced'
        row=dict(owned_process_group=p.pid,sigkill_escalated=escalated,remaining_live_owned_children=remaining,argv=argv,cwd=str(cwd or WORK),exit_code=code,stdout=relative(out),stderr=relative(err),timeout_seconds=timeout,stop_reason=stop,peak_owned_rss=peak,pressure_before=before,pressure_samples=samples,elapsed_seconds=round(time.monotonic()-start,3))
        self.report['commands'].append(row)
        if stop or code not in allowed: raise RuntimeError(label+' failed')
        return out.read_text()

    def fetch(self,url,name,limit=32*1024**2):
        start=time.monotonic();path=self.out/name
        request=urllib.request.Request(url,headers={'User-Agent':'s24-ios-exynos-source-research'})
        for attempt in range(3):
            try:
                if time.monotonic()>=self.deadline: raise TimeoutError('Finite source run deadline reached')
                with urllib.request.urlopen(request,timeout=max(1,min(45,self.deadline-time.monotonic()))) as response:
                    data=response.read(limit+1)
                    if len(data)>limit: raise ValueError('Bounded source download exceeded')
                    path.write_bytes(data)
                    self.report.setdefault('downloads',[]).append(dict(url=url,status=response.status,path=relative(path),sha256=sha(path),bytes=len(data),elapsed_seconds=round(time.monotonic()-start,3)))
                break
            except (http.client.HTTPException, urllib.error.URLError, TimeoutError) as error:
                partial=getattr(error,'partial',b'')
                failure=self.out/(name+'.attempt-'+str(attempt)+'.partial')
                failure.write_bytes(partial)
                self.report.setdefault('download_failures',[]).append(dict(url=url,attempt=attempt,error=repr(error),partial=relative(failure),sha256=sha(failure)))
                if attempt==2: raise
        return data

    def primary_blob(self,url,blob,label,repository):
        data=self.fetch(url,label+'.raw',limit=1024**2)
        digest=lambda b:hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
        if digest(data)==blob: return data
        self.report.setdefault('rejected_downloads',[]).append(dict(path=relative(self.out/(label+'.raw')),expected_git_blob=blob,actual_git_blob=digest(data)))
        for attempt in range(3):
            body=self.fetch('https://api.github.com/repos/'+repository+'/git/blobs/'+blob,label+'.blob-'+str(attempt)+'.json',limit=2*1024**2)
            try:
                doc=json.loads(body)
                if doc['encoding']!='base64' or doc['sha']!=blob: raise ValueError('Wrong Git blob metadata')
                data=base64.b64decode(doc['content'])
                if digest(data)!=blob: raise ValueError('Git object content mismatch')
                return data
            except (ValueError,KeyError):
                if attempt==2: raise
        raise ValueError('Pinned Git blob unavailable')

    def source(self):
        root=json.loads(self.fetch('https://api.github.com/repos/llvm/llvm-project/git/trees/'+REVISION,'repository-tree.json'))
        entry=next(x for x in root['tree'] if x['path']=='compiler-rt')
        runtime=json.loads(self.fetch('https://api.github.com/repos/llvm/llvm-project/git/trees/'+entry['sha'],'runtime-root-tree.json'))
        trees=[]
        for item in runtime['tree']:
            if item['type']=='blob': trees.append(item)
        wanted={'cmake','include','lib'}
        for item in runtime['tree']:
            if item['path'] not in wanted: continue
            if item['path']=='lib':
                libs=json.loads(self.fetch('https://api.github.com/repos/llvm/llvm-project/git/trees/'+item['sha'],'library-root-tree.json'))
                for lib in libs['tree']:
                    if lib['path'] not in {'builtins','profile'}: continue
                    subtree=json.loads(self.fetch('https://api.github.com/repos/llvm/llvm-project/git/trees/'+lib['sha']+'?recursive=1',lib['path']+'-tree.json'))
                    self.check('complete-primary-'+lib['path']+'-tree',not subtree.get('truncated'))
                    trees.extend(dict(**{k:v for k,v in x.items() if k!='path'},path='lib/'+lib['path']+'/'+x['path']) for x in subtree['tree'])
            else:
                subtree=json.loads(self.fetch('https://api.github.com/repos/llvm/llvm-project/git/trees/'+item['sha']+'?recursive=1',item['path']+'-tree.json'))
                self.check('complete-primary-'+item['path']+'-tree',not subtree.get('truncated'))
                trees.extend(dict(**{k:v for k,v in x.items() if k!='path'},path=item['path']+'/'+x['path']) for x in subtree['tree'])
        data=self.fetch('https://github.com/llvm/llvm-project/releases/download/llvmorg-17.0.6/compiler-rt-17.0.6.src.tar.xz','compiler-rt-17.0.6.src.tar.xz')
        source=self.out/'source';source.mkdir();total=0
        with tarfile.open(fileobj=io.BytesIO(data),mode='r:xz') as archive:
            for member in archive:
                parts=Path(member.name).parts
                if not parts or parts[0]!='compiler-rt-17.0.6.src' or '..' in parts or member.name.startswith('/'):
                    raise ValueError('Unexpected source archive path')
                if not member.isfile(): continue
                total+=member.size
                if total>256*1024**2: raise ValueError('Bounded source expansion exceeded')
                target=source.joinpath(*parts[1:]);target.parent.mkdir(parents=True,exist_ok=True)
                stream=archive.extractfile(member)
                if stream is None: raise ValueError('Missing source member')
                target.write_bytes(stream.read())
        verified={};different=[]
        for item in trees:
            if item['type']!='blob' or item['mode']!='100644': continue
            p=source/item['path']
            if not p.is_file(): different.append(item['path']);continue
            contents=p.read_bytes();blob=hashlib.sha1(b'blob '+str(len(contents)).encode()+b'\0'+contents).hexdigest()
            if blob!=item['sha']: different.append(item['path'])
            else: verified[item['path']]=dict(git_blob_sha1=blob,sha256=sha(p))
        self.report['source_tree']=dict(commit=REVISION,tree_sha=entry['sha'],verified_files=len(verified),mismatches=different,root=relative(source))
        dump(self.out/'source-files.json',verified)
        self.check('release-runtime-files-match-pinned-Git-tree',len(verified)>300 and not different)
        self.report['outcome']='pass'

    def recover_source(self):
        old=WORK/'artifacts/xnu-cc-kext'/self.args.source_run
        previous=json.loads((old/'report.json').read_text())
        self.check('recover-only-pinned-source-capsule',previous['source_revision']==REVISION and previous['outcome']=='fail' and previous['error'].startswith('EOFError'))
        entries=[]
        base=json.loads((old/'runtime-root-tree.json').read_text())
        entries.extend(x for x in base['tree'] if x['type']=='blob')
        for name,prefix in [('builtins','lib/builtins/'),('profile','lib/profile/'),('include','include/'),('cmake','cmake/')]:
            tree=json.loads((old/(name+'-tree.json')).read_text())
            self.check('complete-recovered-'+name+'-tree',not tree.get('truncated'))
            entries.extend(dict(**{k:v for k,v in x.items() if k!='path'},path=prefix+x['path']) for x in tree['tree'])
        verified={};source=self.out/'source';source.mkdir()
        for item in entries:
            if item['type']!='blob' or item['mode']!='100644': continue
            name=item['path'];original=old/'source'/name;contents=original.read_bytes()
            blob=hashlib.sha1(b'blob '+str(len(contents)).encode()+b'\0'+contents).hexdigest()
            if blob!=item['sha']: raise ValueError('Recovered source Git blob mismatch: '+name)
            target=source/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(original,target)
            verified[name]=dict(git_blob_sha1=blob,sha256=sha(target))
        for name in ['repository-tree.json','runtime-root-tree.json','library-root-tree.json','builtins-tree.json','profile-tree.json','include-tree.json','cmake-tree.json']:
            shutil.copyfile(old/name,self.out/name)
        self.report['source_tree']=dict(commit=REVISION,root=relative(source),verified_files=len(verified),complete_release_archive=False,scope='Complete pinned builtins/profile/include/cmake source subtrees and top-level files recovered before truncated unused-test archive tail;each copied file matches primary Git blob')
        self.report['parent_evidence']=dict(path=relative(old/'evidence.json'),sha256=sha(old/'evidence.json'))
        dump(self.out/'source-files.json',verified)
        self.check('all472-genuine-needed-source-files-verified',len(verified)==472)
        self.report['outcome']='pass'

    def public_headers(self):
        revision='a61a5933206342413af76579500f313a045c1c33'
        prefix='https://api.github.com/repos/apple-oss-distributions/Libc/git/trees/'
        root=json.loads(self.fetch(prefix+revision,'libc-root-tree.json'))
        include=next(x for x in root['tree'] if x['path']=='include')
        tree=json.loads(self.fetch(prefix+include['sha']+'?recursive=1','libc-include-tree.json'))
        self.check('complete-primary-public-Libc-include-tree',not tree.get('truncated'))
        result={};headers=self.out/'headers';headers.mkdir()
        for row in tree['tree']:
            if row['type']!='blob' or row['mode']!='100644': continue
            name=row['path'];download='header-'+name.replace('/','_')
            data=self.fetch('https://raw.githubusercontent.com/apple-oss-distributions/Libc/'+revision+'/include/'+name,download,limit=1024**2)
            blob=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
            if blob!=row['sha']: raise ValueError('Public Libc header blob mismatch: '+name)
            target=headers/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
            result[name]=dict(revision=revision,git_blob_sha1=blob,sha256=sha(target))
        licenses=[x for x in root['tree'] if 'LICENSE' in x['path'].upper() and x['type']=='blob']
        for row in licenses:
            self.fetch('https://raw.githubusercontent.com/apple-oss-distributions/Libc/'+revision+'/'+row['path'],'Libc-'+row['path'])
        dump(self.out/'public-header-files.json',result)
        self.report['public_headers']=dict(repository='https://github.com/apple-oss-distributions/Libc',revision=revision,tag='Libc-1534.100.14',root=relative(headers),files=len(result),sdk=False,scope='Public source headers only;no proprietary SDK binaries or private ABI oracle')
        self.report['outcome']='pass'

    def supplement_headers(self):
        parent,_=self.qualified_parent(self.args.headers_run)
        manifest=json.loads((parent/'public-header-files.json').read_text())
        headers=self.out/'headers';headers.mkdir()
        for name,row in manifest.items():
            original=parent/'headers'/name
            if sha(original)!=row['sha256']: raise ValueError('Changed source header')
            target=headers/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(original,target)
        revision='6982ddbfca1047c86680ec7c66da152789746efd'
        repo=MAIN/'references/puredarwin-build-inputs'
        prefix='src/Libraries/AvailabilityVersions/include/'
        listing=self.run(['git','-C',repo,'ls-tree','-r',revision,'--',prefix,'src/Libraries/dyld/upstream/include/dlfcn.h','src/Libraries/libSystem/libplatform/include/libkern/OSCacheControl.h'],'pinned-supplement-header-tree')
        for line in listing.splitlines():
            mode,kind,rest=line.split(' ',2);blob,name=rest.split('\t')
            if kind!='blob' or mode!='100644': continue
            installed=name[len(prefix):] if name.startswith(prefix) else ('libkern/OSCacheControl.h' if name.endswith('/OSCacheControl.h') else 'dlfcn.h')
            if installed in manifest and manifest[installed].get('git_blob_sha1')==blob and sha(headers/installed)==manifest[installed]['sha256']: continue
            data=self.primary_blob('https://raw.githubusercontent.com/PureDarwin/PureDarwin/'+revision+'/'+name,blob,'supplement-'+installed.replace('/','_'),'PureDarwin/PureDarwin')
            actual=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
            if actual!=blob: raise ValueError('Pinned supplement Git blob mismatch')
            target=headers/installed;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
            manifest[installed]=dict(repository='https://github.com/PureDarwin/PureDarwin',revision=revision,source_path=name,git_blob_sha1=blob,sha256=sha(target))
        if (parent/'Libc-headers.sh').is_file(): shutil.copyfile(parent/'Libc-headers.sh',self.out/'Libc-headers.sh')
        else: self.fetch('https://raw.githubusercontent.com/apple-oss-distributions/Libc/a61a5933206342413af76579500f313a045c1c33/xcodescripts/headers.sh','Libc-headers.sh')
        dump(self.out/'public-header-files.json',manifest)
        self.report['header_parent']=dict(path=relative(parent/'evidence.json'),sha256=sha(parent/'evidence.json'))
        self.report['public_headers']=dict(root=relative(headers),files=len(manifest),scope='Exact public source header subset and genuine declaration install paths;not an acquired SDK or private ABI oracle')
        self.check('public-availability-and-dlfcn-staged',all((headers/n).is_file() for n in ['os/availability.h','AvailabilityInternal.h','dlfcn.h']))
        self.report['outcome']='pass'

    def inputs(self):
        parent,report=self.qualified_parent(self.args.source_run)
        self.check('qualified-source-parent',report['outcome']=='pass' and report['source_revision']==REVISION)
        self.source=parent/'source';manifest=json.loads((parent/'source-files.json').read_text())
        for name,row in manifest.items():
            if sha(self.source/name)!=row['sha256']: raise ValueError('Changed pinned runtime source: '+name)
        self.report['runtime_source_inputs']=manifest
        self.report['parent_evidence']=dict(path=relative(parent/'evidence.json'),sha256=sha(parent/'evidence.json'))
        self.check('exact-qualified-selected-compiler',sha(COMPILER)==COMPILER_SHA)
        self.report['compiler']=dict(path=relative(COMPILER),sha256=sha(COMPILER))
        self.resource=self.out/'resource';include=self.resource/'include'
        headers=MAIN/'references/xnu-tapi/src/clang/lib/Headers'
        shutil.copytree(headers,include)
        self.report['resource_headers']={relative(p):sha(p) for p in include.rglob('*') if p.is_file()}
        self.libtool=MAIN/'artifacts/xnu-macho-tools/macho-session4/prefix/bin/aarch64-apple-darwin-libtool'
        self.ld=MAIN/'artifacts/xnu-macho-tools/macho-session4/prefix/bin/aarch64-apple-darwin-ld'
        self.report['tools_sha256']={str(p):sha(p) for p in [self.libtool,self.ld,NDK/'llvm-readobj',NDK/'llvm-nm',NDK/'llvm-ar']}
        witness={}
        for name in ['Driver.cpp','ToolChains/Darwin.cpp','ToolChain.cpp']:
            path='src/clang/lib/Driver/'+name
            data=self.run(['git','-C',MAIN/'references/xnu-tapi','show',DRIVER_REVISION+':'+path],'driver-'+Path(name).stem)
            actual=MAIN/'artifacts/xnu-compiler-types/frontend-session1/compiler-source'/path
            self.check('unchanged-selected-'+name,data.encode()==actual.read_bytes())
            witness[path]=dict(revision=DRIVER_REVISION,sha256=sha(actual))
        self.report['driver_sources']=witness
        self.extra_includes=[]
        if self.args.headers_run:
            parent,headers=self.qualified_parent(self.args.headers_run)
            self.check('qualified-public-header-parent',headers['outcome']=='pass')
            for name,row in json.loads((parent/'public-header-files.json').read_text()).items():
                if sha(parent/'headers'/name)!=row['sha256']: raise ValueError('Changed public header: '+name)
            installed=self.out/'public-source-headers';installed.mkdir()
            header_manifest=json.loads((parent/'public-header-files.json').read_text())
            self.header_manifest=header_manifest;self.header_parent=parent;self.installed_headers=installed
            for name,row in header_manifest.items():
                original=parent/'headers'/name
                if name=='sys/cdefs.h':
                    self.check('exclude-Libc-build-internal-cdefs-per-native-install-policy','Not to be installed in /usr/include' in original.read_text())
                    continue
                target=installed/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(original,target)
            self.report['source_header_staging_policy']='Exact public source declaration bytes;exclude Libc internal sys/cdefs.h explicitly marked not-installed and absent native SYS_INSTHDRS;use selected XNU real cdefs and generated aliases,not disabled feature checks'
            self.extra_includes=[installed,MAIN/'references/puredarwin-build-inputs/src/Libraries/AvailabilityVersions/include',MAIN/'references/xnu-host-dispatch',MAIN/'references/xnu-kernel-pthread/include',MAIN/'references/xnu-kernel-pthread/include/pthread',MAIN/'references/apple-xnu/EXTERNAL_HEADERS',MAIN/'references/apple-xnu/bsd',MAIN/'references/apple-xnu/osfmk',MAIN/'references/apple-xnu/libkern']
            self.report['header_parent']=dict(path=relative(parent/'evidence.json'),sha256=sha(parent/'evidence.json'))
            self.report['public_source_header_roots']=[relative(p) for p in self.extra_includes]

        self.run([COMPILER,'-print-resource-dir'],'original-resource-dir')

    def setup_headers(self):
        setup=self.out/'setup-headers';(setup/'sys').mkdir(parents=True)
        prefix=self.out/'availability-tool-prefix';script=prefix/'usr/local/libexec/availability.pl';script.parent.mkdir(parents=True)
        original=MAIN/'references/xnu-availability/availability.pl';shutil.copyfile(original,script);script.chmod(0o755)
        kernel=MAIN/'references/apple-xnu'
        self.run(['/bin/bash',kernel/'bsd/sys/make_symbol_aliasing.sh',prefix,setup/'sys/_symbol_aliasing.h'],'native-symbol-aliasing-header')
        self.run(['/bin/sh',kernel/'bsd/sys/make_posix_availability.sh',setup/'sys/_posix_availability.h'],'native-posix-availability-header')
        self.report['native_header_generators']={relative(p):sha(p) for p in [original,kernel/'bsd/sys/make_symbol_aliasing.sh',kernel/'bsd/sys/make_posix_availability.sh']}
        self.report['availability_tool_prefix_is_sdk']=False
        self.extra_includes.insert(0,setup)

    def feature_profile(self,flags):
        native=(self.source/'cmake/builtin-config-ix.cmake').read_text()
        results={}
        for variable in ['COMPILER_RT_HAS_ATOMIC_KEYWORD','COMPILER_RT_HAS_ASM_LSE']:
            match=re.search(r'builtin_check_c_compiler_source\('+variable+r'\s+"((?:\\.|[^"\\])*)"\s*\)',native,re.S)
            if not match: raise ValueError('Actual native feature test missing')
            text=match.group(1).replace('\\"','"')
            source=self.out/(variable+'.c');source.write_text(text)
            self.run([COMPILER,*flags,'-c',source,'-o',source.with_suffix('.o')],'feature-'+variable,allowed=(0,1))
            results[variable]=self.report['commands'][-1]['exit_code']==0
        source=self.out/'unwind-header.c';source.write_text('#include <unwind.h>\nint s24_unwind_header;\n')
        self.run([COMPILER,*flags,'-c',source,'-o',source.with_suffix('.o')],'feature-HAVE_UNWIND_H',allowed=(0,1))
        results['HAVE_UNWIND_H']=self.report['commands'][-1]['exit_code']==0
        self.features=results;self.report['native_feature_profile']=results

    def select_sources(self):
        builtins=self.source/'lib/builtins';cmake=self.source/'cmake/Modules'
        text=(builtins/'CMakeLists.txt').read_text()
        begin=text.index('set(GENERIC_SOURCES');end=text.index('add_custom_target(builtins)')
        selected=self.out/'source-selection.cmake';selected.write_text(text[begin:end])
        directory=self.out/'selection';directory.mkdir()
        script='cmake_minimum_required(VERSION 3.20)\nproject(CCKextSourceSelection NONE)\n'
        script+='set(APPLE TRUE)\n'+''.join('set('+k+' '+('TRUE' if v else 'FALSE')+')\n' for k,v in self.features.items())
        script+='set(CMAKE_CURRENT_SOURCE_DIR "'+str(builtins)+'")\n'
        script+='list(APPEND CMAKE_MODULE_PATH "'+str(cmake)+'")\ninclude(CompilerRTDarwinUtils)\n'
        script+='include("'+str(selected)+'")\n'
        script+='set(DARWIN_EXCLUDE_DIR "'+str(builtins/'Darwin-excludes')+'")\n'
        script+='darwin_find_excluded_builtins_list(ios_arm64_EXCLUDED OS ios ARCH arm64)\n'
        script+='darwin_filter_builtin_sources(filtered cc_kext_ios_arm64 EXCLUDE ios_arm64_EXCLUDED ${arm64_SOURCES})\n'
        script+='add_custom_target(lse_builtin_symlinks ${arm64_lse_commands})\n'
        script+='file(WRITE "'+str(self.out/'selected-sources.txt')+'" "")\n'
        script+='foreach(src ${filtered})\nget_source_file_property(defs ${src} COMPILE_DEFINITIONS)\nget_source_file_property(incs ${src} INCLUDE_DIRECTORIES)\n'
        script+='if(NOT defs)\nset(defs "")\nendif()\nif(NOT incs)\nset(incs "")\nendif()\n'
        script+='string(REPLACE ";" "," defs "${defs}")\nstring(REPLACE ";" "," incs "${incs}")\n'
        script+='file(APPEND "'+str(self.out/'selected-sources.txt')+'" "${src}|${defs}|${incs}\\n")\nendforeach()\n'
        (directory/'CMakeLists.txt').write_text(script)
        self.run(['cmake','-S',directory,'-B',self.out/'selection-build'],'genuine-CMake-source-selection')
        self.run(['cmake','--build',self.out/'selection-build','--target','lse_builtin_symlinks','--parallel','2'],'genuine-outline-helper-generation')
        rows=[line.split('|') for line in (self.out/'selected-sources.txt').read_text().splitlines()]
        self.source_flags={}
        self.sources=[]
        for name,defs,incs in rows:
            path=Path(name) if Path(name).is_absolute() else builtins/name
            self.sources.append(path)
            self.source_flags[str(path)]=['-D'+d for d in defs.split(',') if d]+[item for d in incs.split(',') if d for item in ['-I',d]]
        native=(cmake/'CompilerRTDarwinUtils.cmake').read_text()
        profile_block=re.search(r'set\(PROFILE_SOURCES (.*?)\)',native,re.S).group(1)
        self.sources.extend((builtins/n).resolve() for n in profile_block.split())
        self.check('genuine-source-selection-nonempty',len(self.sources)>250 and len(self.sources)==len(set(self.sources)))
        self.report['selection']=dict(count=len(self.sources),sources=[relative(p) for p in self.sources],cmake_source_begin=begin,cmake_source_end=end,native_flags=['-fPIC','-O3','-fvisibility=hidden','-DVISIBILITY_HIDDEN','-Wall','-fomit-frame-pointer','-arch','arm64','-mkernel','-DKERNEL_USE'],measured_features=self.features,scope='Actual pinned builtins source-list expressions and Darwin exclusion/architecture-override functions; explicit host adaptation, not an Xcode SDK configure')

    def inspect_archive(self,archive,objects):
        members=archive_members(archive.read_bytes())
        self.check('all-genuine-source-objects-in-archive',len(members)==len(objects))
        rows=[];definitions=set();imports=set()
        for (name,data),original in zip(members,objects):
            self.check('archive-member-'+name,name==original.name and hashlib.sha256(data).hexdigest()==sha(original))
            defined,undefined=object_symbols(data);definitions.update(defined);imports.update(undefined)
            rows.append(dict(name=name,sha256=sha(original),defined=sorted(defined),undefined=sorted(undefined)))
        output=self.run([NDK/'llvm-readobj','--file-headers',archive],'independent-all-member-headers')
        self.check('independent-all-member-ARM64-architecture',output.count('Format: Mach-O arm64')==len(objects))
        for label,option,expected in [('defined','--defined-only',definitions),('undefined','--undefined-only',imports)]:
            output=self.run([NDK/'llvm-nm','-g',option,'--just-symbol-name',archive],'independent-all-member-'+label)
            observed={line.strip() for line in output.splitlines() if line.strip() and not line.strip().endswith(':')}
            self.check('independent-all-member-'+label+'-symbols-agree',observed==expected)
        self.report['runtime_symbols']=dict(defined=sorted(definitions),undefined=sorted(imports),external_imports=sorted(imports-definitions),scope='All members inspected;remaining kernel/libc/section-magic imports explicit,not a full-runtime closure claim')
        dump(self.out/'archive-members.json',rows)
        self.check('genuine-integer-and-profile-exports',{'___divti3','___udivti3','___multi3','___llvm_profile_get_magic','___llvm_profile_get_version'}<=definitions)

    def host_semantics(self):
        compiler=Path('/home/egor/.local/bin/clang')
        files=['divti3','modti3','udivti3','umodti3','udivmodti4','multi3','ashlti3','lshrti3','ashrti3','clzti2','ctzti2','cmpti2','ucmpti2']
        binary=self.out/'host-integer-semantics';source=getattr(self,'patched_source',self.source)
        instrument=['-std=gnu11','-O3','-g','-Wall','-Wextra','-Werror','-fno-builtin','-fsanitize=address,undefined','-fno-omit-frame-pointer']
        environment=['env','ASAN_OPTIONS=detect_leaks=1:halt_on_error=1','UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1']
        self.run([compiler,*instrument,'-I',source/'lib/builtins',self.fixture_root/'integer-semantics.c',*[source/'lib/builtins'/(n+'.c') for n in files],'-o',binary],'host-genuine-integer-semantics-build')
        result=self.run([*environment,binary],'host-genuine-integer-semantics-execute',timeout=30)
        self.check('host10128-independent-genuine-integer-cases','PASS 10128 independently constructed integer cases' in result)
        if hasattr(self,'patched_source'):
            for name,root in [('original',self.source),('corrected',self.patched_source)]:
                binary=self.out/('host-arithmetic-shift-'+name)
                self.run([compiler,*instrument,'-I',root/'lib/builtins',self.fixture_root/'arithmetic-shift.c',root/'lib/builtins/ashrti3.c','-o',binary],name+'-full-sanitizer-shift-build')
                result=self.run([*environment,binary],name+'-full-sanitizer-shift-execute',timeout=30,allowed=(1,) if name=='original' else (0,))
                if name=='original':
                    diagnostic=(self.out/(name+'-full-sanitizer-shift-execute.stderr.txt')).read_text()
                    self.check('original-actual-UBSan-negative-signed-left-shift','ashrti3.c:34:34: runtime error: left shift of negative value -1' in diagnostic)
                else:self.check('corrected1281025-independent-full-sanitizer-shift-cases','PASS 1281025 independent arithmetic shift cases' in result)
        self.report['host_semantic_scope']='Actual host x86_64 O3 source execution under full ASan+UBSan;independent unsigned64-limb shift oracle,shift-add products and constructed quotients;not execution of ARM64 objects or full287-source runtime behavior'
        self.report['tested_integer_source_full_sanitizers_qualified']=True
        self.report['tools_sha256'][str(compiler.resolve())]=sha(compiler)

    def header_inventory(self):
        revision='6982ddbfca1047c86680ec7c66da152789746efd'
        repo=MAIN/'references/puredarwin-build-inputs'
        prefixes=['src/Libraries/libSystem/libmalloc','src/Libraries/libSystem/libplatform','src/Libraries/libSystem/libsystem_kernel','src/Libraries/libSystem/libc','src/Libraries/dyld/upstream/include']
        listing=self.run(['git','-C',repo,'ls-tree','-r',revision,'--',*prefixes],'pinned-public-header-resolution-inventory')
        all_files={};published={}
        for line in listing.splitlines():
            mode,kind,rest=line.split(' ',2);blob,name=rest.split('\t')
            if kind!='blob': continue
            all_files[name]=(mode,blob)
            if '/include/' in name and name.endswith('.h'):
                installed=name.split('/include/',1)[1]
                published.setdefault(installed,[]).append(name)
        self.public_inventory=all_files;self.published_headers=published

    def resolve_header(self,name):
        if len(self.report.setdefault('resolved_public_headers',{}))>=64: raise ValueError('Public header closure bound reached')
        choices=self.published_headers.get(name,[])
        if not choices: return False
        hashes={self.public_inventory[p][1] for p in choices}
        if len(hashes)!=1: raise ValueError('Ambiguous native public header source: '+name+' '+str(choices))
        source=choices[0];links=[];revision='6982ddbfca1047c86680ec7c66da152789746efd'
        for level in range(5):
            mode,blob=self.public_inventory[source]
            data=self.primary_blob('https://raw.githubusercontent.com/PureDarwin/PureDarwin/'+revision+'/'+source,blob,'resolve-'+name.replace('/','_')+'-'+str(level),'PureDarwin/PureDarwin')
            if mode=='100644': break
            if mode!='120000': raise ValueError('Unreviewed public header file mode')
            links.append(dict(path=source,git_blob_sha1=blob,target=data.decode().strip()))
            source=posixpath.normpath(posixpath.join(posixpath.dirname(source),data.decode().strip()))
            if not source.startswith('src/Libraries/'): raise ValueError('Public source symlink escapes source boundary')
        else: raise ValueError('Public source symlink loop')
        target=self.installed_headers/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        raw=self.out/'headers'/name;raw.parent.mkdir(parents=True,exist_ok=True);raw.write_bytes(data)
        row=dict(repository='https://github.com/PureDarwin/PureDarwin',revision=revision,source_path=source,source_symlink_chain=links,git_blob_sha1=blob,sha256=sha(raw))
        self.header_manifest[name]=row;self.report['resolved_public_headers'][name]=row
        return True

    def header_closure(self):
        self.inputs();self.setup_headers();self.header_inventory()
        shutil.copytree(self.header_parent/'headers',self.out/'headers')
        flags=['-target','arm64-apple-ios16.5','-resource-dir',self.resource,'-fPIC','-O3','-fvisibility=hidden','-DVISIBILITY_HIDDEN','-Wall','-fomit-frame-pointer','-mkernel','-DKERNEL_USE','-nostdinc','-isystem',self.resource/'include','-I',self.source/'include',*[item for p in self.extra_includes for item in ['-isystem',p]]]
        self.feature_profile(flags);self.select_sources()
        if self.features['COMPILER_RT_HAS_ASM_LSE']: flags+=['-DHAS_ASM_LSE']
        objects=self.out/'survey-objects';objects.mkdir();failures=[]
        for index,source in enumerate(self.sources):
            for attempt in range(25):
                label='closure-'+str(index)+'-'+str(attempt);obj=objects/(str(index)+'-'+source.stem+'.o')
                self.run([COMPILER,*flags,*self.source_flags.get(str(source),[]),'-c',source,'-o',obj],label,allowed=(0,1))
                if self.report['commands'][-1]['exit_code']==0: break
                diagnostic=(self.out/(label+'.stderr.txt')).read_text()
                missing=re.findall(r"fatal error: '([^']+)' file not found",diagnostic)
                if len(missing)!=1 or not self.resolve_header(missing[0]):
                    failures.append(dict(source=relative(source),diagnostics=self.report['commands'][-1]['stderr']));break
            else: raise ValueError('Per-source public dependency closure bound reached')
        self.report['header_closure']=dict(selected_sources=len(self.sources),failures=failures,scope='Adaptive compile survey only;final archive requires fresh all-source compile against stable verified declaration snapshot')
        dump(self.out/'public-header-files.json',self.header_manifest)
        self.report['public_headers']=dict(root=relative(self.out/'headers'),files=len(self.header_manifest),scope='Exact public source declaration closure;no SDK binaries or fabricated types')
        if failures: raise RuntimeError('Public declaration closure unresolved for '+str(len(failures))+' sources')
        self.report['outcome']='pass'

    def build(self):
        self.inputs()
        if self.args.headers_run: self.setup_headers()
        flags=['-target','arm64-apple-ios16.5','-resource-dir',self.resource,'-fPIC','-O3','-fvisibility=hidden','-DVISIBILITY_HIDDEN','-Wall','-fomit-frame-pointer','-mkernel','-DKERNEL_USE','-nostdinc','-isystem',self.resource/'include','-I',self.source/'include',*[item for p in self.extra_includes for item in ['-isystem',p]]]
        self.feature_profile(flags);self.select_sources()
        if self.features['COMPILER_RT_HAS_ASM_LSE']: flags+=['-DHAS_ASM_LSE']
        directory=self.out/'objects';directory.mkdir();objects=[]
        failed=[]
        for index,source in enumerate(self.sources):
            output=directory/(str(index)+'-'+source.stem+'.o')
            self.run([COMPILER,*flags,*self.source_flags.get(str(source),[]),'-MD','-MF',output.with_suffix('.d'),'-c',source,'-o',output],'compile-'+str(index)+'-'+source.stem,allowed=(0,1))
            if self.report['commands'][-1]['exit_code']!=0: failed.append(dict(source=relative(source),diagnostics=self.report['commands'][-1]['stderr']))
            else: objects.append(output)
        dependencies={}
        for obj in objects:
            text=obj.with_suffix('.d').read_text().replace('\\\n','')
            for token in shlex.split(text.split(':',1)[1]):
                path=Path(token)
                if not path.is_absolute(): path=WORK/path
                if not path.resolve().is_relative_to(MAIN): raise ValueError('Unexpected non-project/native-public dependency: '+str(path))
                dependencies[relative(path)]=sha(path)
        dump(self.out/'dependency-files.json',dependencies)
        self.report['dependency_files']=len(dependencies)
        self.report['compile_survey']=dict(selected=len(self.sources),compiled=len(objects),failures=failed)
        if failed: raise RuntimeError('Genuine native compilation failed for '+str(len(failed))+' sources;exact diagnostics retained')
        archive=self.resource/'lib/darwin/libclang_rt.cc_kext_ios.a';archive.parent.mkdir(parents=True)
        self.run([self.libtool,'-static','-o',archive,*objects],'genuine-native-runtime-archive')
        self.report['archive']=dict(path=relative(archive),sha256=sha(archive),objects=len(objects))
        self.inspect_archive(archive,objects);self.host_semantics()
        self.report['outcome']='pass'

    def recheck_build(self):
        parent,old=self.qualified_parent(self.args.build_run,outcomes=('fail',))
        self.check('precise-prior-native-build-and-host-UBSan-failure',old.get('error')=="RuntimeError('host-genuine-integer-semantics-execute failed')" and old['compile_survey']['compiled']==old['compile_survey']['selected']==287 and old['checks'][-1]['name']=='genuine-integer-and-profile-exports' and all(c['pass_check'] for c in old['checks']))
        diagnostic=(MAIN/old['commands'][-1]['stderr']).read_text()
        self.check('retained-real-source-UBSan-negative-shift','ashrti3.c:34:34: runtime error: left shift of negative value -1' in diagnostic)
        self.check('original-selected-native-compiler-preserved',sha(COMPILER)==COMPILER_SHA and old['compiler']['sha256']==COMPILER_SHA)
        source_parent,source_report=self.qualified_parent(self.args.source_run)
        self.source=MAIN/source_report['source_tree']['root']
        self.libtool=MAIN/'artifacts/xnu-macho-tools/macho-session4/prefix/bin/aarch64-apple-darwin-libtool'
        self.ld=MAIN/'artifacts/xnu-macho-tools/macho-session4/prefix/bin/aarch64-apple-darwin-ld'
        for path,digest in json.loads((parent/'dependency-files.json').read_text()).items():
            if sha(MAIN/path)!=digest: raise ValueError('Changed actual native compilation dependency: '+path)
        for name in ['objects','resource']: shutil.copytree(parent/name,self.out/name)
        for key in ['compiler','runtime_source_inputs','driver_sources','selection','native_feature_profile','compile_survey','tools_sha256']:
            self.report[key]=old[key]
        self.patched_source=self.out/'patched-source';shutil.copytree(self.source,self.patched_source)
        patch_inputs=self.out/'runtime-patch';shutil.copytree(WORK/'patches/cc-kext-runtime',patch_inputs)
        patch=patch_inputs/'0001-ashrti3-unsigned-cross-word-shift.patch'
        pin=json.loads((patch_inputs/'source-pin.json').read_text())
        original=self.source/'lib/builtins/ashrti3.c';corrected=self.patched_source/'lib/builtins/ashrti3.c'
        self.check('exact-original-source-and-unsigned-shift-patch',pin['revision']==REVISION and sha(original)==pin['base_sha256'] and sha(patch)==pin['patch_sha256'])
        option='--directory='+str(self.patched_source.relative_to(WORK))
        self.run(['git','apply','--check',option,patch],'unsigned-shift-patch-exact-base-check')
        self.run(['git','apply',option,patch],'unsigned-shift-patch-owned-source-apply')
        self.check('exact-corrected-source-bytes',sha(corrected)==pin['patched_sha256'])
        self.run(['git','apply','--check',option,patch],'already-corrected-source-negative-patch-check',allowed=(1,))
        changed=[name for name,row in old['runtime_source_inputs'].items() if sha(self.patched_source/name)!=row['sha256']]
        self.check('only-one-selected-runtime-source-body-changed',changed==['lib/builtins/ashrti3.c'])
        members=json.loads((parent/'archive-members.json').read_text())
        row=next(r for r in members if '___ashrti3' in r['defined'])
        member=row['name'];output=self.out/'objects'/member
        process=next(c for c in old['commands'] if '-o' in c['argv'] and c['argv'][c['argv'].index('-o')+1]==str(parent/'objects'/member))
        argv=process['argv'].copy();argv[argv.index(str(original))]=str(corrected)
        argv[argv.index('-o')+1]=str(output);argv[argv.index('-MF')+1]=str(output.with_suffix('.d'))
        self.run(argv,'actual-only-corrected-native-translation-unit-build')
        before=object_symbols((parent/'objects'/member).read_bytes());after=object_symbols(output.read_bytes())
        self.check('corrected-native-symbol-ABI-surface-unchanged',before==after)
        self.run([NDK/'llvm-objdump','-d',parent/'objects'/member],'original-native-shift-disassembly')
        self.run([NDK/'llvm-objdump','-d',output],'corrected-native-shift-disassembly')
        retained=[r for r in members if r['name']!=member]
        self.check('all286-other-native-object-bytes-retained',len(retained)==286 and all(sha(self.out/'objects'/r['name'])==r['sha256'] for r in retained))
        archive=self.out/'resource/lib/darwin/libclang_rt.cc_kext_ios.a'
        objects=[self.out/'objects'/r['name'] for r in members]
        self.run([self.libtool,'-static','-o',archive,*objects],'genuine-runtime-rearchive-with-only-corrected-member')
        self.report['reused_native_build']=dict(evidence=relative(parent/'evidence.json'),sha256=sha(parent/'evidence.json'),retained_objects=286,recompiled_objects=1,scope='Original287 actual native compile/dependency witnesses retained;one unsigned-shift-corrected TU compiled with same native flags and full genuine archive rebuilt')
        self.report['source_correction']=dict(**pin,patch_path=relative(patch),original_object_sha256=sha(parent/'objects'/member),corrected_object_sha256=sha(output),original_archive_sha256=old['archive']['sha256'])
        self.report['archive']=dict(path=relative(archive),sha256=sha(archive),objects=287)
        dependencies=json.loads((parent/'dependency-files.json').read_text())
        text=output.with_suffix('.d').read_text().replace('\\\n','')
        dependencies.update({relative(Path(t)):sha(Path(t)) for t in shlex.split(text.split(':',1)[1])})
        dump(self.out/'dependency-files.json',dependencies);self.report['dependency_files']=len(dependencies)
        self.inspect_archive(archive,objects);self.host_semantics()
        self.report['outcome']='pass'

    def driver_link(self,name,resource,object_path,expected_library,positive=False,literal=False):
        output=self.out/('probe-'+name)
        argv=[COMPILER,'-target','arm64-apple-ios16.5','-mkernel','-nostdlib','-static','-resource-dir',resource,'--ld-path='+str(self.ld_wrapper),'-Wl,-e,_s24_runtime_link_probe',object_path,'-Wl,-lcc_kext' if literal else '-lcc_kext','-o',output]
        self.run([*argv,'-###'],'driver-'+name+'-expansion')
        expansion=(self.out/('driver-'+name+'-expansion.stderr.txt')).read_text()
        backend=[]
        for line in expansion.splitlines():
            tokens=shlex.split(line)
            if tokens and tokens[0]==str(self.ld_wrapper): backend.append([str(self.ld),*tokens[1:]])
        self.check(name+'-one-genuine-backend-expansion',len(backend)==1)
        expected=str(resource/'lib/darwin/libclang_rt.cc_kext_ios.a')
        self.check(name+'-exact-compiler-resource-lookup',backend[0].count(expected)==(1 if expected_library else 0))
        self.check(name+'-reserved-library-expansion',('-lcc_kext' in backend[0])==literal)
        self.run(argv,'driver-'+name+'-execute',allowed=(0,1))
        code=self.report['commands'][-1]['exit_code']
        journal=self.out/('backend-probe-'+name+'.json')
        observed=json.loads(journal.read_text())
        self.check(name+'-actual-executed-backend-argv-matches-expansion',observed['argv']==backend[0])
        self.report.setdefault('driver_links',{})[name]=dict(exit_code=code,expanded_backend=backend[0],actual_backend_journal=relative(journal),resource=relative(resource),output_exists=output.is_file(),output_sha256=sha(output) if output.is_file() else None)
        if positive:
            self.check(name+'-actual-link-success',code==0 and output.is_file())
            text=self.run([NDK/'llvm-nm','--undefined-only','--just-symbol-name',output],'positive-no-unresolved-imports')
            self.check('tiny-helper-link-has-no-unresolved-imports',not text.strip())
            self.run([NDK/'llvm-readobj','--file-headers','--symbols',output],'positive-actual-MachO-image-inspection')
            text=self.run([NDK/'llvm-nm','--defined-only','--just-symbol-name',output],'positive-actual-helper-providers')
            self.check('actual-linked-genuine-helper-providers',{'___divti3','___modti3','___multi3','___udivti3','___umodti3','___ashrti3','_s24_runtime_link_probe'}<=set(text.splitlines()))
        else: self.check(name+'-actual-invalid-link-fails',code!=0 and not output.exists())

    def stop_control(self):
        ids=self.out/'owned-stop-pids.json'
        try: self.run([sys.executable,self.fixture_root/'owned-child-stop.py',ids],'owned-ignore-term-timeout-control',timeout=.5)
        except RuntimeError:
            row=self.report['commands'][-1]
            doc=json.loads(ids.read_text())
            self.check('actual-owned-parent-child-session',doc['group']==doc['child_group']==row['owned_process_group'])
            self.check('actual-finite-owned-SIGKILL-escalation',row['stop_reason']=='timeout' and row['sigkill_escalated'] and row['exit_code']==-9 and not row['remaining_live_owned_children'] and not live_group(row['owned_process_group']))
        else: raise ValueError('Owned timeout fixture unexpectedly returned normally')

    def controls(self):
        parent,report=self.qualified_parent(self.args.build_run)
        self.check('actual-parent-runtime-build',report.get('mode','build') in {'build','build-recheck'} and report['outcome']=='pass')
        self.check('same-selected-original-compiler',report['compiler']['sha256']==COMPILER_SHA and sha(COMPILER)==COMPILER_SHA)
        archive=MAIN/report['archive']['path']
        self.check('exact-compiled-parent-archive',sha(archive)==report['archive']['sha256'])
        self.ld=MAIN/'artifacts/xnu-macho-tools/macho-session4/prefix/bin/aarch64-apple-darwin-ld'
        self.libtool=MAIN/'artifacts/xnu-macho-tools/macho-session4/prefix/bin/aarch64-apple-darwin-libtool'
        self.report['tools_sha256']={str(p):sha(p) for p in [COMPILER,self.ld,self.libtool,NDK/'llvm-nm',NDK/'llvm-ar',NDK/'llvm-readobj']}
        source_parent,source_report=self.qualified_parent(self.args.source_run)
        self.source=MAIN/source_report['source_tree']['root']
        original_resource=Path(self.run([COMPILER,'-print-resource-dir'],'original-resource-before').strip())
        original_archive=original_resource/'lib/darwin/libclang_rt.cc_kext_ios.a'
        self.check('original-default-runtime-absent',not original_archive.exists())
        self.report['parent_build']=dict(path=relative(parent/'evidence.json'),sha256=sha(parent/'evidence.json'),archive=relative(archive),archive_sha256=sha(archive))
        objects=[parent/'objects'/row['name'] for row in json.loads((parent/'archive-members.json').read_text())]
        roots={name:self.out/('resource-'+name) for name in ['positive','missing','corrupt','incomplete','foreign','platform']}
        for root in roots.values(): (root/'lib/darwin').mkdir(parents=True)
        runtime=lambda root:root/'lib/darwin/libclang_rt.cc_kext_ios.a'
        self.run([self.libtool,'-static','-o',runtime(roots['positive']),*objects],'deterministic-native-runtime-rearchive')
        second=self.out/'deterministic-second.a'
        self.run([self.libtool,'-static','-o',second,*objects],'deterministic-native-runtime-replay')
        self.check('native-archive-byte-reproducible-with-ZERO_AR_DATE',sha(second)==sha(runtime(roots['positive'])))
        self.inspect_archive(runtime(roots['positive']),objects)
        self.ld_wrapper=self.out/'trace-native-ld.py'
        self.ld_wrapper.write_text('#!/usr/bin/python3\nimport json,os,sys\nfrom pathlib import Path\nargs=sys.argv[1:]\nname=Path(args[args.index("-o")+1]).name if "-o" in args else "query-"+str(os.getpid())\np=Path('+repr(str(self.out))+')/("backend-"+name+".json")\nreal='+repr(str(self.ld))+'\np.write_text(json.dumps({"argv":[real,*args],"pid":os.getpid(),"process_group":os.getpgrp()},indent=2)+"\\n")\nos.execv(real,[real,*args])\n')
        self.ld_wrapper.chmod(0o755)
        probe=self.out/'link-probe.o'
        flags=['-target','arm64-apple-ios16.5','-mkernel','-O1','-ffreestanding','-fno-builtin']
        self.run([COMPILER,*flags,'-c',self.fixture_root/'link-probe.c','-o',probe],'actual-ARM64-helper-link-probe-build')
        self.driver_link('positive',roots['positive'],probe,True,positive=True)
        self.driver_link('missing',roots['missing'],probe,False)
        original=runtime(roots['positive']).read_bytes()
        runtime(roots['corrupt']).write_bytes(b'?'+original[1:])
        try: archive_members(runtime(roots['corrupt']).read_bytes())
        except ValueError: self.check('real-corrupt-archive-guard-rejects',True)
        else: raise ValueError('Corrupt runtime accepted')
        self.driver_link('corrupt',roots['corrupt'],probe,True)
        member=next(row['name'] for row in json.loads((parent/'archive-members.json').read_text()) if '___udivti3' in row['defined'])
        shutil.copyfile(runtime(roots['positive']),runtime(roots['incomplete']))
        self.run([NDK/'llvm-ar','d',runtime(roots['incomplete']),member],'real-incomplete-runtime-remove-genuine-member')
        self.check('real-incomplete-member-count-guard-rejects',len(archive_members(runtime(roots['incomplete']).read_bytes()))!=len(objects))
        self.driver_link('incomplete',roots['incomplete'],probe,True)
        for name,target in [('foreign','x86_64-apple-macos13'),('platform','arm64-apple-macos13')]:
            obj=self.out/(name+'-genuine-udivti3.o')
            self.run([NDK/'clang' if name=='foreign' else COMPILER,'-target',target,'-mkernel','-O3','-nostdinc','-isystem',parent/'resource/include','-c',self.source/'lib/builtins/udivti3.c','-o',obj],name+'-actual-genuine-source-build')
            self.run([self.libtool,'-static','-o',runtime(roots[name]),obj],name+'-actual-genuine-source-archive')
            self.run([NDK/'llvm-readobj','--file-headers',obj],name+'-independent-profile-inspection')
            try: object_symbols(obj.read_bytes())
            except ValueError as error: self.report.setdefault('negative_guards',{})[name]=str(error)
            else: raise ValueError('Wrong target runtime accepted')
            self.check('real-'+name+'-profile-guard-rejects',True)
            self.driver_link(name,roots[name],probe,True)
        self.driver_link('literal-bypass',roots['positive'],probe,False,literal=True)
        self.check('original-compiler-and-resource-preserved',sha(COMPILER)==COMPILER_SHA and not original_archive.exists())
        self.stop_control()
        self.report['qualified_component']=dict(kind='genuine-public-compiler-runtime',archive=relative(runtime(roots['positive'])),archive_sha256=sha(runtime(roots['positive'])),resource_dir=relative(roots['positive']),resource_scope='Link-only explicit driver resource tree;retain separately qualified headers for kernel compiles',compiler=relative(COMPILER),compiler_sha256=COMPILER_SHA,source_revision=REVISION,archive_members=len(objects),target='arm64-apple-ios16.5',cpu_subtype='plain ARM64;no arm64e/PAC qualification',all_selected_functions_preserved=True,source_correction=report.get('source_correction'),exact_upstream_source=False,corecrypto_provider=False,full_kernel_qualified=False,full_runtime_behavior_qualified=False,apple_private_abi_qualified=False,device_executed=False)
        dump(self.out/'qualified-component.json',self.report['qualified_component'])
        self.report['outcome']='pass'

    def finish(self):
        self.report['summary']='Pinned genuine compiler-rt source and Darwin ARM64 cc_kext qualification;physical/private/full-kernel claims remain false'
        dump(self.out/'report.json',self.report)
        artifacts=[p for p in self.out.rglob('*') if p.is_file() and p.name!='evidence.json']
        evidence={k:self.report[k] for k in ['kind','origin','outcome','recorded_at','commands','commit','summary','device_executed']}
        evidence.update(artifacts=[relative(p) for p in artifacts],sha256={relative(p):sha(p) for p in artifacts})
        dump(self.out/'evidence.json',evidence)
        print(json.dumps(dict(outcome=self.report['outcome'],error=self.report.get('error'),evidence=relative(self.out/'evidence.json'))))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run',required=True);parser.add_argument('--mode',choices=['source','recover-source','public-headers','supplement-headers','header-closure','build','build-recheck','controls'],required=True)
    parser.add_argument('--source-run')
    parser.add_argument('--headers-run')
    parser.add_argument('--build-run')
    args=parser.parse_args()
    if not args.run or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in args.run): parser.error('Canonical fresh run required')
    runner=Runner(args)
    try:
        if args.mode=='source': runner.source()
        elif args.mode=='recover-source': runner.recover_source()
        elif args.mode=='public-headers': runner.public_headers()
        elif args.mode=='supplement-headers': runner.supplement_headers()
        elif args.mode=='header-closure': runner.header_closure()
        elif args.mode=='build': runner.build()
        elif args.mode=='build-recheck': runner.recheck_build()
        else: runner.controls()
    except Exception as error: runner.report['error']=repr(error)
    runner.finish();return 0 if runner.report['outcome']=='pass' else 1

if __name__=='__main__':
    resource.setrlimit(resource.RLIMIT_CORE,(0,0));sys.exit(main())
