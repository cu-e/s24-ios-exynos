package dev.egor.s24probe.qualifier;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.ComponentName;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.Rect;
import android.os.Build;
import android.os.Bundle;
import android.os.SystemClock;
import android.os.ParcelFileDescriptor;
import android.view.InputDevice;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowInsetsController;
import android.view.accessibility.AccessibilityNodeInfo;
import android.accessibilityservice.AccessibilityServiceInfo;
import android.widget.TextView;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import org.json.JSONArray;
import org.json.JSONObject;

/** Emulator-only instrumentation of the unchanged target APK. Not part of its build. */
public final class Qualifier extends Instrumentation {
    private static final String PKG="dev.egor.s24probe";
    private volatile Activity current;
    private Bundle arguments;
    private JSONObject report=new JSONObject();
    @Override public void onCreate(Bundle args) { arguments=args; super.onCreate(args); start(); }
    @Override public void callActivityOnCreate(Activity a, Bundle b) { current=a; super.callActivityOnCreate(a,b); }
    @Override public void callActivityOnResume(Activity a) { current=a; super.callActivityOnResume(a); }
    private void require(boolean ok,String message) { if (!ok) throw new IllegalStateException(message); }
    private Object field(String name) throws Exception {
        Field f=current.getClass().getDeclaredField(name);f.setAccessible(true);return f.get(current);
    }
    private String status() {
        final String[] text={null};runOnMainSync(()->{try{text[0]=((TextView)field("status")).getText().toString();}catch(Exception e){throw new RuntimeException(e);}});return text[0];
    }
    private String reportText() {
        final String[] text={null};runOnMainSync(()->{try{text[0]=(String)field("lastReport");}catch(Exception e){throw new RuntimeException(e);}});return text[0];
    }
    private boolean enabled(String name) {
        final boolean[] value={false};runOnMainSync(()->{try{value[0]=((View)field(name)).isEnabled();}catch(Exception e){throw new RuntimeException(e);}});return value[0];
    }
    private void awaitStatus(String fragment) {
        long end=SystemClock.uptimeMillis()+20000;
        while(SystemClock.uptimeMillis()<end) { if(status().contains(fragment))return;SystemClock.sleep(100); }
        throw new IllegalStateException("Missing status "+fragment+"; actual: "+status());
    }
    private void click(String field) throws Exception {
        final int[] at=new int[2];
        runOnMainSync(()->{try{
            View v=(View)field(field);require(v.isEnabled() && current.hasWindowFocus(),"Control unavailable: "+field);
            v.getLocationOnScreen(at);at[0]+=v.getWidth()/2;at[1]+=v.getHeight()/2;
        }catch(Exception e){throw new RuntimeException(e);}});
        long now=SystemClock.uptimeMillis();
        MotionEvent down=MotionEvent.obtain(now,now,MotionEvent.ACTION_DOWN,at[0],at[1],0);down.setSource(InputDevice.SOURCE_TOUCHSCREEN);
        MotionEvent up=MotionEvent.obtain(now,now+40,MotionEvent.ACTION_UP,at[0],at[1],0);up.setSource(InputDevice.SOURCE_TOUCHSCREEN);
        sendPointerSync(down);SystemClock.sleep(40);sendPointerSync(up);down.recycle();up.recycle();
    }
    private void recreate() {
        Activity before=current;runOnMainSync(before::recreate);
        awaitRecreated(before);
    }
    private void awaitRecreated(Activity before) {
        long end=SystemClock.uptimeMillis()+15000;
        while(current==before && SystemClock.uptimeMillis()<end)SystemClock.sleep(100);
        require(current!=before,"Activity did not recreate");waitForIdleSync();
    }
    private void write(String name,String text) throws Exception {
        try(FileOutputStream s=new FileOutputStream(new File(getTargetContext().getFilesDir(),name))){s.write(text.getBytes(StandardCharsets.UTF_8));}
    }
    private void screenshot(String name) throws Exception {
        waitForIdleSync();SystemClock.sleep(400);
        Bitmap b=getUiAutomation().takeScreenshot();require(b!=null,"Missing real screen capture");
        try(FileOutputStream s=new FileOutputStream(new File(getTargetContext().getFilesDir(),name))){require(b.compress(Bitmap.CompressFormat.PNG,100,s),"Capture encoding failed");}finally{b.recycle();}
    }
    private void collect(AccessibilityNodeInfo n,JSONArray list,int depth) throws Exception {
        if(n==null || depth>30 || list.length()>300)return;
        Rect r=new Rect();n.getBoundsInScreen(r);
        JSONObject item=new JSONObject();item.put("class",String.valueOf(n.getClassName()));item.put("text",String.valueOf(n.getText()));item.put("description",String.valueOf(n.getContentDescription()));
        item.put("enabled",n.isEnabled());item.put("clickable",n.isClickable());item.put("focusable",n.isFocusable());item.put("bounds",r.flattenToString());list.put(item);
        for(int i=0;i<n.getChildCount();i++){AccessibilityNodeInfo child=n.getChild(i);collect(child,list,depth+1);if(child!=null)child.recycle();}
    }
    private void assessControls() throws Exception {
        JSONArray controls=new JSONArray();
        for(String name:new String[]{"start","stop","save"}) {
            final JSONObject item=new JSONObject();
            runOnMainSync(()->{try{
                TextView v=(TextView)field(name);float density=current.getResources().getDisplayMetrics().density;
                item.put("name",name);item.put("label",v.getText().toString());item.put("enabled",v.isEnabled());item.put("height_dp",v.getHeight()/density);item.put("width_dp",v.getWidth()/density);item.put("clickable",v.isClickable());
            }catch(Exception e){throw new RuntimeException(e);}});controls.put(item);
        }
        report.put("live_controls",controls);JSONArray nodes=new JSONArray();AccessibilityNodeInfo root=null;
        if(Build.VERSION.SDK_INT>=30)runOnMainSync(()->{
            try {
                WindowInsetsController c=current.getWindow().getDecorView().getWindowInsetsController();require(c!=null,"Missing attached system-bars controller");
                int mask=WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS|WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS;
                boolean dark=(current.getResources().getConfiguration().uiMode&0x30)==0x20;
                int actual=c.getSystemBarsAppearance()&mask;report.put("system_bar_appearance",actual);report.put("dark_theme",dark);
                require(actual==(dark?0:mask),"System-bar icon appearance does not match actual theme");
            }catch(Exception e){throw new RuntimeException(e);}
        });
        long end=SystemClock.uptimeMillis()+5000;
        while(root==null && SystemClock.uptimeMillis()<end){root=getUiAutomation().getRootInActiveWindow();if(root==null)SystemClock.sleep(100);}
        collect(root,nodes,0);if(root!=null)root.recycle();report.put("accessibility_nodes",nodes);
        report.put("talkback_spoken_behavior_qualified",false);
    }
    private JSONObject measurement() throws Exception {
        JSONObject r=new JSONObject(reportText());
        require(r.getString("outcome").equals("pass") && r.getInt("compared_pixels")==65536 && r.getInt("mismatched_pixels")==0,"Genuine fixture did not pass");
        require(r.getString("source_sha256").equals(arguments.getString("source_sha256")),"Runtime source mismatch");return r;
    }
    private static String digest(File file) throws Exception {
        MessageDigest d=MessageDigest.getInstance("SHA-256");try(FileInputStream in=new FileInputStream(file)){byte[] b=new byte[65536];int n;while((n=in.read(b))!=-1)d.update(b,0,n);}
        StringBuilder s=new StringBuilder();for(byte b:d.digest())s.append(String.format("%02x",b&255));return s.toString();
    }
    private boolean clickSave(AccessibilityNodeInfo n) {
        if(n==null)return false;
        CharSequence t=n.getText();
        if(t!=null && t.toString().equalsIgnoreCase("Save") && n.isEnabled() && n.isClickable())return n.performAction(AccessibilityNodeInfo.ACTION_CLICK);
        for(int i=0;i<n.getChildCount();i++){AccessibilityNodeInfo c=n.getChild(i);boolean found=clickSave(c);if(c!=null)c.recycle();if(found)return true;}
        return false;
    }
    @Override public void onStart() {
        String mode=arguments.getString("mode","run");int result=Activity.RESULT_CANCELED;
        try {
            require(Build.HARDWARE.contains("ranchu") || Build.HARDWARE.contains("goldfish"),"Qualification only allowed in the host emulator");
            String sha=digest(new File(getTargetContext().getApplicationInfo().sourceDir));require(sha.equals(arguments.getString("apk_sha256")),"Installed APK digest mismatch");
            report.put("mode",mode);report.put("target_apk_sha256",sha);report.put("primary_device",false);
            AccessibilityServiceInfo service=getUiAutomation().getServiceInfo();
            service.flags|=AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS|AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS|AccessibilityServiceInfo.FLAG_INCLUDE_NOT_IMPORTANT_VIEWS;
            getUiAutomation().setServiceInfo(service);
            Intent intent=new Intent().setComponent(new ComponentName(PKG,PKG+".MainActivity")).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            current=startActivitySync(intent);waitForIdleSync();SystemClock.sleep(500);
            if(mode.equals("restart")) {
                report.put("fault_injection","Host-only reflection sets idle RunGate poison; no GPU hang was induced");
                Object gate=field("GATE");Method finish=gate.getClass().getDeclaredMethod("finish",boolean.class);finish.setAccessible(true);finish.invoke(gate,true);
                recreate();awaitStatus("Force stop this app");
                require(!enabled("start"),"Restart-required Start remained enabled");
            } else if(mode.equals("theme")) {
                String beforeReport=reportText();Activity before=current;
                boolean dark=(current.getResources().getConfiguration().uiMode & 0x30)==0x20;
                String target=dark?"no":"yes";
                try(ParcelFileDescriptor.AutoCloseInputStream stream=new ParcelFileDescriptor.AutoCloseInputStream(getUiAutomation().executeShellCommand("cmd uimode night "+target))){while(stream.read()!=-1){}}
                long end=SystemClock.uptimeMillis()+15000;while(current==before && SystemClock.uptimeMillis()<end)SystemClock.sleep(100);
                require(current!=before,"Night mode did not recreate the actual Activity");waitForIdleSync();
                require(((current.getResources().getConfiguration().uiMode & 0x30)==0x20)!=dark,"Actual night configuration did not change");
                if(beforeReport!=null)require(beforeReport.equals(reportText()),"Live theme change lost the genuine result");
                report.put("live_theme_recreated",true);report.put("target_night_mode",target);
            } else if(mode.equals("storage") || mode.equals("commit")) {
                String fault=mode.equals("commit")?"last-report.json":"last-report.json.new";
                require(new File(getTargetContext().getFilesDir(),fault+"/blocker").isFile(),"Missing explicit host-created storage fault");
                report.put("storage_fault",mode.equals("commit")?"nonempty base directory blocks AtomicFile commit":"nonempty .new directory blocks startWrite");
                click("start");long end=SystemClock.uptimeMillis()+20000;
                while(reportText()==null && SystemClock.uptimeMillis()<end)SystemClock.sleep(100);
                JSONObject measured=measurement();report.put("measurement",measured);awaitStatus("Report could not be stored privately");
                require(enabled("start") && enabled("save"),"Storage fault poisoned GPU or lost export");
                recreate();awaitStatus("Report could not be stored privately");require(measurement().toString().equals(measured.toString()),"Recreation lost genuine in-memory report");
                report.put("genuine_result_retained_after_recreate",true);
            } else if(mode.equals("lifecycle")) {
                Object gate=field("GATE");Method busy=gate.getClass().getDeclaredMethod("isBusy");busy.setAccessible(true);
                View start=(View)field("start");Activity before=current;final boolean[] observed={false};
                // Trigger the real listener on its UI thread, then observe the
                // actual gate before dispatch latency lets a short job finish.
                // Native work is genuine; no gate state or result is injected.
                runOnMainSync(()->{try{start.performClick();observed[0]=(Boolean)busy.invoke(gate);before.recreate();}catch(Exception e){throw new RuntimeException(e);}});
                report.put("lifecycle_trigger","Actual Start listener invoked on main thread, not an external pointer event");
                report.put("gate_busy_at_recreate",observed[0]);require(observed[0],"No actual worker overlap observed");
                awaitRecreated(before);long end=SystemClock.uptimeMillis()+15000;
                while((!enabled("start") || reportText()==null) && SystemClock.uptimeMillis()<end)SystemClock.sleep(100);
                require(enabled("start"),"Previous worker did not retire without a restart");
                String first=reportText();require(first!=null,"Recreated Activity lost actual first result after UI-thread observation deadline");report.put("first_measurement",new JSONObject(first));
                click("start");awaitStatus("Result: pass");report.put("measurement",measurement());report.put("new_worker_after_retirement",true);
            } else if(mode.equals("run") || mode.equals("export")) {
                click("start");awaitStatus("Result: pass");report.put("measurement",measurement());
                if(mode.equals("export")) {
                    click("save");long end=SystemClock.uptimeMillis()+30000;boolean saved=false;
                    while(!saved && SystemClock.uptimeMillis()<end) {
                        AccessibilityNodeInfo root=getUiAutomation().getRootInActiveWindow();
                        if(root!=null && !PKG.contentEquals(root.getPackageName()==null?"":root.getPackageName())) {
                            JSONArray nodes=new JSONArray();collect(root,nodes,0);report.put("picker_accessibility_nodes",nodes);
                            saved=clickSave(root);
                        }
                        if(root!=null)root.recycle();if(!saved)SystemClock.sleep(200);
                    }
                    require(saved,"No semantic document-picker Save control within30seconds");
                    awaitStatus("Report saved");report.put("system_document_picker_saved",true);
                }
            } else require(mode.equals("initial"),"Unknown qualification mode");
            report.put("status",status());assessControls();screenshot("qualifier-"+mode+".png");report.put("outcome","pass");result=Activity.RESULT_OK;
        } catch(Throwable error) {
            try{report.put("outcome","fail");report.put("error",error.toString());report.put("actual_status",status());screenshot("qualifier-"+mode+".png");}catch(Throwable ignored){}
        }
        try{write("qualifier-"+mode+".json",report.toString(2));}catch(Exception ignored){}
        Bundle results=new Bundle();results.putString("qualification",report.toString());finish(result,results);
    }
}
