/* Genuine selected callback typedef assignment, no function-pointer casts. */
#include "typed.h"
int s24_rsa_callbacks(ccrsa_make_pub_fn_t *make,ccrsa_verify_pkcs1v15_fn_t *verify){
    if(!make || !verify)return CCERR_PARAMETER;
    *make=s24_rsa_make_pub;*verify=s24_rsa_verify_pkcs1v15;return CCERR_OK;
}
