# Portable IIG selected-version work

Base: Nyktis/iig-port `ea6d147d668ca15d490da638012243fcd705f30d`.
License: MIT, copyright 2026 iig-port contributors. Preserve LICENSE.nyktis
and NOTICE.nyktis, including Zilong Tan's fasthash notice. Those licenses
apply to their components independently of this workspace.

`0001-explicit-selected-arm64-target.patch` permits exactly
`-target arm64-apple-ios16.5` alongside upstream's unknown-architecture mode.
It leaves other upstream target restrictions intact. The unpatched binary
rejects all 17 selected target invocations (IIGABI-001). This patch permits
an explicit actual compiler target for real type-width/AST checks; it does
not claim to reproduce Apple's original IIG target model or ABI.

0002-selected-legacy24-rpc.patch adapts the emitter to selected XNU's actual
24-byte IORPC: full inline content replaces the newer kernel content pointer,
and the existing public IORPCMessageFromMach API decodes the message. No fake
XNU field/prototype is added. Its banner labels this as an experiment;
Apple's selected generated-code equivalence remains unqualified.

0004-invoke-check-extents-before-access.patch follows 0001/0002 and checks
method-specific message/reply sizes and required pointers before generated
Invoke field access or optimizer nonnull assumptions. Actual host IIGABI-011
exposed four failing cases; IIGABI-013 passes all 11 controls, including a
guard-page boundary. Other dispatch/marshalling paths remain unqualified.

0003-host-linux-target-header.patch is separate from the generator series.
It applies to the full licensed RES-009 corrected TargetConditionals.h,
originating in PureDarwin6982ddbfca1047c86680ec7c66da152789746efd.
Preserve its APSL notice. This adds an accurate Linux/x86_64 host branch in
a private host-only copy; real ARM64 compiles retain the existing qualified
header. No SDK is synthesized.

The runner checks/applies patches to private artifact copies only. Original
checkouts and historical run bytes are preserved. No install script, Apple
SDK/test archive, or generated unsupported RPC stub is adopted.
