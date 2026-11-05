/* Owned integration interface; actual selected XNU descriptor declaration. */
#ifndef S24_KERNEL_XTS_PROVIDER_H
#define S24_KERNEL_XTS_PROVIDER_H
#include "xts.h"
/* Immutable descriptors have static lifetime; callbacks reject before prepare.
 * Preparation is called at serialized EARLY_BOOT before table registration.
 * Metadata values are bound to accepted KRN029 and rechecked against BOTH real
 * factories before publication. Private factory modes never escape. */
#define S24_KERNEL_XTS_KEY_BYTES 608
#define S24_KERNEL_XTS_TWEAK_BYTES 48
extern const struct ccmode_xts s24_kernel_xts_encrypt;
extern const struct ccmode_xts s24_kernel_xts_decrypt;
int s24_kernel_xts_prepare(void);
const struct ccmode_xts *s24_kernel_xts_encrypt_mode(void);
const struct ccmode_xts *s24_kernel_xts_decrypt_mode(void);
#endif
