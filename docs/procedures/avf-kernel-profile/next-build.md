# Next genuine AVF XNU preparation/build

This is a gated future plan, not executed build instructions or a grant for a
heavy build/VM. VM-006 owns source/profile qualification only. A new task and
resource lease must own future preparation, compilation, linking and CPU runs.
Do not resume VM-002/KRN-026 or edit another owner's inputs as a shortcut.

1. Stage the full Scion donor at `a6f4bc38aa244359cd365c976244a88c9d6b3304`
   and XNU `c54f35ca767986246321eb901baf8f5ff7923f6a` into fresh owned storage.
   Bind all source files, licenses and full ordered patch applicability. The
   current 116-file/14-composed-file graph is not a complete prepared kernel.
   The real `xnu/apply.sh` additionally needs HFS `31d5ec238dfab485e78a9a30b8b92d13e8914f03`,
   its pinned core/encoding lists/patch, all `xnu/files`, `drivers/map`, driver
   files/configs, any selected layers and all 34 numbered patches. It refuses
   an existing output tree; never point it at shared references/native outputs.
2. Fix the actual guest profile explicitly: `ARCH_CONFIGS=ARM64`,
   `MACHINE_CONFIGS=BCM2837`, `KERNEL_CONFIGS=DEVELOPMENT`, `BUILD_LTO=0`,
   `DO_CTFMERGE=0`. Keep genuine DEVELOPMENT link/export/alias/symbolset behavior;
   never transplant a native command and delete its exports. Keep original
   native E1S objects/features/export list unmodified. Default open runtime
   configuration is `configs/defconfig`; capture an explicit `.config` and every
   generated `MASTER.hakios`/driver-header choice. Runtime firmware-none switches
   do not exclude compiled drivers. Do not accidentally inherit a device .config.
3. Qualify a guest header/tool route before compiling all objects. The stock
   `xnu-deps/setup.sh` needs iPhoneOS16.5 SDK includes and pre-generated
   MacOSX13.3 DriverKit headers; no qualified supplied paths establish that route.
   Do not run it to acquire an SDK. Instead inspect/replay the already accepted
   public SETUP/MIG/header installation and matched compiler-resource recipes
   against the freshly composed guest tree. Reuse genuine public source inputs
   and board-independent tools only after matching recorded hashes, target and
   include namespaces. Record each genuinely missing header/tool/provider; no
   empty header, fake IDL layout, constant allocator metadata or fabricated ABI.
   KRN-022's 76 unavailable generated entries and KRN-004's partial IIG work
   are explicit limits, not complete guest SDK inputs. Do not blindly copy their
   native generated products or claim private Apple ABI from an open generator.
4. Bind the accepted custom compiler/linker candidates from `inputs.json`.
   The donor wrapper hardcodes `/usr/bin/clang`; any future owned wrapper must
   explicitly select the qualified frontend and preserve coherent guest flags.
   Assert genuine allocator builtins (`XNU_NO_TYPE_BUILTINS=0`). Match the compile
   resource headers to that compiler; never use KRN-025's link-only resource root
   as a compiler-header root. Regenerate guest doconf/setup/MIG/assembly/IIG and
   source-installed kernel/kext headers before compiling against them.
5. Rebuild genuine firehose and pthread against guest headers/configuration.
   Pinned source releases are libdispatch `a641558f447659d90ad002ef0ee6f0212273fbfc`,
   libpthread `a6c70ca0e544347a0377babf748f831577ec24f9`, AvailabilityVersions
   `5d9baee345b3bc72b26c71adc65f94f2d5e9ced2`. Preserve qualified native install
   context rather than raw-private-header fallback. Existing E1S archives are
   source/procedure references only. Recheck real callback/type/layout/import
   contracts and native aliases for the new guest; no historical archive or
   empty provider may fill a gap. cc_kext's qualified board-independent archive
   is a separate link-only candidate requiring exact compiler/target binding.
6. Under a separately granted build lease, generate all actual DEVELOPMENT/
   BCM2837 recipes and coherent objects into owned outputs, starting with a tiny
   representative compile for each disputed dependency. Capture full argv,
   dependencies and native MachO object formats; do not rename/reuse E1S objects.
   A stock-route command skeleton, valid only after its header/tool route is
   qualified in the isolated donor root, is:

   ```sh
   # FUTURE, NOT EXECUTED: GUEST_XNU names a fresh composed guest source tree.
   XNU_SRC="$GUEST_XNU" MACHINE=BCM2837 ./xnu-build.sh -j1 exporthdrs
   XNU_SRC="$GUEST_XNU" MACHINE=BCM2837 ./tools/make-kernel.sh -j1
   ```

   The real wrapper still sets SDKROOT=iphoneos and sources xnu-env.sh. Any
   public-source replacement must supply a witnessed coherent include/tool/
   library namespace; setting an arbitrary SDKROOT does not create those inputs.
   Do not execute this skeleton against the shared donor or before resource and
   input gates are resolved. Whole-tree dry-run/compile/link closure is unmeasured.
7. Keep genuine DEVELOPMENT aliases/symbolset/layout inputs and every real
   required library at the link. Its absence of RELEASE-only forced exports is
   a supported source selector, not a promise all 37 native names or all guest
   references disappear. Measure the actual guest unresolved/duplicate names,
   archive member selection and image existence; inspect a genuinely produced
   arm64 kernel's segments/entry/layout and source provenance before use. The
   MakeInc image base is `0xfffffff007004000`, compatible in source with the
   AVF shim's `0xfffffff004000000` window and +48MiB minimum text offset.
8. A separate VM execution task must consume that actual qualified image with
   the already pinned unchanged AVF shim and qualified QEMU. The kernel must
   include MOCKFS and a raw owned MachO executable ramdisk, not a Linux/rootfs
   substitute. Source-supported command arguments include `rd=md0 cpus=1 -v
   avf_exit=1 security=bringup`; `avf_exit=0` disables the intended no-loader
   PSCI stop and `security=full` may reject an unsigned owned fixture. Preserve
   the existing VM-002 explicit hashes, owned-process deadlines and lease gates.
   Actual Darwin console, conditional owned PID1 marker and natural guest stop
   must be measured before VM-002 acceptance. VM-005's SYNTHETIC PASS proves
   only its explicitly synthetic handoff, not this future XNU execution.

A source graph pass alone neither qualifies a complete SDK/IIG implementation,
full kernel/corecrypto/iOS userspace/private ABI nor proves native E1S behavior
or Android recovery. Those boundaries remain explicit through future work.
