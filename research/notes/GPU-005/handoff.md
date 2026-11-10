# GPU-005 handoff — RADV build not run (2026-11-10)

Owner: `claude-takeover-20261110-6c8f`. Evidence category so far: none. Nothing was built and nothing ran on the phone.

## Done

- Narrowed GPU-005 to `src/android-probe/`, `src/graphics/radv`, `artifacts/gpu-005` and `research/notes/GPU-005`, then claimed it.
- Cloned `https://github.com/JimVulkan/radv-xclipse` at the pinned `fe9b8943aaeec11ed9fccbfcc382da07379afbe5` into the ignored `artifacts/gpu-005/radv-xclipse` (58 MB, clean tree).
- Created the ignored venv `artifacts/gpu-005/venv` with Mako 1.3.10, MarkupSafe 3.0.4 and packaging 25.0 (Mesa's generator modules).
- Wrote `src/graphics/radv/build.py`. It checks the pin and a clean tree, reproduces the upstream `build.sh` Meson options with NDK 28.2.13676358 (upstream tested r29) and API 34, and records commands, exit codes, tool versions, the output hash, NEEDED entries and exported functions. **It has never been executed.**

## Why it stopped

At 2026-11-10T07:07Z the Claude Code auto-mode classifier denied `python3 src/graphics/radv/build.py --run build-001` with reason "Code from External". A Meson/Ninja build runs the downloaded upstream build files and generators, and Meson downloads the libdrm, zlib and expat wrap sources (each checked against `source_hash`). Following the owner's rule, no other route was tried. `artifacts/gpu-005/build-001` was never created.

## To resume

The owner can either:
1. allow this command in Claude Code permissions (for example a Bash rule for `python3 src/graphics/radv/build.py`), or
2. run it themselves: `! python3 src/graphics/radv/build.py --run build-001`, and then let the agent continue from `artifacts/gpu-005/build-001/report.json`.

After a successful build, the remaining steps are:
- add an app-local loader variant to the probe: `dlopen` the bundled driver and use `vk_icdGetInstanceProcAddr`, without replacing any system library;
- give it a separate package name, so the qualified APK7 identity is untouched;
- run one frame with a short timeout, then compare it with GPU-016's stock baseline.
