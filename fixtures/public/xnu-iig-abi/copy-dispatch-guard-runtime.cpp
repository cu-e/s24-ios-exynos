// Owned host probe of the real generated CopyDispatchQueue_Invoke function.
// Uses genuine selected public headers and generated code; no fake OSObject.
// Separate host helper places one readable byte immediately before a guard page.
#include <DriverKit/OSObject.iig.cpp>

extern "C" void *s24_guarded_byte();
static unsigned calls;
static kern_return_t handler_result = kIOReturnSuccess;
static kern_return_t handle(OSMetaClassBase *target, const char *name,
                           IODispatchQueue **queue)
{
    ++calls;
    if (target || name[0] != 's' || name[1] != '2' || name[2] != '4' || name[3])
        return kIOReturnBadArgument;
    *queue = nullptr;
    return handler_result;
}

int main(int argc, char **argv)
{
    if (argc != 2) return 90;
    const char mode = argv[1][0];
    OSObject_CopyDispatchQueue_Msg_With_Content msg = {};
    OSObject_CopyDispatchQueue_Rpl_With_Content reply = {};
    msg.mach.msgh.msgh_size = sizeof(msg);
    msg.mach.msgh.msgh_id = kIORPCVersionCurrent;
    msg.mach.msgh_body.msgh_descriptor_count = 1;
    msg.__object__descriptor.type = MACH_MSG_PORT_DESCRIPTOR;
    msg.content.__hdr.msgid = OSObject_CopyDispatchQueue_ID;
    msg.content.__hdr.objectRefs = OSObject_CopyDispatchQueue_Msg_ObjRefs;
    msg.content.__name[0] = 's'; msg.content.__name[1] = '2';
    msg.content.__name[2] = '4';
    IORPC rpc = {&msg.mach, &reply.mach, sizeof(msg), sizeof(reply)};
    kern_return_t expected = kIOReturnIPCError;
    unsigned expected_calls = 0;
    unsigned char *small = nullptr;
    auto callback = handle;
    switch (mode) {
    case 'g': expected = kIOReturnSuccess; expected_calls = 1; break;
    case 's': rpc.sendSize = sizeof(msg) - 1; break;
    case 'r': rpc.replySize = sizeof(reply) - 1; break;
    case 'd': msg.mach.msgh_body.msgh_descriptor_count = 0; break;
    case 'o': msg.content.__hdr.objectRefs = 0; break;
    case 'n':
        for (auto &c : msg.content.__name) c = 'x';
        expected = kIOReturnBadArgument; break;
    case 'e': expected = handler_result = kIOReturnBusy; expected_calls = 1; break;
    case 't':
        small = static_cast<unsigned char *>(s24_guarded_byte());
        if (!small) return 94;
        rpc.message = reinterpret_cast<IORPCMessageMach *>(small);
        rpc.sendSize = 1; break;
    case 'z': rpc.message = nullptr; rpc.sendSize = 0; break;
    case 'u': rpc.reply = nullptr; rpc.replySize = 0; break;
    case 'f': callback = nullptr; break;
    default: return 91;
    }
    auto result = OSObject::CopyDispatchQueue_Invoke(rpc, nullptr, callback);
    // Guarded allocation lives until this short child process exits.
    if (result != expected || calls != expected_calls) return 92;
    if (mode == 'g' &&
        (reply.content.__hdr.msgid != OSObject_CopyDispatchQueue_ID ||
         reply.content.__hdr.objectRefs != OSObject_CopyDispatchQueue_Rpl_ObjRefs ||
         reply.content.__hdr.flags != kIORPCMessageOneway ||
         reply.mach.msgh.msgh_id != kIORPCVersionCurrentReply ||
         reply.mach.msgh.msgh_size != sizeof(reply) ||
         reply.mach.msgh_body.msgh_descriptor_count != 1 ||
         reply.queue__descriptor.type != MACH_MSG_PORT_DESCRIPTOR ||
         reply.content.queue != 0)) return 93;
    return 0;
}
