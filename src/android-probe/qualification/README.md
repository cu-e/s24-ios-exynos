# Emulator-only target instrumentation

This separately signed APK tests the genuine probe APK without adding test hooks to its production code. It requires a task-owned ranchu/goldfish guest, verifies the installed target APK SHA256, and records source identity from actual JNI measurement results. It is never installed on the physical S24.

```sh
python3 src/android-probe/build.py --run unique-target-build
python3 src/android-probe/qualification/build.py --run unique-qualifier-build \
  --target-build artifacts/android-probe/unique-target-build
python3 src/android-probe/emulator_check.py \
  --apk artifacts/android-probe/unique-target-build/s24-vulkan-probe.apk \
  --qualifier-apk artifacts/android-probe/unique-qualifier-build/qualifier.apk \
  --run unique-guest-run --port 5582 --adb-server-port 5482
```

Register a bounded experiment under TST-002 first. The builder uses installed platform35/build-tools35 and the target build's existing private development key; the key and APKs remain ignored. It records commands, source copies and hashes. Source or target changes require rebuilding the qualifier; there is no automatic download, signing-key publication or device selection in the builder.

| Case | Actual interaction / assertion | Evidence limit |
|---|---|---|
| Initial | Framework Activity and real view/AX labels, enabled states and measured target sizes | No screen reader speech/gesture qualification |
| Run | Pointer events on Start; genuine JNI65536-pixel result and target/source digest | SwiftShader guest, not Xclipse or Metal |
| Storage | Nonempty private `.new` directory forces startWrite failure; preserve genuine result and recreate Activity | Controlled test-owned filesystem fault, not full-disk qualification |
| Commit | Nonempty private base directory blocks rename; app must detect unavailable committed bytes | Readback verifies bytes, not crash/power-loss durability |
| Lifecycle | Invoke the real Start listener on the main thread, observe actual gate busy, request real Activity recreation, wait for retirement, then run a fresh native worker | Trigger is explicitly programmatic, not an external pointer or GPU hang injection |
| Restart | Reflectively poison the idle RunGate and recreate Activity; check truthful guidance and disabled Start | Controlled UI-state injection, no failed GPU driver or recovery guarantee |
| Export | Pointer event opens actual system document picker; semantic Save, then exported JSON must equal the genuine measurement | Fixed test-owned Downloads filename; no personal provider/account |
| Theme | Change actual night mode and observe framework Activity recreation plus retained genuine result | Current guest/profile only; no physical display performance claim |

Both themes use font scale1.3. Screens come from Android UiAutomation/screencap, with real view and accessibility data. No generated replica, HTML/CSS rendering or fabricated pixel result is used. The private loopback ADB server excludes USB devices with an unused selector, disables automatic emulator/mDNS discovery and admits only the newly owned AVD. The launcher verifies identity before guest mutations and terminates only its own process groups.

Earlier failures remain distinct: EMULATOR-008 failed Python parsing before launch;009 passed basic genuine APK5 readback/restoration/theme captures;010 failed private listener startup before any emulator;011 failed to observe worker overlap after a delayed pointer;012 reached real result/AX assertions but found no usable document-picker Save control after its fixed1.5-second delay. No export was qualified; the later checker waits for semantic readiness. None completes the full UI/runtime task. The new storage readback check is built in APK6; completion requires the actual expanded run and independent native review.

EMULATOR-013 passed all16 cases on exact APK6 in both themes with enlarged text. Actual worker overlap was observed in both lifecycle cases, system-picker exports equaled the genuine JSON, both storage-failure paths retained measured data across Activity recreation, and live theme recreation was observed. Owned emulator/private ADB processes exited and their ports closed. See the [runtime handoff](../../../research/notes/TST-002-runtime-qualification.md) for review and remaining limits.

EMULATOR-016 confirms all16 cases on exact APK7 with qualifier9 (main-thread View reads and actual report-display readiness). Theme-correct system-bar appearance is asserted and genuine screenshots are retained for the bounded independent verdict. Earlier EMULATOR-014 transport failure and015 observation race remain immutable; neither was relabeled a pass. No offline recovery was exercised in016.
