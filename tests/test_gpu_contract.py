"""Negative lifecycle scenarios for the synthetic SGPU oracle, no device access."""
import importlib.util
from pathlib import Path
import sys
import unittest

PATH = Path(__file__).resolve().parents[1] / "src/graphics/contracts/ownership.py"
SPEC = importlib.util.spec_from_file_location("gpu_ownership", PATH)
gpu = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gpu
SPEC.loader.exec_module(gpu)


class GpuOwnershipTests(unittest.TestCase):
    def device(self, page=4096, budget=65536):
        return gpu.Device(cpu_page=page, budget=budget, va_start=0x100000, va_bytes=0x100000)

    def mapped(self, device, client, *, address=0x100000, size=4096):
        handle = device.allocate(client, size)
        device.map_gpu(client, handle, address=address, offset=0, size=size)
        return handle

    def test_cpu_page_padding_charged_globally_without_exposing_extra_gpu_pages(self):
        for page in (4096, 16384):
            with self.subTest(page=page):
                d = self.device(page, 2 * page)
                a, b = d.client(), d.client()
                h = self.mapped(d, a)
                other = self.mapped(d, b)  # per-client VA spaces can reuse addresses
                self.assertEqual(d.used, 2 * page)
                with self.assertRaises(gpu.ContractError):
                    d.allocate(b, 1)
                with self.assertRaises(gpu.ContractError):
                    d.map_gpu(a, h, address=0x104000, offset=4096, size=4096)
                d.unmap_gpu(a, h, 0x100000)
                d.free(a, h)
                replacement = d.allocate(b, 1)
                self.assertNotEqual(replacement, h)
                self.assertEqual(d.used, 2 * page)
                with self.assertRaises(gpu.ContractError):
                    d.free(a, h)
                with self.assertRaises(gpu.ContractError):
                    d.free(a, other)

    def test_timeout_stop_and_one_of_two_fences_do_not_release_backing(self):
        d = self.device()
        a = d.client()
        h = self.mapped(d, a)
        f1, f2 = d.submit(a, {h: "read"}), d.submit(a, {h: "read"})
        d.stop(a)
        self.assertEqual(d.wait(a, f1, 100_000_000), "timeout")
        for operation in (lambda: d.free(a, h), lambda: d.unmap_gpu(a, h, 0x100000),
                          lambda: d.submit(a, {h: "read"}), lambda: d.allocate(a, 4096)):
            with self.assertRaises(gpu.ContractError):
                operation()
        d.backend_complete(f2)
        with self.assertRaises(gpu.ContractError):
            d.unmap_gpu(a, h, 0x100000)
        self.assertEqual(d.used, 4096)
        d.backend_complete(f1)
        self.assertEqual(d.wait(a, f1, 0), "complete")
        d.unmap_gpu(a, h, 0x100000)
        d.free(a, h)
        self.assertEqual(d.used, 0)

    def test_fault_requires_trusted_quiescence_and_device_stays_quarantined(self):
        d = self.device()
        a = d.client()
        h = self.mapped(d, a)
        fence = d.submit(a, {h: "write"})
        d.backend_fault()
        self.assertEqual(d.wait(a, fence, 1), "timeout")
        with self.assertRaises(gpu.ContractError):
            d.unmap_gpu(a, h, 0x100000)
        d.backend_quiesced()
        self.assertEqual(d.wait(a, fence, 0), "error")
        for operation in (lambda: d.client(), lambda: d.submit(a, {h: "read"})):
            with self.assertRaises(gpu.ContractError):
                operation()
        d.unmap_gpu(a, h, 0x100000)
        d.free(a, h)
        self.assertEqual(d.used, 0)

    def test_cache_and_cpu_access_are_not_implied_by_completion(self):
        d = self.device()
        a = d.client()
        h = self.mapped(d, a)
        d.map_cpu(a, h)
        d.cpu_access(a, h, write=True)
        with self.assertRaises(gpu.ContractError):
            d.submit(a, {h: "read"})
        d.synchronize(a, h, "clean")
        fence = d.submit(a, {h: "write"})
        for operation in (lambda: d.cpu_access(a, h), lambda: d.unmap_cpu(a, h),
                          lambda: d.synchronize(a, h, "invalidate")):
            with self.assertRaises(gpu.ContractError):
                operation()
        d.backend_complete(fence)
        with self.assertRaises(gpu.ContractError):
            d.cpu_access(a, h)
        d.synchronize(a, h, "invalidate")
        d.cpu_access(a, h)
        d.unmap_cpu(a, h)
        d.unmap_gpu(a, h, 0x100000)
        d.free(a, h)

    def test_foreign_handles_and_partial_invalid_submit_are_atomic(self):
        d = self.device()
        a, b = d.client(), d.client()
        h = self.mapped(d, a)
        other = self.mapped(d, b)
        for operation in (lambda: d.submit(b, {h: "read"}),
                          lambda: d.submit(a, {h: "read", other: "read"}),
                          lambda: d.map_cpu(b, h)):
            with self.assertRaises(gpu.ContractError):
                operation()
        # Failed multi-BO validation must leave no reference on the valid BO.
        d.unmap_gpu(a, h, 0x100000)
        d.free(a, h)
        fence = d.submit(b, {other: "read"})
        with self.assertRaises(gpu.ContractError):
            d.wait(a, fence, 1)

    def test_va_overflow_overlap_alignment_and_invalid_waits(self):
        d = self.device()
        a = d.client()
        h = self.mapped(d, a)
        other = d.allocate(a, 4096)
        for address, offset, size in ((0x100000, 0, 4096), (0x100001, 0, 4096),
                                      (0x104000, 1, 4096), (0x200000, 0, 4096),
                                      (2**64 - 4096, 0, 8192), (0x104000, 0, True)):
            with self.subTest(address=address, offset=offset, size=size), self.assertRaises(gpu.ContractError):
                d.map_gpu(a, other, address=address, offset=offset, size=size)
        fence = d.submit(a, {h: "read"})
        for timeout in (-1, True, 0.1, 100_000_001, 2**64):
            with self.subTest(timeout=timeout), self.assertRaises(gpu.ContractError):
                d.wait(a, fence, timeout)
        for size in (0, -1, True, 2**64 - 1):
            with self.subTest(size=size), self.assertRaises(gpu.ContractError):
                d.allocate(a, size)
        for page in (True, 4096.0, 8192):
            with self.subTest(page=page), self.assertRaises(gpu.ContractError):
                self.device(page)

    def test_unordered_gpu_writes_cannot_race_existing_references(self):
        d = self.device()
        a = d.client()
        h = self.mapped(d, a)
        read = d.submit(a, {h: "read"})
        with self.assertRaises(gpu.ContractError):
            d.submit(a, {h: "write"})
        d.backend_complete(read)
        write = d.submit(a, {h: "write"})
        for access in ("read", "write"):
            with self.assertRaises(gpu.ContractError):
                d.submit(a, {h: access})
        d.backend_complete(write, error=True)
        self.assertEqual(d.wait(a, write, 0), "error")


if __name__ == "__main__":
    unittest.main()
