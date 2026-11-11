"""Host tests for tools/ios/lzfse_py.py (IOS-002).

Evidence class: host-test. The vectors in tests/fixtures/lzfse_vectors.json are synthetic inputs (a linear
congruential generator, see tools/ios/lzfse_vectors.py) encoded by the pinned reference encoder
(lzfse/lzfse e634ca58, references/lzfse). No Apple data is used. The decoder was also compared byte for byte with the
reference decoder on a real kernelcache; that comparison is not repeatable from the repository and is not asserted here.
"""
import hashlib
import importlib.util
import json
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("lzfse_py", ROOT / "tools/ios/lzfse_py.py")
lz = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lz)
VECTORS = json.loads((ROOT / "tests/fixtures/lzfse_vectors.json").read_text())["vectors"]


def encoded(name):
    return bytes.fromhex(VECTORS[name]["encoded_hex"])


def raw_stream(payload):
    return b"bvx-" + struct.pack("<I", len(payload)) + payload + b"bvx$"


class ReferenceVectors(unittest.TestCase):
    def test_every_vector_decodes_to_the_recorded_hash_and_size(self):
        for name, vec in VECTORS.items():
            with self.subTest(vector=name):
                out = lz.decode(encoded(name))
                self.assertEqual(len(out), vec["raw_bytes"])
                self.assertEqual(hashlib.sha256(out).hexdigest(), vec["raw_sha256"])

    def test_block_kinds_match_what_the_encoder_wrote(self):
        for name, vec in VECTORS.items():
            with self.subTest(vector=name):
                kinds = [kind for kind, _ in lz.iter_blocks(encoded(name))]
                self.assertEqual(kinds, vec["block_kinds"])

    def test_vectors_cover_the_block_types_the_decoder_implements(self):
        seen = {k for vec in VECTORS.values() for k in vec["block_kinds"]}
        self.assertTrue({"bvx2", "bvxn", "bvx$"} <= seen, seen)
        self.assertTrue(any(vec["block_kinds"].count("bvx2") > 1 for vec in VECTORS.values()),
                        "no vector spans two bvx2 blocks")

    def test_iter_blocks_prefix_is_a_prefix_of_the_full_output(self):
        name = "lzfse-multi-block"
        full = lz.decode(encoded(name))
        first = next(iter(lz.iter_blocks(encoded(name))))
        self.assertGreater(len(first[1]), 0)
        self.assertLess(len(first[1]), len(full))
        self.assertEqual(bytes(first[1]), full[:len(first[1])])


class HandBuiltStreams(unittest.TestCase):
    def test_uncompressed_block(self):
        self.assertEqual(lz.decode(raw_stream(b"hello")), b"hello")
        self.assertEqual(lz.decode(raw_stream(b"")), b"")

    def test_two_uncompressed_blocks_concatenate(self):
        data = b"bvx-" + struct.pack("<I", 2) + b"ab" + b"bvx-" + struct.pack("<I", 3) + b"cde" + b"bvx$"
        self.assertEqual(lz.decode(data), b"abcde")

    def test_bvx1_is_refused_by_name(self):
        with self.assertRaisesRegex(lz.LzfseError, "bvx1"):
            lz.decode(b"bvx1" + b"\0" * 64 + b"bvx$")

    def test_unknown_magic_is_refused(self):
        with self.assertRaisesRegex(lz.LzfseError, "unknown block magic"):
            lz.decode(b"abcd" + b"\0" * 8)

    def test_stream_without_end_marker_is_refused(self):
        with self.assertRaises(lz.LzfseError):
            lz.decode(raw_stream(b"x")[:-4])
        with self.assertRaises(lz.LzfseError):
            lz.decode(b"")

    def test_raw_block_longer_than_the_data_is_refused(self):
        with self.assertRaises(lz.LzfseError):
            lz.decode(b"bvx-" + struct.pack("<I", 100) + b"short" + b"bvx$")


class MalformedInput(unittest.TestCase):
    """The decoder reads untrusted archives: every damaged stream must end in LzfseError (or decode to something),
    never in IndexError, struct.error, an unbounded loop or an allocation of the size a header claims."""

    def test_every_truncation_of_small_vectors_is_an_lzfse_error(self):
        for name in ("lzvn-text", "lzvn-runs", "raw-noise"):
            data = encoded(name)
            step = max(1, len(data) // 150)
            for cut in list(range(0, min(len(data), 80))) + list(range(80, len(data), step)):
                with self.subTest(vector=name, cut=cut):
                    with self.assertRaises(lz.LzfseError):
                        lz.decode(data[:cut])

    def test_single_byte_corruption_never_escapes_as_another_exception(self):
        state = 12345
        for name in ("lzvn-text", "lzvn-runs", "lzfse-text"):
            data = encoded(name)
            for i in range(120):
                state = (state * 1103515245 + 12345) & 0x7FFFFFFF
                pos = state % len(data) if i % 3 else i % min(len(data), 400)
                mutated = bytearray(data)
                mutated[pos] ^= 1 << (state >> 8) % 8
                with self.subTest(vector=name, pos=pos):
                    try:
                        out = lz.decode(bytes(mutated))
                    except lz.LzfseError:
                        continue
                    self.assertLess(len(out), 64 * 1024 * 1024)

    def test_corrupted_frequency_table_is_refused(self):
        data = bytearray(encoded("lzfse-text"))
        self.assertEqual(data[:4], b"bvx2")
        data[32:96] = b"\xff" * 64
        with self.assertRaises(lz.LzfseError):
            lz.decode(bytes(data))

    def test_block_counts_beyond_the_per_block_limit_are_refused(self):
        data = bytearray(encoded("lzfse-text"))
        v0 = struct.unpack_from("<Q", data, 8)[0]
        v0 = (v0 & ~((1 << 20) - 1)) | ((1 << 20) - 4)  # n_literals = 2^20 - 4, far above 40000
        struct.pack_into("<Q", data, 8, v0)
        with self.assertRaises(lz.LzfseError):
            lz.decode(bytes(data))


if __name__ == "__main__":
    unittest.main()
