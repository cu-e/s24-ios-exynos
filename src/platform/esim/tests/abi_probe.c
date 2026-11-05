#include "session.h"

const unsigned long long s24_esim_abi[] = {
    sizeof(struct esim_session), _Alignof(struct esim_session),
    offsetof(struct esim_session, cancel_requested), sizeof(_Atomic(unsigned)),
    sizeof(struct esim_transport), sizeof(struct esim_limits),
    __GCC_ATOMIC_INT_LOCK_FREE, ESIM_MAX_COMMAND, ESIM_MAX_RESPONSE, ESIM_MAX_EXCHANGES
};
