import dev.egor.s24vmmviewer.Protocol;

import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;

/**
 * Host JVM test of the viewer protocol. args[0]: frames written by the C encoder (test/wire.c);
 * args[1]: touch messages to write for the C decoder. Prints one JSON line with the counts.
 */
public final class ProtocolTest {
    private static int checks, failures;

    private static void check(boolean ok, String what) {
        checks++;
        if (!ok) {
            failures++;
            System.err.println("FAIL " + what);
        }
    }

    private static int pixel(int base, int index) { /* XR24 bytes B,G,R,X starting at base+4*index */
        int b = (base + 4 * index) & 0xff, g = (base + 4 * index + 1) & 0xff, r = (base + 4 * index + 2) & 0xff;
        return 0xff000000 | r << 16 | g << 8 | b;
    }

    private static byte[] header(int magic, int version, int width, int height, long seq, int x, int y, int w, int h, int format, int payload) {
        byte[] b = new byte[Protocol.HEADER_BYTES];
        int[] words = {magic, version, width, height, (int) seq, (int) (seq >>> 32), x, y, w, h, format, payload};
        for (int i = 0; i < words.length; i++)
            for (int k = 0; k < 4; k++) b[4 * i + k] = (byte) (words[i] >>> (8 * k));
        return b;
    }

    private static boolean rejects(byte[] b) {
        try {
            Protocol.decodeHeader(b);
            return false;
        } catch (IOException expected) {
            return true;
        }
    }

    public static void main(String[] args) throws IOException {
        int[] fb = new int[5 * 3];
        try (DataInputStream in = new DataInputStream(new FileInputStream(args[0]))) {
            long[] seqs = {7, 8, 0x100000009L};
            int[][] rects = {{0, 0, 5, 3}, {1, 1, 2, 2}, {4, 2, 1, 1}};
            int[] bases = {0x10, 0xa0, 0xf0};
            for (int frame = 0; frame < 3; frame++) {
                byte[] hb = new byte[Protocol.HEADER_BYTES];
                in.readFully(hb);
                Protocol.Header h = Protocol.decodeHeader(hb);
                int[] r = rects[frame];
                check(h.width == 5 && h.height == 3 && h.seq == seqs[frame], "frame " + frame + " size/seq");
                check(h.x == r[0] && h.y == r[1] && h.w == r[2] && h.h == r[3] && h.payloadBytes == r[2] * r[3] * 4, "frame " + frame + " rectangle");
                byte[] payload = new byte[h.payloadBytes];
                in.readFully(payload);
                Protocol.apply(fb, h, payload);
            }
            check(in.read() == -1, "no trailing bytes");
        }
        /* expected framebuffer: frame 0 everywhere, frame 1 over (1..2, 1..2), frame 2 at (4,2) */
        for (int y = 0; y < 3; y++)
            for (int x = 0; x < 5; x++) {
                int expected = pixel(0x10, y * 5 + x);
                if (x >= 1 && x <= 2 && y >= 1 && y <= 2) expected = pixel(0xa0, (y - 1) * 2 + (x - 1));
                if (x == 4 && y == 2) expected = pixel(0xf0, 0);
                check(fb[y * 5 + x] == expected, "pixel " + x + "," + y);
            }

        int f = Protocol.FRAME_MAGIC, v = Protocol.VERSION, xr = Protocol.FORMAT_XR24;
        check(!rejects(header(f, v, 5, 3, 1, 0, 0, 5, 3, xr, 60)), "valid header accepted");
        check(rejects(header(0x46343254, v, 5, 3, 1, 0, 0, 5, 3, xr, 60)), "bad magic");
        check(rejects(header(f, 2, 5, 3, 1, 0, 0, 5, 3, xr, 60)), "bad version");
        check(rejects(header(f, v, 5, 3, 1, 0, 0, 5, 3, 0x34324241, 60)), "bad format");
        check(rejects(header(f, v, 0, 3, 1, 0, 0, 0, 3, xr, 0)), "zero width");
        check(rejects(header(f, v, 4097, 3, 1, 0, 0, 1, 1, xr, 4)), "width above limit");
        check(rejects(header(f, v, 5, 3, 1, 4, 0, 2, 1, xr, 8)), "rectangle past the right edge");
        check(rejects(header(f, v, 5, 3, 1, 0, 0, 0, 1, xr, 0)), "empty rectangle");
        check(rejects(header(f, v, 5, 3, 1, -1, 0, 2, 1, xr, 8)), "x wraps (0xffffffff)");
        check(rejects(header(f, v, 5, 3, 1, 0, 0, 5, 3, xr, 59)), "short payload");
        check(rejects(header(f, v, 4096, 4096, 1, 0, 0, 4096, 4096, xr, 0)), "payload field disagrees with w*h*4");
        check(rejects(new byte[47]), "short header");

        byte[] t = Protocol.encodeTouch(3, 42, 1124, 2435);
        check(t.length == 20 && (t[0] & 0xff) == 0x53 && (t[1] & 0xff) == 0x32 && (t[2] & 0xff) == 0x34 && (t[3] & 0xff) == 0x54, "touch magic S24T");
        int[][] bad = {{10, 0, 0, 0}, {-1, 0, 0, 0}, {0, -2, 0, 0}, {0, 0, -1, 0}};
        for (int[] b : bad) {
            boolean threw = false;
            try {
                Protocol.encodeTouch(b[0], b[1], b[2], b[3]);
            } catch (IllegalArgumentException expected) {
                threw = true;
            }
            check(threw, "encodeTouch rejects " + b[0] + "," + b[1]);
        }

        ByteArrayOutputStream touches = new ByteArrayOutputStream();
        touches.write(Protocol.encodeTouch(0, 0, 10, 20));
        touches.write(Protocol.encodeTouch(9, 65535, 1124, 2435));
        touches.write(Protocol.encodeTouch(0, -1, 0, 0));
        byte[] slot10 = Protocol.encodeTouch(0, 1, 2, 3);
        slot10[4] = 10; /* a raw slot-10 message the C decoder must reject */
        touches.write(slot10);
        try (FileOutputStream out = new FileOutputStream(args[1])) {
            out.write(touches.toByteArray());
        }
        System.out.println("{\"checks\":" + checks + ",\"failures\":" + failures + "}");
        System.exit(failures == 0 ? 0 : 1);
    }
}
