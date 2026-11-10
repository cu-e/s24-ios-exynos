package dev.egor.s24vmmviewer;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Rect;
import android.view.MotionEvent;
import android.view.View;

/** Draws the guest framebuffer scaled to fit and turns touches into framebuffer coordinates. */
final class FrameView extends View {
    interface TouchSink {
        void touch(int slot, int trackingId, int x, int y);
    }

    private final Object lock = new Object();
    private final Paint text = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Rect dst = new Rect();
    private Bitmap bitmap;
    private int[] framebuffer;
    private String status = "";
    private TouchSink sink;

    FrameView(Context context) {
        super(context);
        text.setColor(Color.WHITE);
        text.setTextSize(36f);
        setBackgroundColor(Color.BLACK);
    }

    void setTouchSink(TouchSink sink) {
        this.sink = sink;
    }

    void setStatus(String status) {
        synchronized (lock) {
            this.status = status;
        }
        postInvalidate();
    }

    /** Called from the network thread with a decoded frame. */
    void frame(Protocol.Header header, byte[] payload) {
        synchronized (lock) {
            if (bitmap == null || bitmap.getWidth() != header.width || bitmap.getHeight() != header.height) {
                bitmap = Bitmap.createBitmap(header.width, header.height, Bitmap.Config.ARGB_8888);
                framebuffer = new int[header.width * header.height];
            }
            Protocol.apply(framebuffer, header, payload);
            int offset = header.y * header.width + header.x;
            bitmap.setPixels(framebuffer, offset, header.width, header.x, header.y, header.w, header.h);
        }
        postInvalidate();
    }

    @Override
    protected void onDraw(Canvas canvas) {
        synchronized (lock) {
            if (bitmap != null) {
                fit(bitmap.getWidth(), bitmap.getHeight());
                canvas.drawBitmap(bitmap, null, dst, null);
            }
            if (!status.isEmpty()) canvas.drawText(status, 24f, 60f, text);
        }
    }

    /** The centred, aspect-preserving destination rectangle for a w x h frame. */
    private void fit(int w, int h) {
        float scale = Math.min(getWidth() / (float) w, getHeight() / (float) h);
        int dw = Math.round(w * scale), dh = Math.round(h * scale);
        int left = (getWidth() - dw) / 2, top = (getHeight() - dh) / 2;
        dst.set(left, top, left + dw, top + dh);
    }

    @Override
    public boolean onTouchEvent(MotionEvent event) {
        TouchSink s = sink;
        int w, h;
        synchronized (lock) {
            if (bitmap == null || s == null) return true;
            w = bitmap.getWidth();
            h = bitmap.getHeight();
            fit(w, h);
        }
        int action = event.getActionMasked();
        if (action == MotionEvent.ACTION_CANCEL) {
            for (int i = 0; i < event.getPointerCount(); i++) lift(s, event.getPointerId(i));
            return true;
        }
        int index = event.getActionIndex();
        for (int i = 0; i < event.getPointerCount(); i++) {
            int id = event.getPointerId(i);
            if (id >= Protocol.SLOTS) continue;
            boolean up = (action == MotionEvent.ACTION_UP || action == MotionEvent.ACTION_POINTER_UP) && i == index;
            boolean moved = action == MotionEvent.ACTION_MOVE ||
                    ((action == MotionEvent.ACTION_DOWN || action == MotionEvent.ACTION_POINTER_DOWN) && i == index);
            if (up) {
                lift(s, id);
            } else if (moved) {
                int x = clamp((event.getX(i) - dst.left) * w / Math.max(1, dst.width()), w);
                int y = clamp((event.getY(i) - dst.top) * h / Math.max(1, dst.height()), h);
                s.touch(id, id, x, y);
            }
        }
        return true;
    }

    private static void lift(TouchSink s, int id) {
        if (id < Protocol.SLOTS) s.touch(id, -1, 0, 0);
    }

    private static int clamp(float value, int limit) {
        return Math.max(0, Math.min(limit - 1, (int) value));
    }
}
