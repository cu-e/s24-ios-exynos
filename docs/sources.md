# Sources and examples

`python3 tools/lab.py sources` lists primary sources. The selected S24, graphics, Exynos and platform snapshots now have full SHAs. Entries with revision=null remain research leads and cannot be fetched/reused by the source tool until pinned. [Reuse decisions](../research/notes/RES-001-reuse-map.md) record licensing and compatibility boundaries.

Use `python3 tools/sources.py fetch ID` for an explicit pinned checkout and `python3 tools/sources.py verify ID ...` for read-only provenance checks. Donor checkouts are sparse documentation reviews unless their registry entry says otherwise. Submodules, firmware and SDKs are not fetched automatically. See [procedure](procedures/sources-check.md).

| Example needed | Starting point |
|---|---|
| Exact e1s loader/patches | s24-port: README, E1S_PROGRESS, xnu/e1s/README, docs/e1s-hackios-port-map |
| S24 protocols and addresses | s24-linux, DTS from the exact firmware; compare with the s24-port hardware map |
| Exynos UFS, power and port structure | y2sios, scion-starlte; do not copy addresses automatically |
| Xclipse graphics inside Android | radv-xclipse |
| Metal/AIR → Vulkan | metal2vulkan |
| Common XNU and userland layers | hakios, unixnu |
| e1s UEFI limitations | silicium, Status.md |
| Separate emulator for older iOS | un1box; a different approach, not native validation |

Clone selected sources into references/<source-id>, check out a full SHA, and inspect git status and licenses. Do not fetch all repositories, submodules, toolchains or firmware without a task requirement. Do not execute upstream flash/install scripts during research.

Each project patch needs a source URL, base SHA, source file list, license/attribution, rationale, checks and limitations. Do not commit large upstream trees over src/.

research/snapshots contains a historical import from the 2026-11-05 review and is excluded from Git. That review did not measure the owner's device. Public research/notes can become stale; operational facts belong in state/lab.json and dated evidence.
