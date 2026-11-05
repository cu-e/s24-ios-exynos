#include "SGPUUserClient.hpp"
#include <IOKit/IOLib.h>
#include <IOKit/IOKitKeys.h>
#include <libkern/c++/OSBoolean.h>
#include <kern/task.h>
#include <kern/task_ref.h>

OSDefineMetaClassAndAbstractStructors(SGPUTransportProvider, IOService);
OSDefineMetaClassAndStructors(SGPUUserClient, IOUserClient);

namespace {
constexpr UInt32 connectionType = 0;
constexpr const char *entitlement = "org.s24.research.gpu.transport";

IOReturn outer(s24gpu::Transport status)
{
    switch (status) {
    case s24gpu::Transport::ok: return kIOReturnSuccess;
    case s24gpu::Transport::bad_argument: return kIOReturnBadArgument;
    case s24gpu::Transport::unsupported: return kIOReturnUnsupported;
    case s24gpu::Transport::not_privileged: return kIOReturnNotPrivileged;
    case s24gpu::Transport::not_open: return kIOReturnNotOpen;
    case s24gpu::Transport::not_ready: return kIOReturnNotReady;
    case s24gpu::Transport::busy: return kIOReturnBusy;
    case s24gpu::Transport::no_memory: return kIOReturnNoMemory;
    case s24gpu::Transport::io_error: return kIOReturnIOError;
    }
    return kIOReturnInternalError;
}

struct Invocation {
    SGPUTransportProvider *provider;
    SGPUUserClient *client;
};
} // namespace

bool SGPUTransportProvider::init(OSDictionary *properties)
{
    if (!IOService::init(properties)) return false;
    lock_ = IOLockAlloc();
    return lock_ != nullptr;
}

void SGPUTransportProvider::stop(IOService *provider)
{
    if (lock_) {
        IOLockLock(lock_);
        stopping_ = true;
        IOLockUnlock(lock_);
    }
    // Waiting for a synchronous method is not proof that submitted GPU work
    // stopped. Existing provider-held sessions and resources stay retained.
    IOService::stop(provider);
}

void SGPUTransportProvider::free()
{
    if (lock_) { IOLockFree(lock_); lock_ = nullptr; }
    IOService::free();
}

bool SGPUUserClient::authenticated(task_t task, void *security, UInt32 type)
{
    if (task == TASK_NULL || security != static_cast<void *>(task) || task != current_task() ||
        type != connectionType) return false;
    if (IOUserClient::clientHasPrivilege(static_cast<void *>(task), kIOClientPrivilegeAdministrator) != kIOReturnSuccess)
        return false;
    const auto value = IOUserClient::copyClientEntitlement(task, entitlement);
    return value.get() == kOSBooleanTrue;
}

IOReturn SGPUTransportProvider::newUserClient(task_t task, void *security, UInt32 type,
    OSDictionary *properties, IOUserClient **handler)
{
    if (!handler) return kIOReturnBadArgument;
    *handler = nullptr;
    if (!SGPUUserClient::authenticated(task, security, type)) return kIOReturnNotPrivileged;
    IOLockLock(lock_);
    const bool ready = !stopping_ && hardwareReadyLocked();
    IOLockUnlock(lock_);
    if (!ready) return kIOReturnNotReady;
    SGPUUserClient *client = new SGPUUserClient;
    if (!client) return kIOReturnNoMemory;
    if (!client->initWithTask(task, security, type, properties)) { client->release(); return kIOReturnNotPrivileged; }
    if (!client->attach(this)) { client->release(); return kIOReturnNotAttached; }
    if (!client->start(this)) { client->detach(this); client->release(); return kIOReturnNotReady; }
    *handler = client;
    return kIOReturnSuccess;
}

bool SGPUUserClient::initWithTask(task_t task, void *security, UInt32 type, OSDictionary *properties)
{
    if (!authenticated(task, security, type) || !IOUserClient::initWithTask(task, security, type, properties)) return false;
    owner_ = task;
    task_reference(owner_);
    return setProperty(kIOUserClientDefaultLockingKey, kOSBooleanTrue) &&
        setProperty(kIOUserClientDefaultLockingSingleThreadExternalMethodKey, kOSBooleanTrue) &&
        setProperty(kIOUserClientDefaultLockingSetPropertiesKey, kOSBooleanTrue);
}

bool SGPUUserClient::start(IOService *service)
{
    SGPUTransportProvider *provider = OSDynamicCast(SGPUTransportProvider, service);
    if (!provider || !owner_ || !IOUserClient::start(service)) return false;
    provider_ = provider;
    provider_->retain(); // Immutable until free; stop does not clear this pointer.
    if (!provider_->admitClient(this)) {
        provider_->release(); provider_ = nullptr;
        IOUserClient::stop(service);
        return false;
    }
    return true;
}

bool SGPUTransportProvider::admitClient(SGPUUserClient *client)
{
    IOLockLock(lock_);
    const auto status = s24gpu::admit(client->session_, reinterpret_cast<uintptr_t>(client->owner_),
        client->owner_ != TASK_NULL, !stopping_ && hardwareReadyLocked());
    if (status == s24gpu::Transport::ok) client->retain(); // Hardware-session hold.
    IOLockUnlock(lock_);
    return status == s24gpu::Transport::ok;
}

void SGPUTransportProvider::dispatch(void *raw, const sgpu_request_view *view, sgpu_backend_result *result)
{
    const auto call = static_cast<Invocation *>(raw);
    call->provider->hardwareRequestLocked(call->client->owner_, call->client, view, result);
}

s24gpu::Completion SGPUTransportProvider::transact(SGPUUserClient *client, uintptr_t caller, const s24gpu::Shape &shape)
{
    IOLockLock(lock_);
    const auto status = s24gpu::begin(client->session_, caller, shape, !stopping_ && hardwareReadyLocked());
    if (status != s24gpu::Transport::ok) { IOLockUnlock(lock_); return {status, SGPU_BACKEND_ERROR, 0}; }
    client->retain(); // Survives all error and concurrent close paths.
    s24gpu::Storage *storage = IOMallocType(s24gpu::Storage);
    s24gpu::Completion result = {s24gpu::Transport::no_memory, SGPU_UNSUPPORTED, 0};
    if (storage) {
        Invocation call = {this, client};
        result = s24gpu::snapshot_dispatch(shape, *storage, dispatch, &call);
        // This owns only synchronous snapshots, never GPU backing or an IB.
        IOFreeType(storage, s24gpu::Storage);
    }
    s24gpu::finish(client->session_, result.protocol_status);
    IOLockUnlock(lock_);
    client->release();
    return result;
}

void SGPUTransportProvider::closeClient(SGPUUserClient *client)
{
    bool releaseHold = false;
    IOLockLock(lock_);
    s24gpu::close(client->session_);
    if (client->session_.provider_hold && !client->session_.close_notified) {
        client->session_.close_notified = true;
        const auto proof = hardwareCloseLocked(client->owner_, client);
        releaseHold = s24gpu::release_session_hold(client->session_, proof);
    }
    IOLockUnlock(lock_);
    // Unknown quiescence deliberately retains the session/client/provider/task
    // chain. A future backend needs its own reviewed asynchronous drain path.
    if (releaseHold) client->release();
}

IOReturn SGPUUserClient::externalMethod(uint32_t selector, IOExternalMethodArguments *args,
    IOExternalMethodDispatch *dispatchTable, OSObject *target, void *reference)
{
    if (!args) return kIOReturnBadArgument;
    const size_t capacity = args->structureOutputSize;
    args->structureOutputSize = 0; // Refusals never publish stale output bytes.
    const uint32_t scalarOutputs = args->scalarOutputCount;
    args->scalarOutputCount = 0;
    if (dispatchTable || target || reference) return kIOReturnBadArgument;
    bool reserved = args->__reservedA != 0;
    for (const auto word : args->__reserved) reserved |= word != 0;
    const s24gpu::Shape shape = {
        args->version == kIOExternalMethodArgumentsCurrentVersion, selector, args->selector,
        args->scalarInputCount, scalarOutputs, args->asyncReferenceCount,
        args->asyncWakePort != MACH_PORT_NULL, args->asyncReference != nullptr,
        args->structureInputDescriptor != nullptr,
        args->structureOutputDescriptor != nullptr || args->structureOutputDescriptorSize != 0,
        args->structureVariableOutputData != nullptr, reserved,
        args->structureInput, args->structureInputSize, args->structureOutput, capacity
    };
    if (!provider_) return kIOReturnNotOpen;
    // Recheck credentials/entitlement on each entry, including after exec.
    if (!authenticated(owner_, static_cast<void *>(owner_), connectionType)) return kIOReturnNotPrivileged;
    const auto result = provider_->transact(this, reinterpret_cast<uintptr_t>(current_task()), shape);
    if (result.transport == s24gpu::Transport::ok) args->structureOutputSize = static_cast<uint32_t>(result.bytes);
    // SGPU errors remain encoded in the reply; never cast them to IOReturn.
    return outer(result.transport);
}

IOReturn SGPUUserClient::closeConnection()
{
    if (provider_) provider_->closeClient(this);
    terminate();
    return kIOReturnSuccess; // Connection close, not hardware completion.
}

IOReturn SGPUUserClient::clientClose() { return closeConnection(); }
IOReturn SGPUUserClient::clientDied() { return closeConnection(); }
IOService *SGPUUserClient::getService() { return provider_; }

void SGPUUserClient::stop(IOService *service)
{
    if (provider_) provider_->closeClient(this);
    IOUserClient::stop(service);
}

void SGPUUserClient::free()
{
    // An unknown hardware session keeps a provider hold and cannot reach free.
    if (provider_) { provider_->release(); provider_ = nullptr; }
    if (owner_ != TASK_NULL) { task_deallocate(owner_); owner_ = TASK_NULL; }
    IOUserClient::free();
}
