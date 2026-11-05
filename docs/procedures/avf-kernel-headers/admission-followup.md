# AVFADMIT-001: prospective stable admission guard

VM-008 original owner codex-team-avf-kernel-headers-20261105-cd.
Follow-up branch team/vm-008-admission-20261106 is separate from the frozen
original candidate 2b5aa36. Original descriptor/evidence/index/inputs remain
unchanged in worktrees/vm-008-20261105. This follow-up does not upgrade historical
single-sample runs into three-sample evidence.

Root's current resource queue rule requires three consecutive MemAvailable
samples >=4 GiB, separated by one second. Apply this prospective guard before
every new Headers.run subprocess, including metadata/query commands. Keep the
existing admitted-work post-launch floor/deadline/RSS/owned cleanup unchanged.
Record all attempted timestamped admission samples; any low or too-close sample
rejects before Popen. File-only verification and this probe spawn no subprocess.

Before execution register AVFADMIT-001 in sole MAIN for task VM-008. The bounded
probe imports the actual prospective helper, injects first-low/middle-dip/all-good
sample sequences with a simulated clock/sleep, verifies that failed admission
cannot reach Popen, and runs one actual read-only /proc/meminfo sequence at real
one-second spacing. The actual observation may honestly pass or reject on low
memory; control pass requires correct decision/spacing, not available memory.
No compiler, headers/TUs/IIG matrix, QEMU, device or registry mutation by probe.
One tiny host Python process <=256 MiB; <=30 second timeout. Save source/tool/
patch hashes, exact invocation/exit, actual samples, controls and controller RSS.
Historical qualification and this prospective admission-only qualification stay
separate. No new SDK/ABI/kernel/link/guest/device claim.


Compatibility is deliberately separate. The original qualified-component.json
still requires its original 1d8ebf6 tool hash. This prospective tool keeps the
strict self-hash check and therefore rejects that old descriptor when used as
the verifier. It does not relabel historical runs under the new helper hash.
To reverify the old qualification after installing this guard, invoke the frozen
original entrypoint:

    PYTHONDONTWRITEBYTECODE=1 python3 /home/egor/dev/pet/s24-ios-exynos/worktrees/vm-008-20261105/tools/build/avf_kernel_headers.py --mode verify --main /home/egor/dev/pet/s24-ios-exynos --qualification /home/egor/dev/pet/s24-ios-exynos/worktrees/vm-008-20261105/fixtures/public/avf-kernel-headers/qualified-component.json --out /home/egor/dev/pet/s24-ios-exynos/artifacts/avf-kernel-headers/NEW_FRESH_VERIFICATION_NAME

That original verifier launches no commands; it remains suitable for its frozen
scope. MAIN may also verify the original entrypoint before applying this guard.
The separate admission-only descriptor/capsule pins the new tool and probe,
parent commit, historical descriptor/tool hashes and this compatibility route;
it does not qualify new headers, objects, IIG products or execution.
