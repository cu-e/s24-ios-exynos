/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Host test for module/s5e9945_reset.c against a PMU register-file model. The model is a plain array; it logs every
 * access, barrier and wait in order, and can make registers ignore writes (stuck bits) or change on write. It models
 * nothing about the real PMU (no reset happens); it checks the sequence, the values, the verify/abort rules and that
 * nothing else is touched. Exit status 0 only if every check passes. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#define PMU_WORDS 0x4000u
static uint32_t pmu[PMU_WORDS];
static uint32_t stuck[PMU_WORDS];      /* bits that keep their old value on write */
static uint32_t force_or[PMU_WORDS];   /* bits the "hardware" sets on every write */
struct ev { char k; uint32_t off, val; };
static struct ev lg[256];
static unsigned nlg, g_wait;

static void rec(char k, uint32_t off, uint32_t val) { if (nlg < 256) { lg[nlg].k = k; lg[nlg].off = off; lg[nlg].val = val; nlg++; } }
static uint32_t model_r(volatile const uint32_t *a) {
    uint32_t i = (uint32_t)((const uint32_t *)a - pmu);
    if (i >= PMU_WORDS) { fprintf(stderr, "FAIL access outside the model\n"); exit(3); }
    rec('R', i * 4, pmu[i]); return pmu[i];
}
static void model_w(volatile uint32_t *a, uint32_t v) {
    uint32_t i = (uint32_t)((uint32_t *)a - pmu);
    if (i >= PMU_WORDS) { fprintf(stderr, "FAIL access outside the model\n"); exit(3); }
    rec('W', i * 4, v);
    pmu[i] = ((pmu[i] & stuck[i]) | (v & ~stuck[i])) | force_or[i];
}
#define S5E_MMIO_R(a)    model_r((volatile const uint32_t *)(a))
#define S5E_MMIO_W(a, v) model_w((volatile uint32_t *)(a), (v))
#define S5E_BARRIER()    rec('B', 0, 0)
#define S5E_WAIT()       (g_wait++)
#include "s5e9945_reset.c"

static int fails;
#define CHECK(c, ...) do { if (!(c)) { fails++; printf("FAIL %s:%d: ", __func__, __LINE__); printf(__VA_ARGS__); printf("\n"); } } while (0)

static void reset_model(void) {
    memset(pmu, 0, sizeof pmu); memset(stuck, 0, sizeof stuck); memset(force_or, 0, sizeof force_or);
    nlg = 0; g_wait = 0;
    pmu[0xb8 / 4] = 0xaabbccdd; pmu[0xbc / 4] = 0x12345604; pmu[0x190 / 4] = 0x000000f5; /* mode bits 0 and 2 set (bit 0 as after `adb reboot recovery`), upper bits arbitrary */
    pmu[0x3c00 / 4] = 0; pmu[0x1244 / 4] = 0x5a5a5a5a; pmu[0x810 / 4] = 0x13572468;
}
static unsigned count(char k, int off) { unsigned n = 0; for (unsigned i = 0; i < nlg; i++) if (lg[i].k == k && (off < 0 || lg[i].off == (uint32_t)off)) n++; return n; }
static unsigned writes(void) { return count('W', -1); }
/* the ordered list of write offsets */
static int write_order(uint32_t *out, unsigned max) { unsigned n = 0; for (unsigned i = 0; i < nlg && n < max; i++) if (lg[i].k == 'W') out[n++] = lg[i].off; return (int)n; }
static void untouched_elsewhere(const char *who) {
    CHECK(pmu[0x1244 / 4] == 0x5a5a5a5a, "%s: watchdog route word changed", who);
    CHECK(pmu[0x810 / 4] == 0x13572468, "%s: SYSIP_DAT0 changed", who);
    for (unsigned i = 0; i < nlg; i++) if (lg[i].k == 'W' && lg[i].off != 0xb8 && lg[i].off != 0xbc && lg[i].off != 0x190 && lg[i].off != 0x3c00)
        CHECK(0, "%s: write to unexpected offset 0x%x", who, lg[i].off);
}

static void test_download_sequence(void) {
    reset_model();
    int r = s5e_reset_to((volatile uint32_t *)pmu, S5E_REASON_DOWNLOAD);
    CHECK(r == 0, "status %d", r);
    CHECK(pmu[0xb8 / 4] == 0xaa4eccdd, "INFORM2 0x%08x (byte 2 must become 0x4e, the rest kept)", pmu[0xb8 / 4]);
    CHECK(pmu[0xbc / 4] == 0x12345601, "INFORM3 0x%08x", pmu[0xbc / 4]);
    CHECK(pmu[0x190 / 4] == 0x000000f0, "reboot-cmd 0x%08x (all three mode bits must become 0, the rest kept)", pmu[0x190 / 4]);
    CHECK(pmu[0x3c00 / 4] == 2, "trigger word 0x%x", pmu[0x3c00 / 4]);
    uint32_t o[8]; int n = write_order(o, 8);
    CHECK(n == 4 && o[0] == 0xb8 && o[1] == 0xbc && o[2] == 0x190 && o[3] == 0x3c00, "write order/offsets wrong (n=%d)", n);
    CHECK(g_wait == 1, "wait called %u times", g_wait);
    untouched_elsewhere("download");
    /* exact event interleaving: each write is followed by a barrier, then a read-back of the same register (trigger: barrier only) */
    static const struct ev want[] = {
        {'R', 0xb8, 0}, {'W', 0xb8, 0xaa4eccdd}, {'B', 0, 0}, {'R', 0xb8, 0},
        {'W', 0xbc, 0x12345601}, {'B', 0, 0}, {'R', 0xbc, 0},
        {'R', 0x190, 0}, {'W', 0x190, 0xf0}, {'B', 0, 0}, {'R', 0x190, 0},
        {'W', 0x3c00, 2}, {'B', 0, 0}};
    CHECK(nlg == sizeof want / sizeof want[0], "event count %u", nlg);
    for (unsigned i = 0; i < nlg && i < sizeof want / sizeof want[0]; i++)
        CHECK(lg[i].k == want[i].k && lg[i].off == want[i].off && (want[i].k != 'W' || lg[i].val == want[i].val),
              "event %u is %c 0x%x 0x%x", i, lg[i].k, lg[i].off, lg[i].val);
}
static void test_bootloader_mode(void) {
    reset_model();
    int r = s5e_reset_to((volatile uint32_t *)pmu, S5E_REASON_BOOTLOADER);
    CHECK(r == 0, "status %d", r);
    CHECK(pmu[0xbc / 4] == 0x1234560d, "INFORM3 0x%08x", pmu[0xbc / 4]);
    CHECK(pmu[0x190 / 4] == 0x000000f3, "reboot-cmd 0x%08x (mode 3 expected)", pmu[0x190 / 4]);
    CHECK(pmu[0x3c00 / 4] == 2, "trigger");
    untouched_elsewhere("bootloader");
}
static void test_normal_cancels_the_recovery_mode(void) {
    reset_model(); pmu[0x190 / 4] = 0x00000001;   /* mode left at RECOVERY by the reboot that started the run */
    int r = s5e_reset_to((volatile uint32_t *)pmu, S5E_REASON_NORMAL);
    CHECK(r == 0, "status %d", r);
    CHECK(pmu[0xbc / 4] == 0x12345600, "INFORM3 0x%08x", pmu[0xbc / 4]);
    CHECK((pmu[0x190 / 4] & 7) == 0, "mode 0x%x must be cleared to NORMAL", pmu[0x190 / 4] & 7);
    CHECK(pmu[0x3c00 / 4] == 2, "trigger");
}
static void test_only_three_reasons_are_accepted(void) {
    static const uint32_t bad[] = {0, 0x12345602 /*upload*/, 0x12345604 /*recovery*/, 0x12345609 /*fwup*/, 0x12345600u | 0x100,
                                   0x02345601, 0x12345601u | 0x80000000u, 0xabc00000 /*SET_*/, 0xa5600000 /*multicmd*/, 0xffffffff};
    for (unsigned i = 0; i < sizeof bad / sizeof bad[0]; i++) {
        reset_model();
        int r = s5e_reset_to((volatile uint32_t *)pmu, bad[i]);
        CHECK(r == S5E_RESET_EREASON, "reason 0x%x returned %d", bad[i], r);
        CHECK(nlg == 0, "reason 0x%x produced %u accesses (nothing may be touched)", bad[i], nlg);
        CHECK(g_wait == 0, "reason 0x%x waited", bad[i]);
    }
}
static void test_stuck_inform2_aborts_before_anything_else(void) {
    reset_model(); stuck[0xb8 / 4] = 0xffffffff;
    int r = s5e_reset_to((volatile uint32_t *)pmu, S5E_REASON_DOWNLOAD);
    CHECK(r == S5E_RESET_EVERIFY2, "status %d", r);
    CHECK(count('W', 0xbc) == 0 && count('W', 0x190) == 0 && count('W', 0x3c00) == 0, "wrote past a failed INFORM2");
    CHECK(pmu[0x3c00 / 4] == 0 && g_wait == 0, "triggered or waited after a failure");
}
static void test_stuck_inform3_aborts_before_the_trigger(void) {
    reset_model(); stuck[0xbc / 4] = 0xffffffff;
    int r = s5e_reset_to((volatile uint32_t *)pmu, S5E_REASON_DOWNLOAD);
    CHECK(r == S5E_RESET_EVERIFY3, "status %d", r);
    CHECK(count('W', 0x190) == 0 && count('W', 0x3c00) == 0, "wrote past a failed INFORM3");
    CHECK(pmu[0x3c00 / 4] == 0 && g_wait == 0, "triggered or waited after a failure");
}
static void test_stuck_mode_bits_abort_before_the_trigger(void) {
    reset_model(); stuck[0x190 / 4] = 0x7;     /* the mode bits ignore writes (they read 1, the write wants 0) */
    int r = s5e_reset_to((volatile uint32_t *)pmu, S5E_REASON_DOWNLOAD);
    CHECK(r == S5E_RESET_EVERIFYC, "status %d", r);
    CHECK(count('W', 0x3c00) == 0 && pmu[0x3c00 / 4] == 0 && g_wait == 0, "triggered after a failed mode write");
}
static void test_verify_compares_only_the_mode_bits(void) {
    reset_model(); force_or[0x190 / 4] = 0x100;    /* hardware sets an unrelated bit on every write */
    int r = s5e_reset_to((volatile uint32_t *)pmu, S5E_REASON_DOWNLOAD);
    CHECK(r == 0, "an unrelated bit changing must not abort (status %d)", r);
    CHECK(pmu[0x3c00 / 4] == 2, "no trigger");
}
static void test_verify_of_mode_bits_is_not_vacuous(void) {
    reset_model(); stuck[0x190 / 4] = 0x2;      /* only bit 1 is stuck, at its old value 0 */
    int r = s5e_reset_to((volatile uint32_t *)pmu, S5E_REASON_BOOTLOADER);   /* wants 3: bit 1 must be set but is stuck at 0 */
    CHECK(r == S5E_RESET_EVERIFYC, "a stuck mode bit with a wanted 1 must abort (status %d)", r);
}
static void test_snapshot_never_writes(void) {
    reset_model();
    struct s5e_reset_snapshot s;
    s5e_reset_snapshot((volatile const uint32_t *)pmu, &s);
    CHECK(s.inform2 == 0xaabbccdd && s.inform3 == 0x12345604 && s.cmd == 0xf5, "snapshot %08x %08x %08x", s.inform2, s.inform3, s.cmd);
    CHECK(writes() == 0 && count('B', -1) == 0 && g_wait == 0, "snapshot wrote or waited");
    CHECK(count('R', -1) == 3 && count('R', 0xb8) == 1 && count('R', 0xbc) == 1 && count('R', 0x190) == 1, "snapshot read the wrong words");
}
static void test_prepare_does_not_trigger_and_trigger_writes_only_the_trigger(void) {
    reset_model();
    CHECK(s5e_reset_prepare((volatile uint32_t *)pmu, S5E_REASON_DOWNLOAD) == 0, "prepare");
    CHECK(count('W', 0x3c00) == 0 && g_wait == 0, "prepare triggered");
    reset_model();
    s5e_reset_trigger((volatile uint32_t *)pmu);
    CHECK(writes() == 1 && count('W', 0x3c00) == 1 && pmu[0x3c00 / 4] == 2 && pmu[0xbc / 4] == 0x12345604, "trigger touched more than the trigger word");
}
static void test_inform2_byte_is_replaced_even_when_already_set(void) {
    reset_model(); pmu[0xb8 / 4] = 0x00ff0000;
    CHECK(s5e_reset_prepare((volatile uint32_t *)pmu, S5E_REASON_NORMAL) == 0, "prepare");
    CHECK(pmu[0xb8 / 4] == 0x004e0000, "INFORM2 0x%08x (byte 2 must be exactly 0x4e)", pmu[0xb8 / 4]);
    reset_model(); pmu[0xb8 / 4] = 0xffffffff;
    CHECK(s5e_reset_prepare((volatile uint32_t *)pmu, S5E_REASON_NORMAL) == 0, "prepare");
    CHECK(pmu[0xb8 / 4] == 0xff4effff, "INFORM2 0x%08x (only byte 2 may change)", pmu[0xb8 / 4]);
}
static void test_mode_for(void) {
    CHECK(s5e_reset_mode_for(S5E_REASON_DOWNLOAD) == 0 && s5e_reset_mode_for(S5E_REASON_NORMAL) == 0 && s5e_reset_mode_for(S5E_REASON_BOOTLOADER) == 3, "mode table");
}

int main(void) {
    test_download_sequence(); test_bootloader_mode(); test_normal_cancels_the_recovery_mode(); test_only_three_reasons_are_accepted();
    test_stuck_inform2_aborts_before_anything_else(); test_stuck_inform3_aborts_before_the_trigger(); test_stuck_mode_bits_abort_before_the_trigger();
    test_verify_compares_only_the_mode_bits(); test_verify_of_mode_bits_is_not_vacuous(); test_snapshot_never_writes();
    test_prepare_does_not_trigger_and_trigger_writes_only_the_trigger(); test_inform2_byte_is_replaced_even_when_already_set(); test_mode_for();
    printf(fails ? "FAILED %d check(s)\n" : "all checks passed\n", fails);
    return fails ? 1 : 0;
}
