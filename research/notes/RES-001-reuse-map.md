# RES-001 source and reuse decisions

The source registry pins the selected repositories. `tools/sources.py verify` checks actual checkout SHA, origin, cleanliness and reviewed-file digests. Sparse donor checkouts contain selected documentation, not a transitive build environment. No firmware, IPSW, SDK or submodule was fetched. This is a source review, not a device experiment.

| Source | Decision | License/provenance boundary |
|---|---|---|
| S24 c8860de | Keep as exact loader, E1S delta and protocol-test baseline | Loader GPL-2.0-only; XNU APSL; APFS tools MIT. Preserve individual headers. |
| Embedded HakiOS d82c64a | Keep the version embedded by S24 | APSL for XNU-derived changes; component notices apply. Current HakiOS is a separate donor. |
| Current HakiOS 87bf485 | Review newer shared interfaces separately | LICENSE MIT and LICENSE.APSL were read. Do not apply current hardware initialization to E1S. |
| S20+ 68fe2e9 | Adapt concepts for UFS, power and Metal integration | LICENSE/NOTICE reviewed: own MIT work, APSL XNU/HFS, Mesa MIT, brcmfmac ISC and component notices. No blanket MIT relicensing. |
| S9 8ee7538 | Architectural donor only; exact file licensing required before code reuse | Sparse README review is not a file-level license audit. Keep the existing per-file verification requirement. |
| RADV fe9b894 | Android custom-driver candidate; later adapt winsys | Third-party notices reviewed: Mesa primarily MIT, additional per-file licenses and fetched dependencies. No native kernel backend provided. |
| metal2vulkan 219f013 | Host translator candidate, later Metal frontend component | LICENSE reviewed: GPL-2.0-or-later OR LGPL-3.0-or-later. Choose and preserve an applicable distribution arrangement before linking/distribution. |
| UniXNU c740efb | Interface/architecture donor, not a drop-in S24 platform | BSD-2-Clause-Patent repository license; component/dependency licenses remain distinct. |
| Silicium 6b3d90b | e1s display/memory/boot limitations | No e1s USB/storage control assumed. Vendor/component notices must be retained before reuse. |
| Samsung BSP 4174841 / reference f85e53c | Register, wiring and protocol research | Linux GPL-2.0 and file headers; do not copy incompatible code wholesale into APSL XNU. Firmware matching remains unresolved. |

## Keep, adapt, replace, missing

- Keep E1S board identity, guarded initialization, read-only-first UFS, independent boot packaging checks and the distinction between owned PID 1 and Apple userland.
- Adapt generic XNU platform services, IOSurface/input/network boundaries and host tests after matching their ABI and source SHA.
- Replace Qualcomm-specific GPU, modem, audio and board power paths. Exact Wi-Fi is KIWI/CNSS, not the S9/S20 Broadcom controller.
- Missing or unverified: native execution, live memory reservations, recovery/control, Xclipse kernel services and Metal registration, real iOS userland on S24, radio/IMS/eUICC services, audio/camera/power qualification.

No donor's checked README box is local acceptance. The capability matrix and individual device evidence establish that separately. See [feasibility review](2026-11-05-feasibility.md) and [implementation contract](../../docs/implementation.md).
