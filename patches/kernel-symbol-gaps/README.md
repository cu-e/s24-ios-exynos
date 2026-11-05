# Selected kernel source symbol gaps

Base Apple XNU: c54f35ca767986246321eb901baf8f5ff7923f6a,with the existing
prepared E1S delta witnessed by KLINK-012. Apply only to fresh copies of the
four exact files listed in fixtures/public/xnu-kernel-symbol-gaps/source-inputs.json.
The source remains under its upstream Apple Public Source License2.0 notices.
Do not override upstream licensing or redistribute SDK/binary inputs here.

The patch gives the already exported legacy clean_mmu_dcache name a real
entry label at the existing CleanPoC_Dcache code,no new instruction or stub.
It scopes SleepToken's export to its genuine WITH_CLASSIC_S2R definition.
It uses the build system's XNU_TARGET_OS_OSX selector consistently for all
five stage2 iBoot declaration,producer and log-consumer branches. Public
TargetConditionals' defined-zero value is not a reliable defined() platform
selector. The original macOS-only producer/consumer policy is preserved.

Actual target code/storage and enabled/disabled source controls are required.
Neither symbol closure nor unchanged code bytes proves ARM cache,firmware,
suspend/resume or native runtime correctness on Exynos. No original tree is edited.
