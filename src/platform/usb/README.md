# Read-only USB transport boundary

`readonly.c` is reusable freestanding C for a future USB bulk transport. It
implements a complete-frame read-only block server/client and DMA address-range
arithmetic. It allocates no memory and performs no I/O. The server has only a
read callback. A real host test opens an owned image with `O_RDONLY`; native USB
enumeration, endpoint I/O, PHY, clocks, IRQ, IOMMU and XNU block-device integration
are separate work. `profile.json` records source-derived E1S requirements.

## Wire format S24R1

All integers are little endian. The header is encoded byte by byte; no C struct
is cast onto untrusted wire data. Every request has exactly 40 bytes.

| Offset | Bytes | Field |
|---|---|---|
| 0 | 4 | ASCII `S24R` |
| 4 | 2 | Version 1 |
| 6 | 2 | READ=1, reply=0x8001 |
| 8 | 8 | Nonzero session id |
| 16 | 8 | Nonzero monotonically increasing request id |
| 24 | 8 | Byte offset in the read-only image |
| 32 | 4 | Read length, positive and at most 65536 |
| 36 | 4 | Reserved, must be zero |

A successful reply repeats session/id/offset/length and appends exactly length
bytes. There is no success response for failed/short reads. Any other request
opcode is rejected. Geometry requires power-of-two 512..4096 byte blocks,
nonzero block-aligned capacity and a block-aligned maximum transfer. Client
LBA multiplication and server byte extents are checked before the read callback.
The request's length is not a request payload length.

The future endpoint layer must assemble exactly one complete bounded frame
before this API is called. USB packets/URBs need not coincide with frames.
This code rejects truncated or extra bytes; it does not implement streaming
assembly, endpoint descriptors, USB MSC, UASP or a peer handshake. S24R1 is an
owned research protocol requiring a matching peer; no Apple USB service ABI
is asserted.

## Lifecycle and ownership

Zero-initialize each state object once. Calls are serialized by a single owner;
native interrupt synchronization is the integrator's responsibility. There is
one pending client read. All state objects and output/view objects must occupy
valid, independent storage. Caller-supplied buffer capacities must describe
actual accessible memory. The backend is trusted to write no more than the
provided length and return its actual byte count.

A backend may synchronously disconnect its server; its in-flight slot remains
held until return, so reconnect cannot reuse it while the callback is live.
Partial/error reads and disconnect during a callback scrub the bounded response
region and return zero outgoing bytes. Request ids are consumed before backend
work, so a backend failure cannot replay that id. Buffer-capacity rejection
performs no read and consumes no id.

Disconnect invalidates pending client state. A malformed, stale or mismatched
reply closes the client session before exposing data. A valid reply returns a
borrowed immutable view into the receive buffer; the view expires when the
caller reuses/frees that buffer. Reconnect requires a larger nonzero session id
within the same state lifetime. Request-id exhaustion fails without wrapping.
Fresh peer binding across process restart, authentication, deadlines and a
hardware watchdog are not implemented by this state machine.

The DMA helper checks the entire supplied CPU/bus window and a requested slice
for representability and address-width bounds. It does not prove that a mapping
exists or synchronize caches. USB disconnect is not proof that DMA stopped;
native code must quiesce endpoints and verify completion before freeing memory.

## Checks

```sh
python3 src/platform/usb/check.py --run fresh-run
```

This requires existing pinned primary checkouts under the main laboratory's
`references/`, a host C/C++ compiler, host Clang sanitizers and the existing NDK
Clang. The script accepts `--lab-root`, `--host-clang` and `--clang` overrides.
It snapshots sources and checks actual command exits, malformed/truncated/
unaligned frames, range arithmetic, replay, response mismatch, partial backend
reads, callback disconnect, read-only file use, 20000 deterministic mutations,
an independent Python wire vector and four real ARM object formats. ARM objects
are compiled and inspected, not executed. No phone is selected.
Separate deliberately invalid host controls must trigger ASan heap-overflow and
UBSan signed-overflow diagnostics; they are never linked into the adapter.

All adapter code is project-owned. No GPL vendor driver implementation is
copied into it. Source facts remain attributed to the pinned upstream files.
