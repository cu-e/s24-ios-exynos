# 0002 — Owner autonomy grant of 2026-11-10

Status: in force. Recorded by `claude-authority-record-20261110` at the owner's request so the same questions are not asked again.

## Source

The owner gave two messages in the session of 2026-11-10. The first set the goal and listed allowed actions. The second is described by the owner as the final instruction on project autonomy and supersedes the first where they differ. The originals are in Russian. The quotes below are the owner's exact boundary sentences; the English text is a translation and adds nothing.

Goal (first message): "Продолжай проект s24-ios-exynos автономно до работающей системы на моём S24: загрузка ядра, изображение, ввод, GPU и затем измерение производительности. Сохранение моих данных — обязательное условие."

Final instruction, sole mandatory boundary: "Единственная обязательная граница: сохранить существующий Android, приложения, настройки, аккаунты и пользовательские данные телефона. Резервная копия сама по себе не разрешает нарушить это условие."

Final instruction, explicit prohibitions: "Не разрешаю стирание данных, factory reset, разблокировку загрузчика со сбросом, прошивку или подмену существующих разделов Android, вмешательство в EFS, ключи и шифрование. Не считай наличие root доказательством безопасности произвольного действия."

## Granted without further questions

1. Host: any needed development, fetching sources and dependencies, builds, tests, reviews, local commits, merging verified branches into `main`, and repairing project infrastructure.
2. Subagents, self-directed task assignment, and taking over unfinished tasks of a stopped Codex after checking its state and recording the ownership transfer. Others' changes and results are preserved. Live sessions are not interrupted.
3. On the connected S24: ADB, diagnostics, reading needed system data, root (su) for diagnostics, and copying system partitions to the host. Personal data and secrets do not go into reports.
4. The `android-app` scope: build, install, run, update and remove the project's own test APKs, including GPU/Vulkan tests. User apps and data are kept. Tests are time-bounded, handle errors and stop.
5. Bounded GPU and KVM experiments, including `/dev/kvm` capability ioctls (`KVM_GET_API_VERSION`, `KVM_CHECK_EXTENSION`, `KVM_GET_VCPU_MMAP_SIZE`) and creating a test virtual machine (`KVM_CREATE_VM` and what a bounded guest needs), while the boundary above holds.
6. Changing the project permission registry to reflect exactly this instruction.

## Not granted

- Erasing data, factory reset, bootloader unlock that resets the device.
- Flashing or replacing any existing Android partition (BOOT, init_boot, vendor_boot, dtbo, vbmeta, recovery, super, userdata and the rest), GPT changes.
- Anything touching EFS, keys or encryption.
- The owner's first message also excluded changing the boot chain and rebooting the phone. The final message neither grants nor forbids an intentional reboot, so an intentional reboot is treated as not granted. A kernel crash caused by an approved KVM or GPU experiment can still reboot the phone; experiments must be designed to keep that risk low and must record it.
- Root access is not evidence that an action is safe.

## Consequences for the registry

- `project.permissions.android-app` becomes `true`.
- `project.permissions.native` stays `false`. Native XNU on the S24 needs a written BOOT-class partition or a changed boot chain, both excluded. Native tasks need a new owner decision with a tested recovery plan.
- The practical route to running XNU on the phone is a guest under Android KVM, shown and driven through the project's own APK. A guest that uses the Android Vulkan driver is Android-hosted acceleration and must be reported as such, not as a native XNU GPU driver.

## Evidence rules that still apply

Android Vulkan, software models and successful compilation are not GPU under XNU. QEMU virt is not an Exynos model. Timelines and frame-rate promises are replaced by measurements.
