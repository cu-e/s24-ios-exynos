// Project-owned Vulkan clear/readback fixture. No Apple or vendor binaries.
#include "probe.h"
#include <vulkan/vulkan.h>
#include <chrono>
#include <cstdint>
#include <sstream>
#include <stdexcept>
#include <vector>

namespace {
using Clock = std::chrono::steady_clock;
constexpr uint32_t W = 256, H = 256;
constexpr VkDeviceSize Budget = 128ull << 20;
std::string quote(const std::string &s) {
    std::string out = "\"";
    for (unsigned char c : s) {
        if (c == '\\' || c == '"') { out += '\\'; out += c; }
        else if (c >= 32 && c < 127) out += c;
        else out += '?';
    }
    return out + '"';
}
void check(VkResult result, const char *what) {
    if (result != VK_SUCCESS) throw std::runtime_error(std::string(what) + ": VkResult " + std::to_string(result));
}
uint32_t memory_type(VkPhysicalDevice physical, uint32_t mask, VkMemoryPropertyFlags flags) {
    VkPhysicalDeviceMemoryProperties properties{};
    vkGetPhysicalDeviceMemoryProperties(physical, &properties);
    for (uint32_t i = 0; i < properties.memoryTypeCount; ++i)
        if ((mask & (1u << i)) && (properties.memoryTypes[i].propertyFlags & flags) == flags) return i;
    throw std::runtime_error("No compatible memory type");
}
}

std::string ProbeResult::json() const {
    std::ostringstream s;
    s << "{\"schema_version\":1,\"fixture\":\"rgba8-red-clear-v1\",\"outcome\":" << quote(outcome)
      << ",\"error\":" << quote(error) << ",\"device_name\":" << quote(device)
      << ",\"api_version\":" << api << ",\"driver_version\":" << driver << ",\"vendor_id\":" << vendor
      << ",\"device_id\":" << device_id << ",\"compared_pixels\":" << compared << ",\"mismatched_pixels\":" << mismatched
      << ",\"elapsed_ms\":" << elapsed_ms << ",\"requires_process_restart\":" << (requires_restart ? "true" : "false") << '}';
    return s.str();
}

ProbeResult run_probe(std::atomic_bool &stop, unsigned deadline_ms) {
    const auto start = Clock::now();
    ProbeResult result;
    VkInstance instance = VK_NULL_HANDLE;
    VkDevice device = VK_NULL_HANDLE;
    VkImage image = VK_NULL_HANDLE;
    VkBuffer buffer = VK_NULL_HANDLE;
    VkDeviceMemory image_mem = VK_NULL_HANDLE, buffer_mem = VK_NULL_HANDLE;
    VkCommandPool pool = VK_NULL_HANDLE;
    VkFence fence = VK_NULL_HANDLE;
    bool in_flight = false, mapped = false;
    try {
        if (stop.load()) { result.outcome = "cancelled"; return result; }
        if (deadline_ms == 0 || deadline_ms > 4000) throw std::runtime_error("Deadline must be 1..4000 ms");
        VkApplicationInfo app{VK_STRUCTURE_TYPE_APPLICATION_INFO};
        app.pApplicationName = "S24 Vulkan probe"; app.apiVersion = VK_API_VERSION_1_1;
        VkInstanceCreateInfo ci{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO}; ci.pApplicationInfo = &app;
        check(vkCreateInstance(&ci, nullptr, &instance), "create instance");
        uint32_t count = 0;
        check(vkEnumeratePhysicalDevices(instance, &count, nullptr), "enumerate devices");
        if (!count) throw std::runtime_error("No Vulkan physical device");
        std::vector<VkPhysicalDevice> physicals(count);
        check(vkEnumeratePhysicalDevices(instance, &count, physicals.data()), "enumerate devices");
        const auto physical = physicals.front();
        VkPhysicalDeviceProperties props{}; vkGetPhysicalDeviceProperties(physical, &props);
        result.device = props.deviceName; result.api = props.apiVersion; result.driver = props.driverVersion;
        result.vendor = props.vendorID; result.device_id = props.deviceID;
        vkGetPhysicalDeviceQueueFamilyProperties(physical, &count, nullptr);
        std::vector<VkQueueFamilyProperties> families(count);
        vkGetPhysicalDeviceQueueFamilyProperties(physical, &count, families.data());
        uint32_t family = count;
        for (uint32_t i = 0; i < count; ++i)
            if (families[i].queueCount && (families[i].queueFlags & VK_QUEUE_GRAPHICS_BIT)) { family = i; break; }
        if (family == count) throw std::runtime_error("No graphics queue");
        float priority = 0.0f;
        VkDeviceQueueCreateInfo qci{VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO};
        qci.queueFamilyIndex = family; qci.queueCount = 1; qci.pQueuePriorities = &priority;
        VkDeviceCreateInfo dci{VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO}; dci.queueCreateInfoCount = 1; dci.pQueueCreateInfos = &qci;
        check(vkCreateDevice(physical, &dci, nullptr, &device), "create device");
        VkQueue queue; vkGetDeviceQueue(device, family, 0, &queue);
        VkImageCreateInfo ici{VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO};
        ici.imageType = VK_IMAGE_TYPE_2D; ici.format = VK_FORMAT_R8G8B8A8_UNORM; ici.extent = {W, H, 1};
        ici.mipLevels = ici.arrayLayers = 1; ici.samples = VK_SAMPLE_COUNT_1_BIT;
        ici.tiling = VK_IMAGE_TILING_OPTIMAL; ici.usage = VK_IMAGE_USAGE_TRANSFER_DST_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT;
        check(vkCreateImage(device, &ici, nullptr, &image), "create image");
        VkMemoryRequirements imreq{}, breq{}; vkGetImageMemoryRequirements(device, image, &imreq);
        VkBufferCreateInfo bci{VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO}; bci.size = W * H * 4; bci.usage = VK_BUFFER_USAGE_TRANSFER_DST_BIT;
        check(vkCreateBuffer(device, &bci, nullptr, &buffer), "create readback");
        vkGetBufferMemoryRequirements(device, buffer, &breq);
        if (imreq.size > Budget || breq.size > Budget - imreq.size) throw std::runtime_error("Allocation exceeds 128 MiB budget");
        VkMemoryAllocateInfo ai{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO}; ai.allocationSize = imreq.size;
        ai.memoryTypeIndex = memory_type(physical, imreq.memoryTypeBits, 0);
        check(vkAllocateMemory(device, &ai, nullptr, &image_mem), "allocate image");
        check(vkBindImageMemory(device, image, image_mem, 0), "bind image");
        ai.allocationSize = breq.size; ai.memoryTypeIndex = memory_type(physical, breq.memoryTypeBits, VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT);
        check(vkAllocateMemory(device, &ai, nullptr, &buffer_mem), "allocate readback");
        check(vkBindBufferMemory(device, buffer, buffer_mem, 0), "bind readback");
        VkCommandPoolCreateInfo pci{VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO}; pci.queueFamilyIndex = family;
        check(vkCreateCommandPool(device, &pci, nullptr, &pool), "create command pool");
        VkCommandBufferAllocateInfo cai{VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO};
        cai.commandPool = pool; cai.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY; cai.commandBufferCount = 1;
        VkCommandBuffer command; check(vkAllocateCommandBuffers(device, &cai, &command), "allocate commands");
        VkCommandBufferBeginInfo bi{VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO}; bi.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
        check(vkBeginCommandBuffer(command, &bi), "begin commands");
        VkImageMemoryBarrier barrier{VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER};
        barrier.srcQueueFamilyIndex = barrier.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
        barrier.image = image; barrier.subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
        barrier.oldLayout = VK_IMAGE_LAYOUT_UNDEFINED; barrier.newLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL;
        barrier.dstAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
        vkCmdPipelineBarrier(command, VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 0, nullptr, 0, nullptr, 1, &barrier);
        VkClearColorValue red{{1.0f, 0.0f, 0.0f, 1.0f}};
        vkCmdClearColorImage(command, image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, &red, 1, &barrier.subresourceRange);
        barrier.oldLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL; barrier.newLayout = VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL;
        barrier.srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT; barrier.dstAccessMask = VK_ACCESS_TRANSFER_READ_BIT;
        vkCmdPipelineBarrier(command, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 0, nullptr, 0, nullptr, 1, &barrier);
        VkBufferImageCopy copy{}; copy.imageSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1}; copy.imageExtent = {W, H, 1};
        vkCmdCopyImageToBuffer(command, image, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, buffer, 1, &copy);
        VkMemoryBarrier host{VK_STRUCTURE_TYPE_MEMORY_BARRIER}; host.srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT; host.dstAccessMask = VK_ACCESS_HOST_READ_BIT;
        vkCmdPipelineBarrier(command, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_HOST_BIT, 0, 1, &host, 0, nullptr, 0, nullptr);
        check(vkEndCommandBuffer(command), "end commands");
        if (stop.load()) { result.outcome = "cancelled"; }
        else if (Clock::now() - start >= std::chrono::milliseconds(deadline_ms)) { result.outcome = "timeout"; result.error = "Deadline reached before submit"; }
        else {
            VkFenceCreateInfo fi{VK_STRUCTURE_TYPE_FENCE_CREATE_INFO}; check(vkCreateFence(device, &fi, nullptr, &fence), "create fence");
            VkSubmitInfo submit{VK_STRUCTURE_TYPE_SUBMIT_INFO}; submit.commandBufferCount = 1; submit.pCommandBuffers = &command;
            in_flight = true; // Submission errors can include device loss; retain until process exit.
            check(vkQueueSubmit(queue, 1, &submit, fence), "submit");
            for (;;) {
                const auto remaining = std::chrono::milliseconds(deadline_ms) - (Clock::now() - start);
                if (remaining <= Clock::duration::zero()) throw std::runtime_error("Fence deadline exceeded; resources retained until process termination");
                const auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(remaining).count();
                auto status = vkWaitForFences(device, 1, &fence, VK_TRUE, static_cast<uint64_t>(std::min<int64_t>(ns, 100000000)));
                if (status == VK_SUCCESS) { in_flight = false; break; }
                if (status != VK_TIMEOUT) check(status, "wait fence");
            }
            if (stop.load()) result.outcome = "cancelled";
            else {
                void *data = nullptr; check(vkMapMemory(device, buffer_mem, 0, VK_WHOLE_SIZE, 0, &data), "map readback"); mapped = true;
                VkMappedMemoryRange range{VK_STRUCTURE_TYPE_MAPPED_MEMORY_RANGE}; range.memory = buffer_mem; range.size = VK_WHOLE_SIZE;
                check(vkInvalidateMappedMemoryRanges(device, 1, &range), "invalidate readback");
                auto bytes = static_cast<const uint8_t *>(data);
                for (unsigned i = 0; i < W * H; ++i) {
                    result.compared++;
                    if (bytes[4*i] != 255 || bytes[4*i+1] != 0 || bytes[4*i+2] != 0 || bytes[4*i+3] != 255) result.mismatched++;
                }
                result.outcome = result.mismatched ? "fail" : "pass";
            }
        }
    } catch (const std::exception &error) { result.error = error.what(); result.outcome = "fail"; }
    result.requires_restart = in_flight;
    // Free only after confirmed completion. Never wait indefinitely for device idle.
    if (!in_flight) {
        if (mapped) vkUnmapMemory(device, buffer_mem);
        if (fence) vkDestroyFence(device, fence, nullptr);
        if (pool) vkDestroyCommandPool(device, pool, nullptr);
        if (buffer) vkDestroyBuffer(device, buffer, nullptr);
        if (image) vkDestroyImage(device, image, nullptr);
        if (buffer_mem) vkFreeMemory(device, buffer_mem, nullptr);
        if (image_mem) vkFreeMemory(device, image_mem, nullptr);
        if (device) vkDestroyDevice(device, nullptr);
        if (instance) vkDestroyInstance(instance, nullptr);
    }
    result.elapsed_ms = std::chrono::duration<double, std::milli>(Clock::now() - start).count();
    return result;
}
