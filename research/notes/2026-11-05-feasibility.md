# Feasibility review: iOS on SM-S921B / Exynos 2400

Review date: 2026-11-05, Asia/Yekaterinburg. Evidence category: source-review. No phone operation or hardware port was performed during this review.

## Established boundaries

The exact [S24 port](https://github.com/RNDMBG/iOS-On-S24/tree/c8860decc62c6d6180e609036d027a2997972420) is written but untested on hardware. Its [userland test](https://github.com/RNDMBG/iOS-On-S24/blob/c8860decc62c6d6180e609036d027a2997972420/docs/e1s-userland.md) runs an owned static PID 1, not Apple launchd. Its previews do not execute XNU. The final export check fails after linking; CI applies patches and runs host checks, not a kernel build. The port's hardware map uses S921BXXS8BYG2 BSP data, whereas our Android baseline is S921BXXS9BYH3.

[RADV Xclipse](https://github.com/JimVulkan/radv-xclipse) reports Android testing on SM-S921B/SM-S926B. [metal2vulkan](https://github.com/steelbrain/metal2vulkan) supplies AIR translation and a Vulkan-backed command model. Neither supplies the complete native S24 XNU graphics stack. [UniXNU GPU adaptation](https://unixnu.com/porting/gpu) separates kernel memory/submit, firmware/power, the Metal frontend and display integration. This is the design reference, not Xclipse hardware evidence.

[S20+](https://github.com/stormtroopxyz/y2sios) reports Mali/Metal, Wi-Fi, UFS and power support; [S9](https://github.com/Scion-Project/hakios-starlte) reports additional audio and front-camera work. Their controllers, GPU, interrupt generation and board wiring differ from S24. [S7](https://github.com/wardevsa/ios-a5xelte/tree/herolte) uses EAGL/Panfrost rather than Metal and has major peripheral gaps. [S10+](https://github.com/orhunnx/beyond2lte-ios) documents actual boot/UI work and unresolved rendering/application limitations. No donor's device result is a measurement of our S24.

## New findings from existing local captures

These are interpretations of original DEV-001 captures, not a new collection:

- kernel-modules.txt: kiwi_v2/cnss2/wlan_firmware_service, sgpu, cpif/shm_ipc, ABOX and CS35L43. This contradicts an online secondary table labeling S24 Wi-Fi Broadcom. Exact endpoint PCI ID is still missing.
- kernel.config: SEC_MODEM_S5000AP and LINK_DEVICE_SHMEM are modules; LINK_DEVICE_PCIE is off. A shared-memory CPIF path is a better starting point than a Qualcomm or external PCIe modem assumption.
- features.txt declares eUICC/MEP. This is framework feature inventory, not a tested provisioning interface.
- KEXEC/KEXEC_FILE are disabled. KVM is configured, but usable access and a guest were not tested. Device tree property reads and bus metadata were unavailable.

The [E1S KIWI V2 overlay](https://github.com/dx4m/android-kernel-samsung-e1s/blob/417484173abc2c4fa93e738ea82ad9f2e84911b1/arch/arm64/boot/dts/samsung/e1s/s5e9945-e1s_wifi_03.dtsi) and [CPIF sources](https://github.com/dx4m/android-kernel-samsung-e1s/tree/417484173abc2c4fa93e738ea82ad9f2e84911b1/drivers/soc/samsung/cpif) are primary source leads, not proven matches to the exact firmware.

## Cellular and eSIM

[QcomBaseband](https://github.com/UniXNU/QcomBaseband) publishes an iOS-side bridge, Qualcomm transport and Coachz packet path. The author reports LTE registration and IPv4 browsing on iOS 17; IPv6 and long sessions remain pending. eSIM interfaces exist, but provisioning remains unverified. This is a stronger lead than a screenshot, and still not a Samsung driver. [HakiOS cellular notes](https://github.com/oosexgang/hakios-xnu-kernel/blob/87bf4851bcc9cbb24fd79997820aa3661abe4ea5/docs/cellular.md) document separate limitations on its Qualcomm target.

[lpac](https://github.com/estkme-group/lpac) is an LPA candidate after a real eUICC transport exists. [Android eSIM architecture](https://source.android.com/docs/core/connect/esim-overview) distinguishes LPA, logical-channel/APDU handling and privileged system APIs. Rootfs boot, a SIM icon and an eSIM settings page do not close these tasks.

## Alternatives and unavailable information

[Scion AVF](https://github.com/Scion-Project/hackios-xnu-kernel/blob/main/avf/README.md) reports XNU/PID 1 in a Pixel AVF guest. S24 availability and full iOS operation are not established. [Un1box](https://github.com/KlugKlugTG/Un1box) targets older emulated iOS; touchHLE targets early apps. [libhybris](https://github.com/libhybris/libhybris) assumes Linux and does not replace native XNU kernel services. DSU handles Android GSIs.

Missing inputs: exact DTB/DTBO and board revision, matching stock images and verified restoration, accessible VM interface, Wi-Fi endpoint identity and board firmware, GPU firmware/security startup details, CP firmware/control commands, eUICC transport, carrier and IMS behavior. Each needs a dated source or actual scoped measurement. No claim is made that proprietary documentation is obtainable.

## Reddit and coverage limits

During the current review, two pages of 100 recent r/hackios titles were inspected; selected S7, S21, Pixel Fold, Xiaomi 15, feature-comparison and cellular threads were read. These overlap the older local 324-post archive and must not be added as 524 unique reviewed posts. The latest cellular [claim](https://www.reddit.com/r/hackios/comments/1xnpxwv/) has removed content in the accessible archive and no reproducible implementation was obtained. A Pixel Fold author said code was not yet published in the reviewed discussion.

Reddit was accessed read-only through its MCP archive/RSS fallback. Metadata lookup failed, some searches timed out, recent comments may be missing, and source visibility is incomplete. GitHub API later rate-limited; raw source pages and pinned Git retrieval are separate access paths. Private chats, deleted content, hardware videos and all repositories were not exhaustively verified. Do not turn a search failure into proof of absence.

## Decisions

Use iOS 16.5/E1S first, preserve Android, and separate the Android lab from native acceptance. Hardware is the target; Apple services/security are separate unresolved goals. Carrier is to be selected before real cellular testing. Full implementation order and gates: [implementation contract](../../docs/implementation.md). State is tracked through capability evidence and the task board.
