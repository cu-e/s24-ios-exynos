# MIG failure propagation

Base: markmentovai/bootstrap_cmds f337e600741638896fb6056ce87c6479f74b89a3, migcom.tproj/mig.sh. Preserve its Apple/CMU notices and repository APPLE_LICENSE; no project-wide license overrides those components.

The upstream shell front end pipes preprocessing into migcom and checks the pipeline status. Without pipefail, a failing preprocessor can be hidden by successful generation from partial valid input. The owned one-line patch enables Bash pipeline failure propagation. It changes no MIG grammar, generated RPC layout or SDK.

Apply/check only in the pinned artifacts build copy. Retain the original source checkout. Qualification must pass a genuine simple interface and reject valid interface text followed by a preprocessor error; this does not qualify generated RPC execution or XNU/SDK ABI.

## Host libdispatch atomic header linkage

Base: swiftlang/swift-corelibs-libdispatch137b6cf3060eae87d9b367c263619c2eca5d3aac, src/block.cpp. Preserve its Apple Apache2.0 notice and repository LICENSE including the Swift runtime exception.

MACHOTOOLS-001 actually fails with the installed NDK19/GCC15 headers: internal.h opens extern-C before its later stdatomic include, whose C++ implementation declares templates. The owned one-line patch includes the same header first in C++ scope. Header guards then preserve the original declarations without placing C++ templates under C linkage. It adds no atomic operation or stub; the source explicitly keeps atomic operations out of block.cpp. C source atomics remain untouched.

This source-based correction must pass the real runtime build and actual once/parallel-block fixtures before its host prefix is qualified. It is unrelated to selected E1S kernel firehose sources, native scheduling or iOS runtime acceptance. Apply only in the artifacts copy and retain the original failed build.

MACHOTOOLS-002 demonstrates that the header-order correction alone is insufficient: hosted C++ std::atomic functions still reject the runtime's C11 _Atomic objects. Keep that failed result; do not claim this one-line change qualifies the runtime.

## Host Clang C11 atomic implementation

Base header: xnu-tapi fa9443738c1a18accef4244732ec6d6ee97a8133, src/clang/lib/Headers/stdatomic.h, Apache2.0 with LLVM exception. The exact vendored LLVM source/header is an open-source compiler component, not an SDK or authored substitute for system atomics.

0003 adds a private build-profile condition that selects this header's existing Clang __c11_atomic implementation instead of forwarding to hosted C++ std::atomic. The builder copies/patches it only in the current artifacts run and adds that include/define only to the host libdispatch and its qualification fixtures. It does not alter global compiler headers, the kernel, TAPI compilation or cctools source. The original header/patch/output hashes and license are retained. No atomic operation is replaced with a stub.

Before the runtime build, an actual mixed C/C++ program must verify long/bool/pointer-width atomic struct size/alignment and32 C++ updates observed by C. The actual dispatch once/32 parallel-callback fixture must then pass. These checks qualify the bounded host-build compatibility profile, not native scheduling or every runtime concurrency behavior.
