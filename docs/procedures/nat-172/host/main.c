#include <stdlib.h>
#include <stdint.h>
#include <stdio.h>
extern void fakeapm_init(void); extern void e1s_pmic_init(void);
extern int host_cmds, host_writes, host_bad_writes, host_pmic_mode, host_settle; extern char host_log[];
extern uint8_t pmic[16][256][256];
extern uint32_t cmu[0x400]; extern int host_dvfs_cmds, host_dvfs_bad;
extern const char *host_case;
int main(int argc, char **argv)
{
	host_pmic_mode = atoi(argv[1]);
	if (argc > 2) host_case = argv[2];
	fakeapm_init();
	e1s_pmic_init();
	if (argc > 2 && argv[2][0] == 'f') {
		extern int e1s_acpm_mfd_write(uint8_t, uint8_t, uint8_t, uint8_t);
		extern int e1s_acpm_mfd_update(uint8_t, uint8_t, uint8_t, uint8_t, uint8_t);
		(void)e1s_acpm_mfd_write(0x0d, 5, 0x3c, 0xd8);
		(void)e1s_acpm_mfd_write(0x0b, 5, 0x3d, 0xd8);
		(void)e1s_acpm_mfd_write(0x0d, 0x1d, 0x3d, 0xd8);
		(void)e1s_acpm_mfd_write(0x0d, 5, 0x3d, 0xd9);
		(void)e1s_acpm_mfd_update(0x0d, 5, 0x3d, 0, 0xff);
	}
	printf("%s", host_log);
	printf("DVFS cmds=%d bad=%d con3=%#x\n", host_dvfs_cmds, host_dvfs_bad, cmu[0x10c / 4]);
	printf("RESULT cmds=%d writes=%d bad=%d ldo9=%#x ldo18=%#x settle=%d\n", host_cmds, host_writes, host_bad_writes,
	    pmic[0x0d][5][0x34], pmic[0x0d][5][0x3d], host_settle);
	return 0;
}
