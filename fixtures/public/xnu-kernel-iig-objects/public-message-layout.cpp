// SPDX-License-Identifier: MIT
// Independent ordinary C++ layout from public selected RPC types and IDL roles.
#include <IOKit/IORPC.h>
struct ServiceContent { IORPCMessage header; OSObjectRef object; OSObjectRef provider; };
struct CopyContent { IORPCMessage header; OSObjectRef object; const char *name; char inline_name[256]; };
#pragma pack(push,4)
struct ServiceMessage { IORPCMessageMach mach; mach_msg_port_descriptor_t object,provider; ServiceContent content; };
struct CopyMessage { IORPCMessageMach mach; mach_msg_port_descriptor_t object; CopyContent content; };
#pragma pack(pop)
static_assert(sizeof(IORPC)==24 && __builtin_offsetof(IORPC,sendSize)==16);
static_assert(sizeof(mach_port_t)==8 && sizeof(mach_port_name_t)==4);
static_assert(sizeof(mach_msg_header_t)==32 && sizeof(mach_msg_body_t)==4);
static_assert(__builtin_offsetof(mach_msg_header_t,msgh_local_port)==16);
static_assert(__builtin_offsetof(mach_msg_port_descriptor_t,pad_end)==12);
static_assert(sizeof(IORPCMessageMach)==36 && sizeof(mach_msg_port_descriptor_t)==16 && sizeof(IORPCMessage)==24);
static_assert(sizeof(ServiceMessage)==108 && __builtin_offsetof(ServiceMessage,content)==68);
static_assert(sizeof(CopyMessage)==348 && __builtin_offsetof(CopyMessage,content)==52);
extern "C" {
extern __attribute__((used)) const unsigned long long s24_public_layout[] = {
 sizeof(IORPC),__builtin_offsetof(IORPC,message),__builtin_offsetof(IORPC,reply),
 __builtin_offsetof(IORPC,sendSize),__builtin_offsetof(IORPC,replySize),
 sizeof(IORPCMessageMach),sizeof(mach_msg_port_descriptor_t),sizeof(IORPCMessage),
 sizeof(ServiceMessage),__builtin_offsetof(ServiceMessage,content),sizeof(ServiceContent),
 sizeof(CopyMessage),__builtin_offsetof(CopyMessage,content),sizeof(CopyContent),
 sizeof(mach_port_t),sizeof(mach_port_name_t),sizeof(mach_msg_header_t),sizeof(mach_msg_body_t),
 __builtin_offsetof(mach_msg_port_descriptor_t,pad_end)
};
}
