# Kernel firehose header export attribution

Pinned Apple libdispatch1415.100.11 revision
`a641558f447659d90ad002ef0ee6f0212273fbfc` supplies the genuine
os/firehose_buffer_private.h and kernel export flags. No authored declaration
replacement or source patch is needed. The runner invokes the qualified host
unifdef on a fresh copied/exported header; original prefixes stay unchanged.

Preserve the Apache2.0 LICENSE and per-file Apple Apache notices. Generated
headers, objects and archives remain in ignored local artifacts. A successful
host compilation does not qualify an Apple private ABI or native device.
