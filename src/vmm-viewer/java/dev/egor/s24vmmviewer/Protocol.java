package dev.egor.s24vmmviewer;

import java.io.IOException;

/**
 * The s24vmm frame/touch wire protocol (src/vmm/scfb.h), without Android dependencies so that the
 * host JVM can test it against the C encoder.
 *
 * VMM to viewer: a 48-byte little-endian header followed by w*h*4 XR24 pixel bytes:
 *   0 magic "S24F", 4 version 1, 8 width, 12 height, 16 frame_seq (u64), 24 x, 28 y, 32 w, 36 h,
 *   40 format XR24, 44 payload bytes.
 * Viewer to VMM: 20-byte touch messages: 0 magic "S24T", 4 slot (0..9), 8 tracking_id (-1 lifts the
 * finger), 12 x, 16 y in framebuffer pixels.
 */
public final class Protocol {
    public static final int FRAME_MAGIC = 0x46343253;
    public static final int TOUCH_MAGIC = 0x54343253;
    public static final int FORMAT_XR24 = 0x34325258;
    public static final int VERSION = 1;
    public static final int HEADER_BYTES = 48;
    public static final int TOUCH_BYTES = 20;
    public static final int SLOTS = 10;
    public static final int MAX_DIMENSION = 4096; /* bounds the per-frame allocation to 64 MiB */

    private Protocol() {}

    public static final class Header {
        public final int width, height, x, y, w, h, payloadBytes;
        public final long seq;

        Header(int width, int height, long seq, int x, int y, int w, int h, int payloadBytes) {
            this.width = width; this.height = height; this.seq = seq;
            this.x = x; this.y = y; this.w = w; this.h = h; this.payloadBytes = payloadBytes;
        }
    }

    static int le32(byte[] b, int offset) {
        return (b[offset] & 0xff) | (b[offset + 1] & 0xff) << 8 | (b[offset + 2] & 0xff) << 16 | (b[offset + 3] & 0xff) << 24;
    }

    static void put32(byte[] b, int offset, int value) {
        for (int i = 0; i < 4; i++) b[offset + i] = (byte) (value >>> (8 * i));
    }

    /** Decodes and bounds-checks a frame header; never trusts a field before it is checked. */
    public static Header decodeHeader(byte[] b) throws IOException {
        if (b.length != HEADER_BYTES) throw new IOException("header length " + b.length);
        if (le32(b, 0) != FRAME_MAGIC) throw new IOException("bad frame magic");
        if (le32(b, 4) != VERSION) throw new IOException("unsupported version " + le32(b, 4));
        if (le32(b, 40) != FORMAT_XR24) throw new IOException("unsupported format");
        long width = le32(b, 8) & 0xffffffffL, height = le32(b, 12) & 0xffffffffL;
        long x = le32(b, 24) & 0xffffffffL, y = le32(b, 28) & 0xffffffffL;
        long w = le32(b, 32) & 0xffffffffL, h = le32(b, 36) & 0xffffffffL;
        long payload = le32(b, 44) & 0xffffffffL;
        long seq = (le32(b, 16) & 0xffffffffL) | (long) le32(b, 20) << 32;
        if (width < 1 || height < 1 || width > MAX_DIMENSION || height > MAX_DIMENSION)
            throw new IOException("bad frame size " + width + "x" + height);
        if (w < 1 || h < 1 || x + w > width || y + h > height) throw new IOException("rectangle outside the frame");
        if (payload != w * h * 4) throw new IOException("payload " + payload + " != w*h*4");
        return new Header((int) width, (int) height, seq, (int) x, (int) y, (int) w, (int) h, (int) payload);
    }

    /** Copies an XR24 rectangle into an ARGB framebuffer of header.width*header.height ints. */
    public static void apply(int[] framebuffer, Header header, byte[] payload) {
        if (framebuffer.length != header.width * header.height || payload.length != header.payloadBytes)
            throw new IllegalArgumentException("buffer sizes do not match the header");
        int src = 0;
        for (int row = 0; row < header.h; row++) {
            int dst = (header.y + row) * header.width + header.x;
            for (int col = 0; col < header.w; col++, src += 4)
                framebuffer[dst + col] = 0xff000000 | (payload[src + 2] & 0xff) << 16 | (payload[src + 1] & 0xff) << 8 | (payload[src] & 0xff);
        }
    }

    public static byte[] encodeTouch(int slot, int trackingId, int x, int y) {
        if (slot < 0 || slot >= SLOTS || trackingId < -1 || x < 0 || y < 0)
            throw new IllegalArgumentException("touch outside the protocol range");
        byte[] b = new byte[TOUCH_BYTES];
        put32(b, 0, TOUCH_MAGIC);
        put32(b, 4, slot);
        put32(b, 8, trackingId);
        put32(b, 12, x);
        put32(b, 16, y);
        return b;
    }
}
