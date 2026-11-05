# BearSSL public arithmetic dependency

Upstream: https://www.bearssl.org/git/BearSSL
Exact revision: `7bea48e5e850ab4cafbe68d3765cdaba13a86d6f`.
Author: Thomas Pornin and the copyright holders named in the original files.
License: MIT; complete LICENSE.txt and original per-file notices are retained.

All33 consumed source/header/license files were copied from canonical exact-pin
Git blobs, with blob framing/hash and SHA256 checks in provenance.json. They are
not copied from the older partial raw HTTP audit cache. All15 overlapping catalog
entries matched; the remaining needed files were independently obtained from the
same canonical Git tree. Source/header contents are unmodified.

Only the public i31 RSA operation, PKCS1-v1.5 verification/unpadding and their
listed nonallocating integer helpers are compiled. Public headers contain other
API declarations; their presence does not qualify or implement those methods.
Owned representation/OID/status/lifetime glue is outside this vendor directory.
The shared Mbed TLS zeroizer is imported from the accepted XTS component, with
its own retained license/provenance. No duplicate zeroizer is defined here.
