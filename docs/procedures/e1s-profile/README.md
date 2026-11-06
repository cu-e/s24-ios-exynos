# Coherent E1S source profile

`python3 tools/build/prepare_xnu.py --root MAIN --run NEW` now emits the usual
fresh patched XNU source, `prepared-source-manifest.json` (all source files,
excluding Git administration), `e1s-profile.json` and the bound `report.json`.
The default without --root remains the current checkout's pinned references.
No compiler is invoked. This is the existing preparation path, not a replacement
build system. `pins.json` rejects revision, header, topology and patch mismatch.

The profile records source capacity MAX_CPUS10, MAX_CPU_CLUSTERS4 and
MAX_CPU_CLUSTER_PHY_ID9. It separately records the donor packer's default
`debug=0xc serial=3 cpus=1 keepsyms=1`; the donor SMP table is source data, not
observed MPIDRs. Source timer25.6MHz/INTID27 and GICv3 distributor/redistributor
addresses agree between donor ADT and loader declarations. Actual boot CPUs,
CNTFRQ, delivered interrupts, complete live DTB and safe physical RAM are unknown.
No synthetic default RAM range is promoted to the hardware profile.

The exact Applec54/c886 source series and STM correction705cba are retained.
The loader23b31 memory patch is required and bound to its accepted ordinary
builder; selected c886/57d0 loader compatibility reuses STR002's accepted witness.
The later57d0 UART/watchdog patches are not selected by this profile. Existing
source/component licenses remain unchanged; this fixture contains hashes and
owned metadata, not redistributed generated third-party source bodies.

A future consumer must select the real kernel configuration, regenerate coherent
E1S headers/types and qualify dependency objects/archives. The native98x RELEASE
objects and BCM2837 guest products are not automatically reusable E1S outputs.
See development-procedure.md for the exact next source-generation commands.

INT002's frozen export diagnosis a644f481/5c29dc1, export-diagnosis.json
SHA dde97bef1b1e6de5809bdbe933f5d192aec076cc398673008ba3f54634f01d95,
separates the 37 full native ABI gaps from unestablished E1S body callers:
17 UAT class/layout/methods, seven pmap_iommu, eleven DART/SART/UAT/NVMe PPL,
and two pmap security queries. No matching public selected ARM64 providers are
supplied. Genuine MakeInc.def811–820 does not pass the RELEASE export list to
a DEVELOPMENT direct link; config/Makefile120–145 still independently checks
private exports/builds symbol sets. This permits investigating a supported
DEVELOPMENT E1S body diagnostic without deleting exports or claiming full ABI
closure. KRN001/KRN026 remain blocked under their original owners.
