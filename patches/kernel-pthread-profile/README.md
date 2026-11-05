# Genuine pthread kext profile

Pinned Apple libpthread a6c70ca0e544347a0377babf748f831577ec24f9 and prepared
Apple XNU c54f35ca767986246321eb901baf8f5ff7923f6a/E1S witnesses. Preserve all
original source licenses (including APSL2.0 pthread/XNU and APSL1.0 decomment).
Use fresh source/header/build prefixes only. The existing typed source port
is a witnessed experimental starting point,not a proven selected Apple ABI.

Native Kernel.framework installed headers are distinct from XNU's internal
EXPORT_HDRS. Follow actual INSTALL_KF lists and K[P]INCFRAME_UNIFDEF,which remove
XNU-only private bodies during header installation. That is genuine SDK header
processing,not disabling kernel functionality. Do not fill absent headers with
invented declarations or silently mix raw internal headers into this profile.

The native selected export aliases map mach_vm_allocate,mach_vm_map,vm_fault
to existing real *_external implementations. Qualify exact alias/link and ABI
behavior;do not add substitute VM functions or successful syscall stubs.
No fake type metadata,empty SDK library or feature removal may produce a pass.
Host build adapters must preserve target header/source bytes and record limits.
