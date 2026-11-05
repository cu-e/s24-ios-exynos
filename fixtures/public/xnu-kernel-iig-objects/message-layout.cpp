// SPDX-License-Identifier: MIT
// Inspect actual regenerated definitions under their full selected IOKit flags.
#include S24_GENERATED_IMPLEMENTATION
#if S24_SERVICE
#define MSG IOService_Start_Msg_With_Content
#define RPL IOService_Start_Rpl_With_Content
#define CONTENT IOService_Start_Msg_Content
#define REFS IOService_Start_Msg_ObjRefs
#define ID IOService_Start_ID
#define ARG provider
#else
#define MSG OSObject_CopyDispatchQueue_Msg_With_Content
#define RPL OSObject_CopyDispatchQueue_Rpl_With_Content
#define CONTENT OSObject_CopyDispatchQueue_Msg_Content
#define REFS OSObject_CopyDispatchQueue_Msg_ObjRefs
#define ID OSObject_CopyDispatchQueue_ID
#define ARG name
#endif
extern "C" {
extern __attribute__((used)) const unsigned long long s24_iig_layout[] = {
 sizeof(IORPC),__builtin_offsetof(IORPC,message),__builtin_offsetof(IORPC,reply),
 __builtin_offsetof(IORPC,sendSize),__builtin_offsetof(IORPC,replySize),
 sizeof(IORPCMessageMach),sizeof(mach_msg_port_descriptor_t),sizeof(IORPCMessage),
 sizeof(MSG),sizeof(RPL),__builtin_offsetof(MSG,content),sizeof(CONTENT),
 __builtin_offsetof(CONTENT,ARG),REFS,ID
};
}
