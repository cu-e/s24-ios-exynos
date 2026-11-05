# Selected setup source attribution

The project-owned runner queries original target genassym/Make/sed rules and
stamps copied version templates using genuine newvers.pl. It supplies no manual
layout offsets or private Apple build/SDK identity.

Source is the recorded prepared Apple XNU8796.121.2 tree at
`c54f35ca767986246321eb901baf8f5ff7923f6a`, after the E1S donor patch set at
`c8860decc62c6d6180e609036d027a2997972420` and the recorded STM coordinate fix.
The prepared-tree witness and per-source hashes identify the actual base;
this patch is not described as applying to an unmodified Apple checkout.

`0001-startup-minimac-declaration-guard.patch` moves an existing declaration
outside CONFIG_VNGUARD while retaining CONFIG_MACF. Its call is under CONFIG_MACF,
and the actual definition in bsd/kern/kern_minimac.c has the same void(void)
signature. No function implementation, policy behavior or compiler check changes.
The runner copies startup.c, checks/applies the patch and records original,
patched source, implementation and patch hashes. The old source tree is intact.

Preserve original APSL2.0 and CMU notices in genassym.c/startup.c/version.c and
all per-file notices. version.h.template retains its distinct APSL1.1 notice.
Generated files/assembly/objects and builder identity remain in ignored local
artifacts. Public manifests include only necessary paths/hashes/measurements.
The Linux adapter byte-copies templates instead of executing BSD install -S;
genuine Perl stamping determines their final contents. No global installation
or native-device permission is implied.
