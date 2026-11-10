/* SPDX-License-Identifier: GPL-2.0-only */
/* Host-only harness for the NAT-036 report routines. It is NAT-022's host_mk.c (the fake DECON0 and the draw hook, unmodified:
 * included below with its main renamed) plus one scenario that drives the real nat036_decide / nat036_report and the real
 * mk_ckpt3_pass / mk_ckpt3_hold (markerlib3.c) the way nat036_ckpt_c does.
 *
 *   host_mk3 ckpt3 MAXDRAWS OUTFILE GLOBAL_CON TRIG_CON STOPS SEQ [full]
 *     STOPS  the C stop list, "11,30,..."
 *     SEQ    the arrivals, "x2:x3,x2:x3,...". Assembly stops (x2:x3 = 2:1..2:5) arrive with SCTLR_EL1.M clear, C stops and
 *            everything else with M set, as the NAT-035 model gives them. The kernel TTBR0 read at checkpoint 5 is the model's.
 *     full   draw the loader's stage markers first
 * Any other arguments are host_mk.c's. Exit status 6 = the sequence ended without a hold (as host_mk.c). */
#define main host_mk_main
#include "host_mk.c"
#undef main

#if defined(MK_XNU_CKPT) && MK_XNU_CKPT
#include "ckpt3.h"

int main(int argc, char **argv)
{
	if (argc >= 8 && !strcmp(argv[1], "ckpt3")) {
		static struct nat036_state st;
		static uint8_t stops[64];
		uint32_t n = 0;
		char *e;

		maxdraws = atoi(argv[2]); outfile = argv[3];
		fake_gc = (uint32_t)strtoul(argv[4], 0, 0); fake_tc = (uint32_t)strtoul(argv[5], 0, 0);
		for (char *s = argv[6]; *s && n < sizeof stops;) {
			stops[n++] = (uint8_t)strtoul(s, &e, 0);
			s = *e ? e + 1 : e;
		}
		mk_host_fb = calloc(1, MK_BANDS * MK_BAND_BYTES);
		if (argc >= 9 && !strcmp(argv[8], "full")) {
			mk_entry_frame(8, 0x30d00800, 0x30d00800);
			mk_stage(MK_ST_LOADER_MAIN); mk_stage(MK_ST_LOADER_FB); mk_stage(MK_ST_LOADER_MEM);
			mk_stage(MK_ST_LOADER_ZERO); mk_stage(MK_ST_LOADER_COPY); mk_stage(MK_ST_LOADER_ADT);
			mk_stage(MK_ST_LOADER_CLEAN); mk_stage(MK_ST_PRE_JUMP);
		}
		st.s.expect = 1;
		st.stops = stops;
		st.nstops = n;
		for (char *s = argv[7]; *s;) {
			struct nat036_decision d;
			struct nat031_frame f = {{0}, 0};
			struct mk_ckpt3 r;
			uint64_t x2, x3;

			x2 = strtoull(s, &e, 0); s = *e ? e + 1 : e;
			x3 = strtoull(s, &e, 0); s = *e ? e + 1 : e;
			int asm_stop = x2 == 2 && x3 >= 1 && x3 <= 5;
			f.x[0] = 0x9e1f90a00ULL; f.x[1] = 0x00a1b2c3ULL; f.x[2] = x2; f.x[3] = x3;
			f.x[4] = 0xfffffff00743e0b0ULL; f.x[5] = 0x00000000deadbeefULL;
			f.x[11] = asm_stop ? 0x3454593cULL : 0x3454593dULL;		/* the arrival SCTLR_EL1 the stub keeps in the x11 slot */
			f.sp = 0xfffffff00a1b2c40ULL;
			nat036_decide(&st, x2, x3, f.x[11], 0x9e15ae000ULL, &d);
			nat036_report(&r, &st, &f, 0x9e2b6f000ULL, 0x22a51a251aULL, 0xfffffff007437000ULL);
			if (d.action == NAT036_HOLD) mk_ckpt3_hold(&r);
			mk_ckpt3_pass(&r);
		}
		return 6;
	}
	return host_mk_main(argc, argv);
}
#else
int main(int argc, char **argv)
{
	return host_mk_main(argc, argv);
}
#endif
