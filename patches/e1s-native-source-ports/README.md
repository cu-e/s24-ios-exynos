# Preserved native declaration ports

These two patch files are exact unchanged copies of accepted local KRN-016
source ports recorded in fixtures/public/xnu-kernel-declarations/qualified-component.json.
Originals remain in artifacts/xnu-kernel-declarations/source-ports-session3.

- 0001-use-existing-kernel-printf-declaration.patch, SHA7c6e8ad0873d5dce32fcd954a52e0ef114cde74af79a9046f04ecb7f61ce087d:
  removes the redundant conflicting printf declaration in mc_provider.c so the
  genuine already-included kernel declaration is used.
- 0002-include-genuine-proc-declarations.patch, SHA164dbcc11c1518ece9f4d7dd4d0798787f0251d4158ac36f6ae0789e03031fc0:
  despite its historical filename, adds the genuine proc_pid prototype to
  user_exception_trace.c. It does not add a header include or function body.

STR014 only promotes these accepted bytes; it does not claim their original
authorship or introduce another source change. Source attribution and applicable
per-file notices/licenses, including the prepared tree's APPLE_LICENSE, remain
unchanged. No blanket license replaces upstream component terms.

Apply existing patches/kernel-symbol-gaps/0001-align-cache-alias-and-platform-guards.patch
SHA7426580b6b6fddae4b87b114ef3d294889413e5c69b76965a63af1eb86b1de0c
first, then these two files in order. That existing four-file patch is reused
at its original path, never edited or duplicated here. Exact source/pre/post
identities and producer qualification witnesses are in the scoped inputs.json.
No compiler/ABI/runtime qualification is implied by source application.
