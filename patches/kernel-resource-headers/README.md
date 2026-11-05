# Matched compiler resource header attribution

Public apple-libtapi revision fa9443738c1a18accef4244732ec6d6ee97a8133 contains
LLVM/Clang17.0.6 TableGen and header sources. The local experimental compiler's
recorded XNU changes are separate from these unchanged generation rules.
No declaration replacement or generator source patch is used here.

Preserve actual Clang/LLVM component Apache2.0 licenses with LLVM exceptions,
all per-file notices and the generated ARM NEON header's own permission notice.
The top-level older TAPI/Apple licenses remain distinct. Generated resource
headers and host/target binaries remain in ignored local artifacts. A resource
header component is not an Apple SDK or private compiler ABI qualification.
