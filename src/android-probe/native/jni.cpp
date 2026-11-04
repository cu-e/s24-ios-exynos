#include "probe.h"
#include <jni.h>

static std::atomic_bool cancelled{false};
extern "C" JNIEXPORT void JNICALL Java_dev_egor_s24probe_MainActivity_reset(JNIEnv *, jclass) { cancelled.store(false); }
extern "C" JNIEXPORT void JNICALL Java_dev_egor_s24probe_MainActivity_cancel(JNIEnv *, jclass) { cancelled.store(true); }
extern "C" JNIEXPORT jstring JNICALL Java_dev_egor_s24probe_MainActivity_measure(JNIEnv *env, jclass) {
    const auto result = run_probe(cancelled).json();
    return env->NewStringUTF(result.c_str());
}
