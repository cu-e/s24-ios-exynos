#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Pure-Python LZFSE / LZVN stream decoder (decode only), for the IOS-002 IPSW inspector.

This is a port of the decoder in https://github.com/lzfse/lzfse at the pinned revision
e634ca58b4821d9f3d560cdc6df5dec02ffc93fd (research/sources.json id "lzfse", references/lzfse/src/:
lzfse_decode_base.c, lzfse_fse.c, lzfse_fse.h, lzfse_internal.h, lzvn_decode_base.c). The structure of the
block headers, the FSE table construction, the bit-stream refill rules and the LZVN opcode table follow that
source line by line; this file is not a new format implementation.

    Copyright (c) 2015-2016, Apple Inc. All rights reserved.

    Redistribution and use in source and binary forms, with or without modification, are permitted provided that
    the following conditions are met:
    1.  Redistributions of source code must retain the above copyright notice, this list of conditions and the
        following disclaimer.
    2.  Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the
        following disclaimer in the documentation and/or other materials provided with the distribution.
    3.  Neither the name of the copyright holder(s) nor the names of any contributors may be used to endorse or
        promote products derived from this software without specific prior written permission.
    THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED
    WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A
    PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY
    DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
    PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
    CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE
    OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH
    DAMAGE.

Differences from the reference, all on the strict side (a valid stream decodes identically):
  * the whole output is one growing bytearray (no destination-full resume);
  * a block must produce exactly its header's n_raw_bytes, and an LZVN block must consume exactly n_payload_bytes
    and end with its end-of-stream opcode;
  * reading a literal beyond the block's n_literals, a zero or out-of-range match distance at a match-only opcode
    and an FSE state beyond the table are errors, where the reference reads uninitialised memory;
  * 'bvx1' blocks (uncompressed frequency tables, a padded C struct) are refused by name: the encoder in the
    reference writes 'bvx2' and no 'bvx1' stream is available to test against.

Public API: decode(data) -> bytes; iter_blocks(data) yields (kind, output_bytearray) after each block, so a caller
can stop early; LzfseError for every malformed or unsupported input."""
import struct

MAGIC_NONE = 0
MAGIC_EOS = 0x24787662   # 'bvx$'
MAGIC_RAW = 0x2d787662   # 'bvx-'
MAGIC_V1 = 0x31787662    # 'bvx1'
MAGIC_V2 = 0x32787662    # 'bvx2'
MAGIC_LZVN = 0x6e787662  # 'bvxn'

L_SYMBOLS, M_SYMBOLS, D_SYMBOLS, LIT_SYMBOLS = 20, 20, 64, 256
L_STATES, M_STATES, D_STATES, LIT_STATES = 64, 64, 256, 1024
MATCHES_PER_BLOCK = 10000
LITERALS_PER_BLOCK = 4 * MATCHES_PER_BLOCK

L_EXTRA_BITS = (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 3, 5, 8)
L_BASE = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 20, 28, 60)
M_EXTRA_BITS = (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3, 5, 8, 11)
M_BASE = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 24, 56, 312)
D_EXTRA_BITS = (0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3,
                4, 4, 4, 4, 5, 5, 5, 5, 6, 6, 6, 6, 7, 7, 7, 7,
                8, 8, 8, 8, 9, 9, 9, 9, 10, 10, 10, 10, 11, 11, 11, 11,
                12, 12, 12, 12, 13, 13, 13, 13, 14, 14, 14, 14, 15, 15, 15, 15)
D_BASE = (0, 1, 2, 3, 4, 6, 8, 10, 12, 16,
          20, 24, 28, 36, 44, 52, 60, 76, 92, 108,
          124, 156, 188, 220, 252, 316, 380, 444, 508, 636,
          764, 892, 1020, 1276, 1532, 1788, 2044, 2556, 3068, 3580,
          4092, 5116, 6140, 7164, 8188, 10236, 12284, 14332, 16380, 20476,
          24572, 28668, 32764, 40956, 49148, 57340, 65532, 81916, 98300, 114684,
          131068, 163836, 196604, 229372)

_FREQ_NBITS = (2, 3, 2, 5, 2, 3, 2, 8, 2, 3, 2, 5, 2, 3, 2, 14,
               2, 3, 2, 5, 2, 3, 2, 8, 2, 3, 2, 5, 2, 3, 2, 14)
_FREQ_VALUE = (0, 2, 1, 4, 0, 3, 1, -1, 0, 2, 1, 5, 0, 3, 1, -1,
               0, 2, 1, 6, 0, 3, 1, -1, 0, 2, 1, 7, 0, 3, 1, -1)


class LzfseError(Exception):
    pass


def _field(v, offset, nbits):
    return (v >> offset) & ((1 << nbits) - 1)


def _decode_freqs(buf, src, src_end):
    """The 360 frequencies (l, m, d, literal) packed after a 'bvx2' header (lzfse_decode_v1)."""
    n_values = L_SYMBOLS + M_SYMBOLS + D_SYMBOLS + LIT_SYMBOLS
    if src == src_end:
        return [0] * n_values   # frequency tables omitted
    values = []
    accum = 0
    accum_nbits = 0
    for _ in range(n_values):
        while src < src_end and accum_nbits + 8 <= 32:
            accum |= buf[src] << accum_nbits
            accum_nbits += 8
            src += 1
        b = accum & 31
        n = _FREQ_NBITS[b]
        if n == 8:
            v = 8 + ((accum >> 4) & 0xf)
        elif n == 14:
            v = 24 + ((accum >> 4) & 0x3ff)
        else:
            v = _FREQ_VALUE[b]
        if n > accum_nbits:
            raise LzfseError("frequency table truncated")
        accum >>= n
        accum_nbits -= n
        values.append(v)
    if accum_nbits >= 8 or src != src_end:
        raise LzfseError("frequency table does not end at the header end")
    return values


def _check_freq(freq, nstates, what):
    if sum(freq) > nstates:
        raise LzfseError("%s frequencies sum beyond %d states" % (what, nstates))


def _geometry(nstates, f):
    k = nstates.bit_length() - f.bit_length()   # clz(f) - clz(nstates)
    j0 = ((2 * nstates) >> k) - f
    return k, j0


def _literal_table(freq):
    """fse_init_decoder_table: state -> (k, symbol, delta)."""
    table = []
    for sym, f in enumerate(freq):
        if f == 0:
            continue
        k, j0 = _geometry(LIT_STATES, f)
        for j in range(f):
            if j < j0:
                table.append((k, sym, ((f + j) << k) - LIT_STATES))
            else:
                table.append((k - 1, sym, (j - j0) << (k - 1)))
        if len(table) > LIT_STATES:
            raise LzfseError("literal frequencies exceed the state count")
    return table


def _value_table(nstates, freq, vbits, vbase):
    """fse_init_value_decoder_table: state -> (total_bits, value_bits, delta, vbase)."""
    table = []
    for sym, f in enumerate(freq):
        if f == 0:
            continue
        k, j0 = _geometry(nstates, f)
        for j in range(f):
            if j < j0:
                table.append((k + vbits[sym], vbits[sym], ((f + j) << k) - nstates, vbase[sym]))
            else:
                table.append((k - 1 + vbits[sym], vbits[sym], (j - j0) << (k - 1), vbase[sym]))
    return table


def _stream_init(data, nbits_field, end, start):
    """fse_in_checked_init64: returns (accum, accum_nbits, pos)."""
    if nbits_field:
        if end < start + 8:
            raise LzfseError("FSE stream out of range")
        pos = end - 8
        accum = int.from_bytes(data[pos:pos + 8], "little")
        nbits = nbits_field + 64
    else:
        if end < start + 7:
            raise LzfseError("FSE stream out of range")
        pos = end - 7
        accum = int.from_bytes(data[pos:pos + 7], "little")
        nbits = 56
    if nbits < 56 or nbits >= 64 or (accum >> nbits) != 0:
        raise LzfseError("FSE stream start is invalid")
    return accum, nbits, pos


def _decode_literals(data, header, lit_end, table):
    n_literals, literal_bits, states = header["n_literals"], header["literal_bits"], list(header["literal_state"])
    accum, nbits, pos = _stream_init(data, literal_bits, lit_end, 0)   # the reference bounds this by the whole source
    out = bytearray(n_literals)
    try:
        for i in range(0, n_literals, 4):
            take = (63 - nbits) & -8
            pos -= take >> 3
            if pos < 0:
                raise LzfseError("literal stream out of range")
            accum = (accum << take) | int.from_bytes(data[pos:pos + (take >> 3)], "little")
            nbits += take
            for j in range(4):
                k, sym, delta = table[states[j]]
                nbits -= k
                if nbits < 0:
                    raise LzfseError("literal stream underflow")
                bits = accum >> nbits
                accum &= (1 << nbits) - 1
                states[j] = (delta + bits) & 0xFFFF
                out[i + j] = sym
    except IndexError:
        raise LzfseError("literal FSE state outside the table")
    return out


def _decode_lmd(data, header, lmd_start, lmd_end, literals, tables, out):
    l_tab, m_tab, d_tab = tables
    accum, nbits, pos = _stream_init(data, header["lmd_bits"], lmd_end, lmd_start)
    l_state, m_state, d_state = header["l_state"], header["m_state"], header["d_state"]
    n_literals = len(literals)
    lit = 0
    D = -1
    try:
        for _ in range(header["n_matches"]):
            take = (63 - nbits) & -8
            pos -= take >> 3
            if pos < lmd_start:
                raise LzfseError("LMD stream out of range")
            accum = (accum << take) | int.from_bytes(data[pos:pos + (take >> 3)], "little")
            nbits += take
            # L
            total, vbits, delta, vbase = l_tab[l_state]
            nbits -= total
            if nbits < 0:
                raise LzfseError("LMD stream underflow")
            sv = accum >> nbits
            accum &= (1 << nbits) - 1
            l_state = (delta + (sv >> vbits)) & 0xFFFF
            L = vbase + (sv & ((1 << vbits) - 1))
            if lit + L >= LITERALS_PER_BLOCK + 64:
                raise LzfseError("literal length beyond the block limit")
            # M
            total, vbits, delta, vbase = m_tab[m_state]
            nbits -= total
            if nbits < 0:
                raise LzfseError("LMD stream underflow")
            sv = accum >> nbits
            accum &= (1 << nbits) - 1
            m_state = (delta + (sv >> vbits)) & 0xFFFF
            M = vbase + (sv & ((1 << vbits) - 1))
            # D
            total, vbits, delta, vbase = d_tab[d_state]
            nbits -= total
            if nbits < 0:
                raise LzfseError("LMD stream underflow")
            sv = accum >> nbits
            accum &= (1 << nbits) - 1
            d_state = (delta + (sv >> vbits)) & 0xFFFF
            new_d = vbase + (sv & ((1 << vbits) - 1))
            if new_d:
                D = new_d
            # execute
            if D < 0 or D > len(out) + L:
                raise LzfseError("match distance beyond the output")
            if lit + L > n_literals:
                raise LzfseError("literal length beyond the block's literals")
            out += literals[lit:lit + L]
            lit += L
            if M:
                if D == 0:
                    raise LzfseError("zero match distance")
                start = len(out) - D
                if D >= M:
                    out += out[start:start + M]
                else:
                    chunk = bytes(out[start:])
                    out += (chunk * (M // D + 1))[:M]
    except IndexError:
        raise LzfseError("LMD FSE state outside the table")


def _lzvn_class(opc):
    if opc < 112 or 128 <= opc < 160 or 192 <= opc < 208:
        if opc == 6:
            return "eos"
        if opc in (14, 22):
            return "nop"
        if opc < 64 and opc & 7 == 6:
            return "udef"   # 30, 38, 46, 54, 62
        if opc & 7 == 6:
            return "pre_d"
        if opc & 7 == 7:
            return "lrg_d"
        return "sml_d"
    if 160 <= opc < 192:
        return "med_d"
    if opc == 224:
        return "lrg_l"
    if 225 <= opc < 240:
        return "sml_l"
    if opc == 240:
        return "lrg_m"
    if opc > 240:
        return "sml_m"
    return "udef"   # 112..127, 208..223


_LZVN_CLASS = tuple(_lzvn_class(i) for i in range(256))


def _lzvn_block(out, payload, n_raw):
    """lzvn_decode over one 'bvxn' payload; matches may reach into earlier output. Appends exactly n_raw bytes."""
    base = len(out)
    pos = 0
    end = len(payload)
    D = 0
    if end == 0:
        raise LzfseError("empty LZVN payload")
    while True:
        src_len = end - pos
        opc = payload[pos]
        kind = _LZVN_CLASS[opc]
        if kind == "eos":
            if src_len < 8:
                raise LzfseError("LZVN end-of-stream opcode truncated")
            pos += 8
            break
        if kind == "udef":
            raise LzfseError("undefined LZVN opcode 0x%02x" % opc)
        if kind == "nop":
            if src_len <= 1:
                raise LzfseError("LZVN truncated after a nop")
            pos += 1
            continue
        L = M = 0
        has_literal = has_match = False
        if kind == "sml_d" or kind == "lrg_d" or kind == "pre_d" or kind == "med_d":
            has_literal = has_match = True
            if kind == "sml_d":
                opc_len = 2
                L = (opc >> 6) & 3
                M = ((opc >> 3) & 7) + 3
                if src_len <= opc_len + L:
                    raise LzfseError("LZVN truncated")
                D = ((opc & 7) << 8) | payload[pos + 1]
            elif kind == "med_d":
                opc_len = 3
                L = (opc >> 3) & 3
                if src_len <= opc_len + L:
                    raise LzfseError("LZVN truncated")
                opc23 = payload[pos + 1] | (payload[pos + 2] << 8)
                M = (((opc & 7) << 2) | (opc23 & 3)) + 3
                D = (opc23 >> 2) & 0x3fff
            elif kind == "lrg_d":
                opc_len = 3
                L = (opc >> 6) & 3
                M = ((opc >> 3) & 7) + 3
                if src_len <= opc_len + L:
                    raise LzfseError("LZVN truncated")
                D = payload[pos + 1] | (payload[pos + 2] << 8)
            else:   # pre_d
                opc_len = 1
                L = (opc >> 6) & 3
                M = ((opc >> 3) & 7) + 3
                if src_len <= opc_len + L:
                    raise LzfseError("LZVN truncated")
        elif kind == "sml_m":
            opc_len = 1
            if src_len <= opc_len:
                raise LzfseError("LZVN truncated")
            M = opc & 15
            has_match = True
        elif kind == "lrg_m":
            opc_len = 2
            if src_len <= opc_len:
                raise LzfseError("LZVN truncated")
            M = payload[pos + 1] + 16
            has_match = True
        elif kind == "sml_l":
            opc_len = 1
            L = opc & 15
            has_literal = True
        else:   # lrg_l
            opc_len = 2
            if src_len <= 2:
                raise LzfseError("LZVN truncated")
            L = payload[pos + 1] + 16
            has_literal = True
        if kind in ("sml_l", "lrg_l") and src_len <= opc_len + L:
            raise LzfseError("LZVN truncated")
        pos += opc_len
        if has_literal:
            out += payload[pos:pos + L]
            pos += L
        if has_match:
            if kind in ("sml_d", "med_d", "lrg_d", "pre_d") and (D > len(out) or D == 0):
                raise LzfseError("invalid LZVN match distance")
            if kind in ("sml_m", "lrg_m") and (D > len(out) or D == 0):
                raise LzfseError("LZVN match-only opcode without a valid previous distance")
            start = len(out) - D
            if D >= M:
                out += out[start:start + M]
            else:
                chunk = bytes(out[start:])
                out += (chunk * (M // D + 1))[:M]
        if len(out) - base > n_raw:
            raise LzfseError("LZVN block produced more than its n_raw_bytes")
    if pos != end:
        raise LzfseError("LZVN block did not consume its payload")
    if len(out) - base != n_raw:
        raise LzfseError("LZVN block produced %d bytes, header says %d" % (len(out) - base, n_raw))


def _v2_header(data, pos):
    if pos + 32 > len(data):
        raise LzfseError("bvx2 header truncated")
    n_raw = struct.unpack_from("<I", data, pos + 4)[0]
    v0, v1, v2 = struct.unpack_from("<QQQ", data, pos + 8)
    header_size = _field(v2, 0, 32)
    if header_size < 32 or pos + header_size > len(data):
        raise LzfseError("bvx2 header size out of range")
    freq = _decode_freqs(data, pos + 32, pos + header_size)
    h = dict(
        n_raw=n_raw, header_size=header_size,
        n_literals=_field(v0, 0, 20), n_literal_payload_bytes=_field(v0, 20, 20), n_matches=_field(v0, 40, 20),
        literal_bits=_field(v0, 60, 3) - 7,
        literal_state=[_field(v1, 10 * i, 10) for i in range(4)],
        n_lmd_payload_bytes=_field(v1, 40, 20), lmd_bits=_field(v1, 60, 3) - 7,
        l_state=_field(v2, 32, 10), m_state=_field(v2, 42, 10), d_state=_field(v2, 52, 10),
        l_freq=freq[0:20], m_freq=freq[20:40], d_freq=freq[40:104], literal_freq=freq[104:360])
    if h["n_literals"] > LITERALS_PER_BLOCK or h["n_matches"] > MATCHES_PER_BLOCK:
        raise LzfseError("bvx2 block counts beyond the per-block limits")
    if h["n_literals"] % 4:
        raise LzfseError("bvx2 literal count is not a multiple of 4")
    if any(s >= LIT_STATES for s in h["literal_state"]) or h["l_state"] >= L_STATES \
            or h["m_state"] >= M_STATES or h["d_state"] >= D_STATES:
        raise LzfseError("bvx2 initial state out of range")
    _check_freq(h["l_freq"], L_STATES, "L")
    _check_freq(h["m_freq"], M_STATES, "M")
    _check_freq(h["d_freq"], D_STATES, "D")
    _check_freq(h["literal_freq"], LIT_STATES, "literal")
    return h


def iter_blocks(data):
    """Decode a raw LZFSE stream block by block; yields (kind, output) after each block, the same bytearray each
    time. The stream must end with its 'bvx$' block."""
    data = bytes(data)
    out = bytearray()
    pos = 0
    while True:
        if pos + 4 > len(data):
            raise LzfseError("stream ends without a bvx$ block")
        magic = struct.unpack_from("<I", data, pos)[0]
        if magic == MAGIC_EOS:
            yield "bvx$", out
            return
        if magic == MAGIC_RAW:
            if pos + 8 > len(data):
                raise LzfseError("bvx- header truncated")
            n = struct.unpack_from("<I", data, pos + 4)[0]
            if pos + 8 + n > len(data):
                raise LzfseError("bvx- payload truncated")
            out += data[pos + 8:pos + 8 + n]
            pos += 8 + n
            yield "bvx-", out
        elif magic == MAGIC_LZVN:
            if pos + 12 > len(data):
                raise LzfseError("bvxn header truncated")
            n_raw, n_payload = struct.unpack_from("<II", data, pos + 4)
            if pos + 12 + n_payload > len(data):
                raise LzfseError("bvxn payload truncated")
            _lzvn_block(out, data[pos + 12:pos + 12 + n_payload], n_raw)
            pos += 12 + n_payload
            yield "bvxn", out
        elif magic == MAGIC_V2:
            h = _v2_header(data, pos)
            lit_start = pos + h["header_size"]
            lit_end = lit_start + h["n_literal_payload_bytes"]
            lmd_end = lit_end + h["n_lmd_payload_bytes"]
            if lmd_end > len(data):
                raise LzfseError("bvx2 payload truncated")
            literals = _decode_literals(data, h, lit_end, _literal_table(h["literal_freq"]))
            tables = (_value_table(L_STATES, h["l_freq"], L_EXTRA_BITS, L_BASE),
                      _value_table(M_STATES, h["m_freq"], M_EXTRA_BITS, M_BASE),
                      _value_table(D_STATES, h["d_freq"], D_EXTRA_BITS, D_BASE))
            before = len(out)
            _decode_lmd(data, h, lit_end, lmd_end, literals, tables, out)
            if len(out) - before != h["n_raw"]:
                raise LzfseError("bvx2 block produced %d bytes, header says %d" % (len(out) - before, h["n_raw"]))
            pos = lmd_end
            yield "bvx2", out
        elif magic == MAGIC_V1:
            raise LzfseError("bvx1 blocks are not supported by this decoder (see the module docstring)")
        else:
            raise LzfseError("unknown block magic 0x%08x at offset %d" % (magic, pos))


def decode(data):
    out = None
    for _kind, out in iter_blocks(data):
        pass
    return bytes(out)
