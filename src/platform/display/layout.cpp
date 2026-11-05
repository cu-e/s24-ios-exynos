#include "contract.h"
static_assert(sizeof(ui_layout)==40,"layout");
static_assert(sizeof(ui_event)==32,"host event, not wire layout");
static_assert(sizeof(ui_input_state)==32,"host state");
static_assert(offsetof(ui_layout,width)==24,"layout width");
