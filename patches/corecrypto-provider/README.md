# No corecrypto replacement patch

KRN-023 creates an input/source/ABI auditor and measurements, not a provider.
No archive, stub, algorithm replacement, callback substitution, feature removal
or provider startup patch is supplied here. Preserve original selected kernel
and donor artifacts and the eight previously sampled NULL callback observations.

Apple XNU `c54f35ca767986246321eb901baf8f5ff7923f6a` retains its APSL-2.0
and per-file notices. The selected donor directory at
`c8860decc62c6d6180e609036d027a2997972420` contains a HakiOS APSL license;
that does not establish a new blanket grant for all contributed minicrypto
code. Component provenance must remain separate. The public Apple corecrypto
`9612a959abb6eac0aac3ee6a7245c46365c9d81b` default license restricts evaluation
and redistribution; its named research text stays in ignored local storage.
No restricted Apple provider implementation is copied into maintained files.

Any future provider patch needs applicable rights, a pinned source/build profile,
exact target header/context/signature and initialization integration, and real
link/runtime assessment. Neither this audit nor algorithm KATs supplies those.

The selected driver's `-lcc_kext` token is compiler-runtime support, rewritten
by Clang's Darwin toolchain to a resource archive. It does not name or qualify
the crypto implementation described here. No libcc_kext crypto patch is needed
or supplied by this audit; compiler-runtime qualification is a separate gate.
