# Native Android design

This utility extends framework Android Material controls. The system theme and existing Android Views implementation are the visual authority. There is no custom brand, approved comp, asset set, web UI, Material 3 library or iOS interface. No custom token sidecar is needed for unchanged platform styling.

## Theme and type

Background, foreground, button colors, disabled states, shapes, elevation and feedback come from `Theme.Material.Light.NoActionBar` or `Theme.Material.NoActionBar`. `onCreate` selects the current system night mode before creating views. Night-mode changes recreate the Activity; orientation/screen-size changes are handled in place. The manifest theme is a fallback.

Default platform font; title 24 sp, instructions/fixture 16 sp, status 18 sp, result/caution 14 sp. Button typography is native with all-caps disabled. Text follows system font scaling.

## Layout and controls

A single vertical column scrolls. Content padding is 24 dp horizontal, 16 dp top and 24 dp bottom. Text blocks have 8 dp vertical padding. Buttons fill available width, wrap their contents, request at least 48 dp height and have an 8 dp top margin. System-bar/cutout insets are applied to the scroll container (legacy system-window insets on API 29). No custom animation, cards, breakpoints or text-entry/IME behavior exists.

Start test, Stop and Save report appear in that order. Start is disabled while a worker owns the process-wide gate or a restart is required. Stop requests cooperative cancellation; it cannot promise immediate GPU termination. Save opens Android's JSON document picker. Status is a polite accessibility live region; results are actual selectable JSON.

Opening the screen never starts a measurement. A recreated Activity waits for an existing worker and restores the actual available report. Private-storage failure retains the measured JSON in process memory and asks the user to export it before ending the process. Restart-required messages explicitly identify Android Force stop followed by reopening.

## Verification limits

Historical captures/source review remain under emulator-session5 and fixtures/public/host-lab/ui-review.json. The current APK7 is captured in artifacts/android-probe/emulator-session16/: qualification-no/yes-initial/run/storage/restart.png and the other named case outputs. These are genuine Android API36/SwiftShader phone-guest captures at720x1560/280dpi and font scale1.3. EMULATOR-016 passed all16 runtime cases, including export byte equality, both storage faults, real busy-worker recreation and live theme recreation. Live AX nodes and48dp control heights were measured. APK7 also sets system status/navigation icon appearance from the actual theme; genuine screenshots are retained for independent confirmation. Independent finish review is recorded separately in fixtures/public/android-ui/; a runtime assertion is not a visual-quality verdict.

Spoken TalkBack, real Android15/S24 performance, ARM64 JNI execution and GPU/kernel recovery remain unqualified. Restart-state coverage uses explicit idle-gate injection; it does not simulate a successful device recovery. The earlier screenshot and newly captured guest screens never establish physical S24 or native iOS support.
