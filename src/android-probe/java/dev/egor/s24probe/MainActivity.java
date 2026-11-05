package dev.egor.s24probe;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.AtomicFile;
import android.view.View;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import org.json.JSONObject;

public final class MainActivity extends Activity {
    static { System.loadLibrary("s24probe"); }
    private static native void reset();
    private static native void cancel();
    private static native String measure();
    private final Handler ui = new Handler(Looper.getMainLooper());
    private Button start, stop, save;
    private TextView status, detail;
    private boolean running = false, destroyed = false;
    private static final RunGate GATE = new RunGate();
    private static final String RESTART = "This test session requires a restart. Force stop this app in Android settings, then reopen.";
    private static final class Completed {
        final String json; final boolean storageFailed;
        Completed(String json, boolean storageFailed) { this.json = json; this.storageFailed = storageFailed; }
    }
    private static volatile Completed latest;
    private int generation = 0;
    private String lastReport = null;

    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
    private TextView text(String value, float size) {
        TextView view = new TextView(this);
        view.setText(value); view.setTextSize(size); view.setPadding(0, dp(8), 0, dp(8));
        return view;
    }
    private Button button(String value, LinearLayout layout) {
        Button view = new Button(this); view.setText(value); view.setAllCaps(false); view.setMinHeight(dp(48));
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2); params.setMargins(0, dp(8), 0, 0);
        layout.addView(view, params); return view;
    }
    @Override public void onCreate(Bundle state) {
        boolean dark = (getResources().getConfiguration().uiMode & android.content.res.Configuration.UI_MODE_NIGHT_MASK) == android.content.res.Configuration.UI_MODE_NIGHT_YES;
        setTheme(dark ? android.R.style.Theme_Material_NoActionBar : android.R.style.Theme_Material_Light_NoActionBar);
        super.onCreate(state);
        ScrollView scroll = new ScrollView(this);
        LinearLayout body = new LinearLayout(this); body.setOrientation(LinearLayout.VERTICAL);
        body.setPadding(dp(24), dp(16), dp(24), dp(24)); scroll.addView(body);
        body.addView(text("S24 Vulkan probe", 24));
        body.addView(text("Check a small image with the Android GPU driver. Results stay on this device until you save a report.", 16));
        status = text("Ready to test", 18); status.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE); body.addView(status);
        body.addView(text("256 × 256 pixels · opaque red · exact comparison", 16));
        start = button("Start test", body); stop = button("Stop", body); save = button("Save report", body);
        stop.setEnabled(false); save.setEnabled(false);
        detail = text("Run a test to see the GPU name and measured result.", 14); detail.setTextIsSelectable(true); body.addView(detail);
        body.addView(text("Stop prevents further work. A GPU driver failure can require restarting the phone.", 14));
        scroll.setOnApplyWindowInsetsListener((view, insets) -> {
            if (android.os.Build.VERSION.SDK_INT >= 30) {
                android.graphics.Insets bars = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
                view.setPadding(bars.left, bars.top, bars.right, bars.bottom);
            } else view.setPadding(insets.getSystemWindowInsetLeft(), insets.getSystemWindowInsetTop(), insets.getSystemWindowInsetRight(), insets.getSystemWindowInsetBottom());
            return insets;
        });
        setContentView(scroll); scroll.requestApplyInsets(); applySystemBarAppearance();
        start.setOnClickListener(view -> begin());
        stop.setOnClickListener(view -> requestStop());
        save.setOnClickListener(view -> {
            Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT); intent.setType("application/json");
            intent.addCategory(Intent.CATEGORY_OPENABLE); intent.putExtra(Intent.EXTRA_TITLE, "s24-vulkan-report.json");
            startActivityForResult(intent, 1);
        });
        // Restore only actual saved reports; opening the app never starts a GPU job.
        File existing = new File(getFilesDir(), "last-report.json");
        if (latest != null) showReport(latest, true);
        else if (existing.isFile()) try {
            lastReport = new String(java.nio.file.Files.readAllBytes(existing.toPath()), StandardCharsets.UTF_8);
            JSONObject report = new JSONObject(lastReport);
            detail.setText(lastReport); status.setText("Previous result: " + report.optString("outcome", "unknown")); save.setEnabled(true);
        } catch (Exception error) { status.setText("Saved report could not be read. Start a new test."); }
        start.setEnabled(!GATE.isPoisoned() && !GATE.isBusy());
        if (GATE.isPoisoned()) status.setText(RESTART);
    }
    private void showReport(Completed result, boolean previous) {
        lastReport = result.json; detail.setText(result.json); save.setEnabled(true);
        try {
            JSONObject data = new JSONObject(result.json);
            String message = GATE.isPoisoned() ? RESTART : (previous ? "Previous result: " : "Result: ") + data.optString("outcome", "unknown");
            if (result.storageFailed) message += "\nReport could not be stored privately. Save report to export this result before ending the app process.";
            status.setText(message);
        } catch (Exception error) { status.setText("Report could not be read."); }
    }
    private void begin() {
        if (running || !GATE.tryStart()) return;
        running = true; final int current = ++generation; reset(); start.setEnabled(false); stop.setEnabled(true); save.setEnabled(false);
        status.setText("Testing image readback…");
        ui.postDelayed(() -> { if (running && current == generation && !destroyed) { cancel(); status.setText("Test exceeded its time limit. If it does not return, force stop this app in Android settings."); } }, 5000);
        new Thread(() -> {
            String report;
            try {
                JSONObject data = new JSONObject(measure());
                data.put("environment", "android-userland"); data.put("application_version", "0.1.0");
                data.put("source_commit", BuildInfo.COMMIT); data.put("source_sha256", BuildInfo.SOURCE_SHA256);
                data.put("recorded_at", java.time.Instant.now().toString());
                report = data.toString(2);
            } catch (Exception error) {
                report = "{\"schema_version\":1,\"outcome\":\"fail\",\"requires_process_restart\":true,\"error\":" + JSONObject.quote(error.toString()) + "}";
            }
            final String completed = report;
            boolean poison = false;
            try { poison = new JSONObject(completed).optBoolean("requires_process_restart", false); }
            catch (Exception ignored) { poison = true; }
            // Storage failure must not replace a genuine measurement or poison the GPU session.
            AtomicFile file = new AtomicFile(new File(getFilesDir(), "last-report.json"));
            FileOutputStream stream = null; boolean storageFailed = false;
            try {
                stream = file.startWrite(); stream.write(completed.getBytes(StandardCharsets.UTF_8)); file.finishWrite(stream); stream = null;
                // AtomicFile logs some commit failures without throwing. Verify
                // the committed bytes before claiming private storage succeeded.
                String stored = new String(java.nio.file.Files.readAllBytes(file.getBaseFile().toPath()), StandardCharsets.UTF_8);
                if (!completed.equals(stored)) throw new java.io.IOException("Stored report does not match the measured result");
            }
            catch (Exception error) { if (stream != null) file.failWrite(stream); storageFailed = true; }
            final Completed result = new Completed(completed, storageFailed);
            latest = result;
            GATE.finish(poison);
            ui.post(() -> {
                running = false; stop.setEnabled(false);
                if (destroyed) return;
                showReport(result, false);
                start.setEnabled(!GATE.isPoisoned());
            });
        }, "vulkan-probe").start();
    }
    private void requestStop() { if (running) { cancel(); stop.setEnabled(false); status.setText("Stopping after the submitted image completes…"); } }
    private void applySystemBarAppearance() {
        boolean dark = (getResources().getConfiguration().uiMode & android.content.res.Configuration.UI_MODE_NIGHT_MASK) == android.content.res.Configuration.UI_MODE_NIGHT_YES;
        View decor = getWindow().getDecorView();
        if (android.os.Build.VERSION.SDK_INT >= 30) {
            WindowInsetsController controller = decor.getWindowInsetsController();
            if (controller != null) {
                int lightBackground = WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS | WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS;
                controller.setSystemBarsAppearance(dark ? 0 : lightBackground, lightBackground);
                return;
            }
        }
        int lightBackground = View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
        int flags = decor.getSystemUiVisibility() & ~lightBackground;
        decor.setSystemUiVisibility(dark ? flags : flags | lightBackground);
    }
    @Override public void onWindowFocusChanged(boolean focused) {
        super.onWindowFocusChanged(focused);
        if (focused) applySystemBarAppearance();
    }
    @Override protected void onResume() {
        super.onResume();
        if (!running && GATE.isBusy()) {
            start.setEnabled(false); status.setText("A previous test is stopping…");
            ui.postDelayed(new Runnable() { public void run() {
                if (destroyed) return;
                if (GATE.isBusy()) { ui.postDelayed(this, 100); return; }
                start.setEnabled(!GATE.isPoisoned());
                if (latest != null) showReport(latest, true);
                else status.setText(GATE.isPoisoned() ? RESTART : "Previous test ended.");
            } }, 100);
        }
    }
    @Override protected void onPause() { requestStop(); super.onPause(); }
    @Override protected void onDestroy() { destroyed = true; cancel(); ui.removeCallbacksAndMessages(null); super.onDestroy(); }
    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request == 1 && result == RESULT_OK && data != null && lastReport != null) {
            Uri uri = data.getData();
            try (OutputStream stream = getContentResolver().openOutputStream(uri)) {
                if (stream == null) throw new java.io.IOException("No output stream");
                stream.write(lastReport.getBytes(StandardCharsets.UTF_8)); status.setText("Report saved");
            } catch (Exception error) { status.setText("Report could not be saved. Choose another location."); }
        }
    }
}
