# Graphics layer

Home for project-owned shader fixtures, reference outputs, Metal-to-Vulkan adapters and app-local Vulkan experiments. No working iOS GUI layer exists yet.

Start with GPU-004: one small test, a pinned translator, expected pixels and an error tolerance. Separate user-facing APIs from the platform memory/queue/firmware backend. Xclipse, Mali and Adreno are not interchangeable.

The first owned fixture is `fixtures/write_marker.ll`, synthetic AIR-shaped LLVM IR that writes integer 9212400 to Metal buffer 0. It is authored for this project, assembled with the installed NDK LLVM 19.0.1, not compiled by Apple's Metal compiler. The selected translator accepts this bitcode; this does not establish support for every LLVM/AIR producer. A synthetic Vulkan 1.2 minimum profile is used, not the S24 capture.

```sh
python3 src/graphics/build_translator.py --run unique-build
python3 src/graphics/check.py --run unique-check \
  --translator artifacts/metal-build/unique-build/source/target/debug/metal2vulkan
```

Requires the pinned source checkout, Rust 1.98.1, installed NDK 28.2.13676358, a host C++ compiler/Vulkan development files and Lavapipe. The committed Cargo dependency lock freezes the initially resolved registry packages. Source and dependency notices remain with the ignored build copy; no upstream source is relicensed here.

The check independently runs spirv-val, verifies the translated descriptor/push-constant interface, dispatches the real translated compute pipeline through host Vulkan, and compares one exact integer plus 15 untouched guard words. There is no Apple-native reference run, Metal Objective-C device registration, image/render pipeline or Xclipse/XNU execution in this result. Each is a separate task. Heavy builds and network access are explicit and are not part of routine `make check`.
