"""Synthetic SGPU lifetime oracle. No GPU, kernel, file, clock or network I/O.

The backend_* methods inject trusted MOCK observations for host tests. They are
not proposed userspace driver requests or evidence of actual hardware retirement.
This single-threaded model is not a memory allocator or a security boundary.
"""
from dataclasses import dataclass, field

GPU_PAGE = 4096
U64_LIMIT = 1 << 64
MAX_WAIT_NS = 100_000_000


class ContractError(ValueError):
    pass


def integer(value, minimum=1, maximum=U64_LIMIT - 1):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ContractError("invalid integer or policy bound")
    return value


def rounded(value, alignment):
    result = (integer(value) + alignment - 1) // alignment * alignment
    if result >= U64_LIMIT:
        raise ContractError("size overflow")
    return result


@dataclass
class _Buffer:
    owner: int
    gpu_bytes: int
    backing_bytes: int
    cpu_mapped: bool = False
    cpu_dirty: bool = False
    gpu_dirty: bool = False
    mappings: dict = field(default_factory=dict)
    pending: set = field(default_factory=set)


@dataclass
class _Fence:
    owner: int
    uses: dict
    result: str = "pending"


class Device:
    """One mock device and shared budget, with explicitly supplied synthetic VA.

    Handles increase for the entire lifetime of this instance and are never
    recycled. Real backends additionally need authenticated clients, locks,
    command validation, page pinning, zeroing and cache/TLB maintenance.
    """

    def __init__(self, *, cpu_page, budget, va_start, va_bytes):
        if type(cpu_page) is not int or cpu_page not in (4096, 16384):
            raise ContractError("CPU granule must be queried, not guessed")
        self.cpu_page = cpu_page
        self.budget = integer(budget)
        self.va_start = integer(va_start)
        self.va_bytes = integer(va_bytes)
        if va_start % GPU_PAGE or va_bytes % GPU_PAGE or va_start + va_bytes >= U64_LIMIT:
            raise ContractError("invalid synthetic GPU VA window")
        self.used = 0
        self._next = 0
        self._clients = {}
        self._buffers = {}
        self._fences = {}
        self._faulted = False

    def _id(self):
        integer(self._next + 1)
        self._next += 1
        return self._next

    def client(self):
        if self._faulted:
            raise ContractError("device faulted")
        handle = self._id()
        self._clients[handle] = False
        return handle

    def _client(self, client, *, accepting=False):
        integer(client)
        if client not in self._clients:
            raise ContractError("unknown client")
        if accepting and (self._clients[client] or self._faulted):
            raise ContractError("client stopped or device faulted")

    def _buffer(self, client, handle):
        self._client(client)
        integer(handle)
        buffer = self._buffers.get(handle)
        if buffer is None or buffer.owner != client:
            raise ContractError("stale or foreign buffer")
        return buffer

    def allocate(self, client, size):
        self._client(client, accepting=True)
        gpu_bytes = rounded(size, GPU_PAGE)
        backing_bytes = rounded(gpu_bytes, self.cpu_page)
        if backing_bytes > self.budget - self.used:
            raise ContractError("shared backing budget exhausted")
        handle = self._id()
        self._buffers[handle] = _Buffer(client, gpu_bytes, backing_bytes)
        self.used += backing_bytes
        return handle

    def map_cpu(self, client, handle):
        self._client(client, accepting=True)
        buffer = self._buffer(client, handle)
        if buffer.cpu_mapped or buffer.pending:
            raise ContractError("CPU mapping already present or GPU in flight")
        buffer.cpu_mapped = True

    def unmap_cpu(self, client, handle):
        buffer = self._buffer(client, handle)
        if not buffer.cpu_mapped or buffer.pending:
            raise ContractError("CPU mapping absent or GPU in flight")
        buffer.cpu_mapped = False

    def cpu_access(self, client, handle, *, write=False):
        buffer = self._buffer(client, handle)
        if type(write) is not bool:
            raise ContractError("write must be boolean")
        if not buffer.cpu_mapped or buffer.pending or buffer.gpu_dirty:
            raise ContractError("CPU access requires idle, mapped, invalidated backing")
        if write:
            buffer.cpu_dirty = True

    def synchronize(self, client, handle, operation):
        buffer = self._buffer(client, handle)
        if buffer.pending or not buffer.cpu_mapped:
            raise ContractError("cache transition requires idle CPU mapping")
        if operation == "clean" and not buffer.gpu_dirty:
            buffer.cpu_dirty = False
        elif operation == "invalidate" and not buffer.cpu_dirty:
            buffer.gpu_dirty = False
        else:
            raise ContractError("unknown or conflicting cache transition")

    def map_gpu(self, client, handle, *, address, offset, size):
        self._client(client, accepting=True)
        buffer = self._buffer(client, handle)
        integer(address)
        integer(offset, minimum=0)
        integer(size)
        if buffer.pending:
            raise ContractError("cannot alter mappings in flight")
        if any(value % GPU_PAGE for value in (address, offset, size)):
            raise ContractError("GPU mapping must use 4 KiB granules")
        end = address + size
        if offset + size > buffer.gpu_bytes or address < self.va_start or end > self.va_start + self.va_bytes:
            raise ContractError("mapping outside BO or synthetic VA window")
        for other in self._buffers.values():
            if other.owner == client:
                for start, (_, length) in other.mappings.items():
                    if address < start + length and start < end:
                        raise ContractError("overlapping GPU VA")
        buffer.mappings[address] = (offset, size)

    def unmap_gpu(self, client, handle, address):
        buffer = self._buffer(client, handle)
        integer(address)
        if buffer.pending or address not in buffer.mappings:
            raise ContractError("mapping absent or GPU in flight")
        del buffer.mappings[address]

    def submit(self, client, uses):
        """Uses is {buffer_handle: 'read'|'write'}; no ordered dependencies yet.

        This only models whole-buffer references, not executable command bytes.
        Real submissions must validate IBs, contexts, ranges and dependency cycles.
        """
        self._client(client, accepting=True)
        if type(uses) is not dict or not uses:
            raise ContractError("nonempty explicit use set required")
        buffers = []
        for handle, access in uses.items():
            buffer = self._buffer(client, handle)
            if access not in ("read", "write") or not buffer.mappings or buffer.cpu_dirty:
                raise ContractError("invalid access, unmapped BO or CPU cache not cleaned")
            if buffer.pending and (access == "write" or any(
                self._fences[f].uses[handle] == "write" for f in buffer.pending
            )):
                raise ContractError("unordered concurrent write")
            buffers.append(buffer)
        fence = self._id()
        self._fences[fence] = _Fence(client, dict(uses))
        for buffer in buffers:
            buffer.pending.add(fence)
        return fence

    def wait(self, client, fence, timeout_ns):
        self._client(client)
        integer(fence)
        integer(timeout_ns, minimum=0, maximum=MAX_WAIT_NS)
        observed = self._fences.get(fence)
        if observed is None or observed.owner != client:
            raise ContractError("stale or foreign fence")
        # No sleeping or progress is simulated. Timeout never retires resources.
        return "timeout" if observed.result == "pending" else observed.result

    def stop(self, client):
        self._client(client)
        self._clients[client] = True

    def backend_fault(self):
        """MOCK fault observation: reject work, retain all outstanding references."""
        self._faulted = True

    def backend_complete(self, fence, *, error=False):
        """MOCK trusted retirement, never a userspace completion assertion."""
        integer(fence)
        observed = self._fences.get(fence)
        if observed is None or observed.result != "pending" or type(error) is not bool:
            raise ContractError("invalid retirement observation")
        for handle, access in observed.uses.items():
            buffer = self._buffers[handle]
            buffer.pending.remove(fence)
            if access == "write":
                buffer.gpu_dirty = True
        observed.result = "error" if error else "complete"

    def backend_quiesced(self):
        """MOCK proof all DMA/queues stopped; a reset request alone is insufficient."""
        if not self._faulted:
            raise ContractError("quiescence path requires fault quarantine")
        for fence, observed in self._fences.items():
            if observed.result == "pending":
                self.backend_complete(fence, error=True)

    def free(self, client, handle):
        buffer = self._buffer(client, handle)
        if buffer.pending or buffer.cpu_mapped or buffer.mappings:
            raise ContractError("buffer still owned by a mapping or submission")
        self.used -= buffer.backing_bytes
        del self._buffers[handle]
