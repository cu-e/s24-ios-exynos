#ifndef KRN041_UUID_UUID_H
#define KRN041_UUID_UUID_H
/* KRN-041 host shim: the host has no libuuid headers. kextsymboltool only
 * needs the type; HakiOS hostcompat.h maps uuid_generate to its own helper. */
typedef unsigned char uuid_t[16];
#endif
