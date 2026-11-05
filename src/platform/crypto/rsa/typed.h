#ifndef S24_RSA_TYPED_H
#define S24_RSA_TYPED_H
#include <libkern/crypto/register_crypto.h>
#include "rsa.h"
int s24_rsa_callbacks(ccrsa_make_pub_fn_t *,ccrsa_verify_pkcs1v15_fn_t *);
#endif
