"""Bounded host model of CPIF link frames; never opens a device or sends data.

Project-owned implementation from field-layout facts in the pinned Samsung
headers linked in README.md. One physical frame only; payload remains opaque.
The real e1s protocol/queue configuration has not been measured.
"""
from dataclasses import dataclass
from enum import Enum
import struct

MAX_FRAME = 1 << 20  # Host policy, not a measured firmware limit.


class Protocol(str, Enum):
    SIPC5 = "sipc5"
    SIT = "sit"


class FrameError(ValueError):
    pass


class TruncatedFrame(FrameError):
    pass


@dataclass(frozen=True)
class Frame:
    protocol: Protocol
    channel: int
    wire_length: int
    consumed: int
    payload: bytes
    control: int | None = None
    sequence: int | None = None
    channel_sequence: int | None = None
    extension: bytes = b""


def parse_frame(data: bytes, protocol: Protocol | str, *, max_frame: int = MAX_FRAME) -> Frame:
    """Decode one complete frame, returning its consumed bytes including padding.

    Require an explicit protocol; do not guess from an unverified device profile.
    Extra bytes belong to a following frame and are left unconsumed. Multi-frame
    control is returned raw; this function does not reassemble fragments or
    interpret RIL/APDU/IP payloads. Padding contents are not specified as zero.
    """
    try:
        mode = Protocol(protocol)
    except (ValueError, TypeError) as error:
        raise FrameError("Select a verified protocol explicitly: sipc5 or sit") from error
    if type(max_frame) is not int or not 1 <= max_frame <= MAX_FRAME:
        raise FrameError("Host frame budget must be 1..1048576 bytes")
    view = memoryview(data).cast("B")
    control = sequence = channel_sequence = None
    extension = b""
    if mode == Protocol.SIPC5:
        if len(view) < 4:
            raise TruncatedFrame("Missing SIPC5 base header")
        cfg, channel = view[0], view[1]
        if cfg & 0xF8 != 0xF8:
            raise FrameError("Invalid SIPC5 start bits")
        variant = cfg & 3
        if variant == 1:
            raise FrameError("Unsupported SIPC5 control-only variant")
        header = {0: 4, 2: 6, 3: 5}[variant]
        if len(view) < header:
            raise TruncatedFrame("Missing SIPC5 extension/control")
        size = struct.unpack_from("<I" if variant == 2 else "<H", view, 2)[0]
        if variant == 3:
            control = view[4]
        alignment = 8 if cfg & 4 else 1
    else:
        # The packed declared fields occupy 10 bytes, but the wire header is 12.
        header, alignment = 12, 8
        if len(view) < header:
            raise TruncatedFrame("Missing SIT 12-byte wire header")
        sync, sequence, control, size, channel, channel_sequence = struct.unpack_from("<HHHHBB", view)
        if sync != 0xABCD:
            raise FrameError("Invalid SIT sync word")
        extension = bytes(view[10:12])
    if size < header:
        raise FrameError("Wire length is smaller than its header")
    if size > max_frame:
        raise FrameError("Wire length exceeds the host frame budget")
    consumed = (size + alignment - 1) // alignment * alignment
    if len(view) < consumed:
        raise TruncatedFrame("Incomplete payload or alignment padding")
    return Frame(mode, channel, size, consumed, bytes(view[header:size]), control,
                 sequence, channel_sequence, extension)
