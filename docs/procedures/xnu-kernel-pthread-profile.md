# Genuine pthread kext source and installed-header profile

KRN-022,owner codex-kernel-pthread-profile-20261105-ag,parent ca68d2b.
The previous goal turn made concrete progress:four real source fixes resolve
three direct source-symbol gaps,with24 final checks and132 repository tests.
This work is host-only. Preserve all original prefixes and KRN-004/KRN-008/
KRN-003 owners. No phone,root,reboot,flash,SDK acquisition or global install.

Use pinned [libpthread kext configuration](https://github.com/apple-oss-distributions/libpthread/blob/a6c70ca0e544347a0377babf748f831577ec24f9/xcodescripts/kext.xcconfig),
[XNU header install rules](https://github.com/apple-oss-distributions/xnu/blob/c54f35ca767986246321eb901baf8f5ff7923f6a/makedefs/MakeInc.rule)
and [native definitions](https://github.com/apple-oss-distributions/xnu/blob/c54f35ca767986246321eb901baf8f5ff7923f6a/makedefs/MakeInc.def).
The local pinned primary checkout is available;current web fetches of pthread
source pages timed out,which does not establish absence of source or support.

New source review refines the earlier direct-object import inventory. The
three historical pthread imports absent by their public names are genuine
native export aliases in Private.exports/Private.arm64.exports. KLINK-011's
actual all-alias.exp maps them to mach_vm_allocate_external,mach_vm_map_external
and vm_fault_external,all present in the current SGAP-001 graph. Verify real
link resolution and correct signatures,including the seven-argument external
vm_fault ABI versus its eight-argument internal form. No new VM stub is needed.

KLINK-003/006 mixed internal EXPORT_HDRS/raw kernel bodies with a kext build.
The real kext configuration sets XNU_KERNEL_PRIVATE,MACH_KERNEL_PRIVATE,
ABSOLUTETIME_SCALAR_TYPE,NEEDS_SCHED_CALL_T and __PTHREAD_EXPOSE_INTERNALS__,but
its Kernel.framework headers have first passed native unifdef installation.
MakeInc.def's K[P]INCFRAME_UNIFDEF removes XNU-only private implementation
branches. Defining flags later cannot restore physically removed header code.
Generate and witness that real installed-header profile instead of relaxing
features or deleting compiler errors. Current real allocator metadata checks
remain enabled;the historical fake metadata header is forbidden.

Register experiments before execution. Query actual INSTINC recursion and
INSTALL_KF lists for public/private MI/MD headers. Install source-backed
headers through actual native recipes in owned output,using qualified unifdef,
genuine decomment and replacecontents. Generated/missing inputs require real
provenanced producers;retain unavailable entries explicitly. Do not invent a
complete SDK claim from a source-generated subset or fallback to raw internals.
Keep original target,board,feature and callback profile requirements visible.

Compile all three real typed pthread TUs with the current source-built compiler
and genuine kext definitions. Independently inspect actual ARM64 objects,
archive members,callback/function-pointer layouts,allocator metadata,all imports
and real native aliases. Use meaningful wrong-header/type/alias negative controls.
Full private Apple ABI,SDK,crypto,link/runtime,native GPU/Wi-Fi/SIM/eSIM and
recovery remain separate gates. All four acceptance criteria and make check
must pass before completion;exact failed/unavailable inputs remain useful evidence.
