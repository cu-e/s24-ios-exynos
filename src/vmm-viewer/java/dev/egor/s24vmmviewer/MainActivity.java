package dev.egor.s24vmmviewer;

import android.app.Activity;
import android.os.Bundle;

import java.io.DataInputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

/**
 * Connects to s24vmm's display port on 127.0.0.1 (default 5824, or the "port" int extra), shows the
 * frames it streams and sends touches back. Loopback only; the app has no other network use.
 */
public final class MainActivity extends Activity {
    private static final int DEFAULT_PORT = 5824;
    private final BlockingQueue<byte[]> touches = new ArrayBlockingQueue<byte[]>(512);
    private volatile boolean running;
    private volatile Socket socket;
    private Thread reader;
    private FrameView view;
    private int port;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        port = getIntent().getIntExtra("port", DEFAULT_PORT);
        if (port < 1 || port > 65535) port = DEFAULT_PORT;
        view = new FrameView(this);
        view.setTouchSink(new FrameView.TouchSink() {
            @Override
            public void touch(int slot, int trackingId, int x, int y) {
                touches.offer(Protocol.encodeTouch(slot, trackingId, x, y)); /* drop when the VMM stops reading */
            }
        });
        setContentView(view);
    }

    @Override
    protected void onStart() {
        super.onStart();
        running = true;
        reader = new Thread(new Runnable() {
            @Override
            public void run() {
                loop();
            }
        }, "s24vmm-frames");
        reader.start();
    }

    @Override
    protected void onStop() {
        running = false;
        closeSocket();
        if (reader != null) reader.interrupt();
        super.onStop();
    }

    private void closeSocket() {
        Socket s = socket;
        if (s != null) {
            try {
                s.close();
            } catch (IOException ignored) {
            }
        }
    }

    private void loop() {
        while (running) {
            view.setStatus("connecting to 127.0.0.1:" + port);
            try (Socket s = new Socket()) {
                socket = s;
                s.setTcpNoDelay(true);
                s.connect(new InetSocketAddress(InetAddress.getByName("127.0.0.1"), port), 1000);
                touches.clear();
                Thread writer = startWriter(s.getOutputStream());
                try {
                    stream(new DataInputStream(s.getInputStream()));
                } finally {
                    writer.interrupt();
                }
            } catch (IOException | RuntimeException error) {
                view.setStatus("disconnected: " + error.getMessage());
            }
            socket = null;
            try {
                Thread.sleep(500);
            } catch (InterruptedException e) {
                return;
            }
        }
    }

    private Thread startWriter(final OutputStream out) {
        Thread writer = new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    while (running) out.write(touches.take());
                } catch (InterruptedException | IOException ignored) {
                }
            }
        }, "s24vmm-touches");
        writer.start();
        return writer;
    }

    private void stream(DataInputStream in) throws IOException {
        byte[] header = new byte[Protocol.HEADER_BYTES];
        long frames = 0;
        while (running) {
            in.readFully(header);
            Protocol.Header h = Protocol.decodeHeader(header);
            byte[] payload = new byte[h.payloadBytes];
            in.readFully(payload);
            view.frame(h, payload);
            if (++frames == 1) view.setStatus("");
        }
    }
}
