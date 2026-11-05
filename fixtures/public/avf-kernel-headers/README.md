# Public AVF guest header qualification

The implementation is tools/build/avf_kernel_headers.py. The qualification
JSON contains only source/tool hashes, bounded host evidence and local artifact
references; it contains no SDK, firmware, Apple binary, private data or kernel
execution claim. The preprocessing trace helper derives from this project's
fixtures/public/xnu-kernel-mig/preprocess.py and preserves exact source/exit status.

Public source attribution and licenses remain with the pinned Scion/XNU/HFS
composition, PureDarwin TargetConditionals source, AvailabilityVersions and
Nyktis IIG candidate artifacts. See docs/procedures/avf-kernel-headers/README.md
for exact pins, source ports, actual results and limits.
