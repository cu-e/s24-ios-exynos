/* Real selected XNU subclasses. No SDK stand-ins or registration personality. */
#ifndef S24_GPU_USERCLIENT_HPP
#define S24_GPU_USERCLIENT_HPP

#include <IOKit/IOUserClient.h>
#include <IOKit/IOLocks.h>
#include "Policy.hpp"

class SGPUUserClient;

/* Abstract owner for a future genuine hardware provider. There is no concrete
 * backend in this component. All calls, admission, stop and close share lock_.
 * Hardware implementations must use bounded operations, must not reenter this
 * gate, and must keep GPU backing alive independently of method/reply lifetime.
 */
class SGPUTransportProvider : public IOService {
    OSDeclareAbstractStructors(SGPUTransportProvider);
    friend class SGPUUserClient;
    IOLock *lock_ = nullptr;
    bool stopping_ = false;

    bool admitClient(SGPUUserClient *);
    void closeClient(SGPUUserClient *);
    s24gpu::Completion transact(SGPUUserClient *, uintptr_t caller, const s24gpu::Shape &);
    static void dispatch(void *, const sgpu_request_view *, sgpu_backend_result *);

protected:
    // Default refusal is intentional. Readiness must mean a qualified, usable
    // native backend; a protocol fixture or allocated service is insufficient.
    virtual bool hardwareReadyLocked() const { return false; }
    virtual void hardwareRequestLocked(task_t originalTask, SGPUUserClient *,
        const sgpu_request_view *, sgpu_backend_result *) = 0;
    virtual s24gpu::Quiescence hardwareCloseLocked(task_t, SGPUUserClient *)
        { return s24gpu::Quiescence::unknown; }

public:
    bool init(OSDictionary *properties = nullptr) override;
    void stop(IOService *provider) override;
    void free() override;
    IOReturn newUserClient(task_t, void *, UInt32, OSDictionary *, IOUserClient **) override;
};

class SGPUUserClient final : public IOUserClient {
    OSDeclareDefaultStructors(SGPUUserClient);
    friend class SGPUTransportProvider;
    task_t owner_ = nullptr;
    SGPUTransportProvider *provider_ = nullptr;
    s24gpu::Session session_ = {};
    static bool authenticated(task_t, void *, UInt32);
    IOReturn closeConnection();

public:
    bool initWithTask(task_t, void *, UInt32, OSDictionary *) override;
    bool start(IOService *) override;
    void stop(IOService *) override;
    void free() override;
    IOReturn clientClose() override;
    IOReturn clientDied() override;
    IOService *getService() override;
    IOReturn externalMethod(uint32_t, IOExternalMethodArguments *,
        IOExternalMethodDispatch * = nullptr, OSObject * = nullptr, void * = nullptr) override;
};

#endif
