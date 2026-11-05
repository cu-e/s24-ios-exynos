#include "frame.h"
static_assert(__is_standard_layout(cam_frame),"owned descriptor layout");
static_assert(sizeof(cam_plane)==24,"plane extent layout");
static_assert(offsetof(cam_frame,allocation_bytes)==56,"owned scalar prefix");
extern "C" const uint64_t cam_owned_layout[]={sizeof(cam_frame),sizeof(cam_layout),sizeof(cam_queue),offsetof(cam_frame,planes)};
