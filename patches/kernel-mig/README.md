# Selected MIG build adaptation and attribution

No upstream MIG/XNU code patch is introduced by KRN-010. The project-owned
`tools/build/xnu_kernel_mig.py` queries genuine Make rules and executes them in
fresh, mode-separated output trees. `fixtures/public/xnu-kernel-mig/preprocess.py`
adds dependency/output tracing and preserves the real preprocessor exit status.
Neither adapter supplies a missing kernel type or modifies generated declarations.

MIG comes from `markmentovai/bootstrap_cmds` at
`f337e600741638896fb6056ce87c6479f74b89a3`, built in HOSTGEN-002. Its already
qualified preprocessor failure-propagation patch remains in
`patches/build-tools/0001-mig-propagate-preprocessor-failure.patch`.
Preserve all original Apple/CMU notices, repository APSL2.0 and the mig.sh
APSL1.0 notice; these licenses are distinct.

XNU source and Make rules come from Apple XNU8796.121.2 at
`c54f35ca767986246321eb901baf8f5ff7923f6a`, with the recorded E1S patch set.
Preserve APSL2.0 and every per-file notice. Generated source/header bytes remain
in ignored local artifacts. Public manifests contain only paths, hashes,
measurements and attribution. This component supplies no SDK/Apple binary grant.
