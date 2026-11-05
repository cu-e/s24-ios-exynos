#include "e1s_wifi.h"
static_assert(sizeof(lx_platform) == 136, "reviewed modern callback ABI");
static_assert(sizeof(nw_wifi_events) == 56, "reviewed receive ownership ABI");
static_assert(offsetof(lx_platform, preempt_enable) == 128, "paired preemption hooks");
