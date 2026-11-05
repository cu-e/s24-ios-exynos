#include "transport.h"
static_assert(sizeof(void *) == 8, "selected host/ARM64 layouts");
static_assert(sizeof(bt_h4) == 80, "borrowed parser state");
static_assert(sizeof(bt_command) == 48, "exclusive initialization command state");
static_assert(sizeof(bt_command_reply) == 24, "borrowed raw reply view");
