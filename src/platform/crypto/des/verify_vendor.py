#!/usr/bin/env python3
"""Verify every vendored upstream byte against the accepted complete pinned archive."""
from pathlib import Path
import difflib,hashlib,json,tarfile
HERE=Path(__file__).resolve().parent
MAIN=Path('/home/egor/dev/pet/s24-ios-exynos')
PIN='068ff080b369adfac81509f9b57b2afabaf82dc5'
ARCHIVE_SHA='ca6bd316bbec49ef20088f39b8755fcaec0b7e45781506de55b17cd191ae6937'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def verify():
 archive=MAIN/'worktrees/krn-029-20261105/artifacts/crypto-xts/inputs/mbedtls.tar.gz'
 raw=archive.read_bytes()
 if sha(raw)!=ARCHIVE_SHA:raise ValueError('complete qualified upstream archive changed')
 v=HERE/'vendor';prov=json.loads((v/'provenance.json').read_text())
 if prov['commit']!=PIN or prov['archive_sha256']!=ARCHIVE_SHA or prov['license_choice']!='Apache-2.0':raise ValueError('source/profile pin mismatch')
 expected={'LICENSE','library/des.c','library/common.h','library/alignment.h','library/ctr.h'}|{'include/mbedtls/'+n+'.h' for n in ['des','private_access','build_info','config_adjust_legacy_crypto','config_adjust_x509','config_adjust_ssl','check_config','platform_util','platform','error']}
 if set(prov['files'])!=expected or set(prov['patches'])!={'library/common.h'}:raise ValueError('unexpected vendored upstream set/patch')
 result={'archive':str(archive),'archive_sha256':ARCHIVE_SHA,'commit':PIN,'upstream_url':'https://github.com/Mbed-TLS/mbedtls/archive/'+PIN+'.tar.gz','source_transport':'read-only independently qualified complete XTS cached archive; no new network acquisition','files':{},'patches':{}}
 with tarfile.open(archive) as t:
  names=t.getnames()
  for name in sorted(expected):
   member='mbedtls-'+PIN+'/'+name
   if names.count(member)!=1:raise ValueError('missing/duplicate archive member '+name)
   source=t.extractfile(member).read();wanted=source
   if name=='library/common.h':
    if source.count(b'#include <assert.h>')!=1:raise ValueError('unexpected canonical patch preimage')
    # Named, exact unused-include portability patch. No algorithm function changes.
    wanted=source.replace(b'#include <assert.h>',b'/* DES software unit has no runtime assert; omit unused libc header. */\n#if !defined(S24_DES_FREESTANDING)\n#include <assert.h>\n#endif')
    patch=''.join(difflib.unified_diff(source.decode().splitlines(True),wanted.decode().splitlines(True),fromfile='a/library/common.h',tofile='b/library/common.h')).encode()
    if (v/'common-freestanding.patch').read_bytes()!=patch:raise ValueError('patch file does not produce exact postimage')
    p=prov['patches'][name]
    if p['upstream_sha256']!=sha(source) or p['local_sha256']!=sha(wanted):raise ValueError('patch pre/post metadata differs from canonical bytes')
    result['patches'][name]={'upstream_sha256':sha(source),'postimage_sha256':sha(wanted),'patch_sha256':sha(patch),'algorithm_bodies_changed':False}
   actual=(v/name).read_bytes()
   if actual!=wanted or sha(actual)!=prov['files'][name]:raise ValueError('vendored canonical member mismatch '+name)
   result['files'][name]={'canonical_member':member,'canonical_sha256':sha(source),'canonical_bytes':len(source),'actual_sha256':sha(actual),'actual_bytes':len(actual),'patched':name in prov['patches']}
 # Omission of assert.h is justified by the actual selected DES translation unit.
 source=(v/'library/des.c').read_text()
 import re
 if re.search(r'\bassert\s*\(',source):raise ValueError('DES primitive now requires real assert dependency')
 result['assert_call_count_des_translation_unit']=0
 result['outcome']='pass'
 return result
if __name__=='__main__':print(json.dumps(verify(),indent=2))
