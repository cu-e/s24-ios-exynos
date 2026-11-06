#!/usr/bin/env python3
"""Independent existing donor decoder oracle for actual C-produced records."""
import importlib.util
import json
import sys
from pathlib import Path

reader, dump, output = map(Path, sys.argv[1:])
spec = importlib.util.spec_from_file_location('pinned_e1s_read_log', reader)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
body = dump.read_bytes()
records = module.extract(body)
assert len(records) == 2, 'actual C output must contain two loader records'
assert records[0][0] == 7 and records[0][1] == 'E1SXNU01'
assert records[0][2] == bytes((i * 17 + 1) & 255 for i in range(0xff00))
record_size = (len(body) - 10) // 2
assert record_size == 65300 and len(body) == 2 * record_size + 10
assert records[1][0] == 7 + record_size + 3
assert records[1][1] == 'E1SXNU01'
assert records[1][2] == b'decoder=0xffffffffffffffff '
assert module.extract_boot_mark(body) is None, 'no initialized kernel marker claim'
# Existing decoder searches magic; it cannot authenticate an extracted candidate.
decoy = b'E1SXNU01' + (5).to_bytes(4, 'little') + bytes(4) + b'DECOY\0'
truncated = b'E1SXNU01' + bytes(3)
candidates = module.extract(body + decoy + truncated)
assert len(candidates) == 3
assert candidates[:2] == records
assert candidates[2] == (len(body), 'E1SXNU01', b'DECOY')
result = {'outcome': 'pass', 'kind': 'host-test', 'actual_decoder_records': len(records),
          'first_offset': records[0][0], 'second_offset': records[1][0],
          'text_lengths': [len(r[2]) for r in records], 'kernel_marker': None, 'with_explicit_decoy_candidates': len(candidates),
          'decoy_offset': len(body), 'truncated_header_ignored': True,
          'magic_extraction_is_not_authentication': True}
output.write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
