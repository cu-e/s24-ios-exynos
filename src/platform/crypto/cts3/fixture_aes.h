/* Real test CBC backends only; excluded from production.json sources. */
#ifndef S24_CTS3_FIXTURE_AES_H
#define S24_CTS3_FIXTURE_AES_H
#include <corecrypto/ccmode.h>
/* algorithm0=accepted DES,1=accepted TDES,2=test-only canonical AES CBC. */
int cts3_fixture_mode(struct ccmode_cbc *,unsigned algorithm,int decrypt);
int cts3_fixture_clear(const struct ccmode_cbc *,cccbc_ctx *);
/* Fault wrapper returns a real error BEFORE the chosen genuine CBC invocation.
 * All other calls invoke the real underlying CBC, never an identity/toy cipher. */
void cts3_fixture_fault(const struct ccmode_cbc *,unsigned at,struct ccmode_cbc *);
unsigned cts3_fixture_calls(void);
#endif
