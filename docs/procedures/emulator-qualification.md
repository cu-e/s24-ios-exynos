# TST-002: exact APK in an isolated Android guest

Physical S24 installation remains unauthorized. Every ADB command must select the unique process-owned emulator serial, and the launcher checks its AVD name before mutations. Never restart the shared server, adopt or terminate another emulator, or copy a private ADB key.

The seven historical API36 failures remain immutable. A smaller 720x1560/280dpi viewport preserves the earlier 1080x2340/420dpi logical aspect/size while reducing software rendering load. Use two vCPUs and 2 GiB guest RAM, a bounded boot deadline and actual semantic control readiness. A successful sys.boot_completed alone did not establish a functioning System UI in prior runs. No coordinate guess can qualify accessibility.

```sh
python3 src/android-probe/emulator_check.py \
  --apk artifacts/android-probe/apk-session5/s24-vulkan-probe.apk \
  --run unique-emulator-run --port 5582
```

Register EMULATOR-008 before the next actual guest run. Record the installed emulator/system-image versions and exact APK/build/input digests. The launcher must verify current compiled inputs against build-report.json before running the unchanged APK. It captures actual screens/hierarchies and tests genuine 65,536-pixel Vulkan readback, saved results and light/dark enlarged text. Host SwiftShader/emulator results never qualify Xclipse or the native S24.

API35 Google APIs revision9 was considered to match Android15. Official repository metadata was initially truncated; exact HTTP ranges reconstructed and parsed the complete document. The selected image archive would be 1,738,815,903 bytes, SHA1 0103e6dab21290c4b9d16550a3ce99476f884eef. Its license text does not match the locally recorded acceptance hash; no new terms were accepted and no image archive was fetched. Continue with the installed API36 image. This is an environment coverage limit, not a change of the phone or approved first iOS version.

TST-002 completion additionally needs real export, restart/storage-error and lifecycle coverage, plus a separate accessibility assessment. A helper's basic runtime pass must not complete the broader task automatically. Controlled emulator-only error injection must be labeled and retain genuine measurement JSON; do not substitute fabricated pixel results. Read-only Impeccable native review uses genuine captures and the existing framework-Views PRODUCT.md/DESIGN.md authority, not a redesign.

## Extended qualification

```sh
python3 src/android-probe/qualification/build.py --run unique-qualifier-build \
  --target-build artifacts/android-probe/apk-session5
python3 src/android-probe/emulator_check.py \
  --apk artifacts/android-probe/apk-session5/s24-vulkan-probe.apk \
  --qualifier-apk artifacts/android-probe/unique-qualifier-build/qualifier.apk \
  --run unique-qualified-guest --port 5582 --adb-server-port 5482
```

Register EMULATOR-010 before the extended APK5 run. EMULATOR-008 retained a Python syntax failure before any guest started; EMULATOR-009 passed genuine pixel/readback/restoration and theme captures. Its emulator binary internally tried unqualified `adb -e` commands, all observed failing with multiple emulators. The launcher now owns a private loopback ADB server, filters USB to an unused task selector, disables mDNS auto-connect and automatic emulator-port scanning, checks its sole transport and verifies the AVD name before any guest mutation. Emulator helpers inherit that same private socket. The shared server is never restarted or terminated.

Primary references: [ADB command options](https://android.googlesource.com/platform/packages/modules/adb/+/7c2fd99d6ec7e0d2d977ba03cecc82375af1baad/client/commandline.cpp), [zero disables emulator scanning](https://android.googlesource.com/platform/packages/modules/adb/+/refs/heads/android15-qpr2-s8-release/client/transport_emulator.cpp), [mDNS auto-connect zero policy](https://android.googlesource.com/platform/system/core/+/634a3dc179da506f2c671c7f50199f5eaa46ea8e/adb/client/transport_mdns.cpp). Runtime ownership and cleanup still require actual evidence; flags alone are not a guarantee.

The separately signed test APK instruments the unchanged target, verifies its installed APK SHA256, sends actual pointer events, captures the actual Android screen/AX hierarchy and checks genuine native fixture JSON. It is never part of the production APK. Cases cover initial/run, real worker overlap with Activity recreation, system document-picker export with byte-equivalent JSON, startWrite and commit storage faults, restart-required UI and live night-mode recreation. Run both themes with font scale1.3. Restart mode explicitly injects an idle RunGate poison through reflection; it does not induce or qualify a GPU-driver hang. Storage faults create nonempty directories at fixed test-owned private paths; they are not a full-disk or production-storage test.

[AtomicFile implementation](https://android.googlesource.com/platform/frameworks/base/+/HEAD/core/java/android/util/AtomicFile.java) logs some finishWrite sync/rename failures instead of throwing. A caught exception alone cannot establish successful persistence. The commit-fault case must expose any silent-loss bug, retain the original failure, then qualify a rebuilt corrected APK separately. No UI assertion may replace a genuine GPU report with manufactured pass bytes.

EMULATOR-013 passed all16 APK6 runtime cases, while independent native review returned **fix** for white status-bar icons on the light surface and stale verification prose. Preserve that separate verdict. APK7 applies system status/navigation appearance at creation/focus and retains the existing layout. Register EMULATOR-014 before its confirmation run; assert the actual attached system-bars appearance against the real theme, recapture the same eight states into a new immutable run, and request a bounded verdict pass. Do not overwrite source-labeled session13 evidence to satisfy a review filename convention. Native screenshots must still be inspected; controller flags alone are not visual proof.

EMULATOR-014 reached three passing light cases with correct bar flags but lost ADB during private-file cleanup; its launcher then exited and retained failure evidence. The cause of disconnect is unproven. Register EMULATOR-015 before the unchanged APK7/qualifier confirmation with improved transport handling. An offline response permits at most30seconds of read-only observation while the exact owned emulator/server processes remain live. Resume only after matching the AVD and hashed guest boot ID. Retry once only for reads or an allowlisted idempotent `rm -f` of fixed test files; never replay install, settings, pointer events or instrumentation/native work. A guest boot change or unrecovered/non-idempotent failure ends the experiment. No shared-server restart or implicit new guest is allowed.

EMULATOR-015 passed the light set but failed a dark lifecycle assertion that read View/report state from the instrumentation thread. Its retained status/capture already shows the actual cancelled report. Register EMULATOR-016 before the same APK7 confirmation with a corrected qualifier: read UI fields through runOnMainSync and wait for actual report display after retirement, rather than racing the enabling of Start. This changes test observation, not target APK bytes or native results. Retain the failed assertion and do not claim it proves application data loss.

EMULATOR-016 passed all16 cases on exact APK7/qualifier9. Both owned processes exited, ports5582/5482 closed and no offline recovery was exercised. The bounded independent confirmation returned **disposition: ship** for the original two findings and introduced regressions; the original fix verdict remains retained. `make check` passed108 tests. See [TST-002 handoff](../../research/notes/TST-002-runtime-qualification.md) and immutable evidence for exact identities and qualification limits.
