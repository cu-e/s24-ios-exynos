package dev.egor.s24probe;

/** Process-wide admission. Activity recreation never owns the native worker's lifetime. */
final class RunGate {
    private boolean busy = false;
    private boolean poisoned = false;
    synchronized boolean tryStart() {
        if (busy || poisoned) return false;
        busy = true; return true;
    }
    synchronized void finish(boolean requiresRestart) {
        poisoned |= requiresRestart; busy = false;
    }
    synchronized boolean isBusy() { return busy; }
    synchronized boolean isPoisoned() { return poisoned; }
}
