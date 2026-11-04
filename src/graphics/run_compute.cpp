// Project-owned host execution of the fixed write_marker SPIR-V interface.
#include <vulkan/vulkan.h>
#include <array>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <vector>

static void ok(VkResult r) { if(r!=VK_SUCCESS) throw std::runtime_error("Vulkan result "+std::to_string(r)); }
int main(int argc,char **argv) {
    if(argc!=2) return 2;
    try {
        std::ifstream file(argv[1],std::ios::binary|std::ios::ate);
        auto bytes=file.tellg();if(bytes<20 || bytes>1024*1024 || bytes%4) throw std::runtime_error("Invalid shader size");
        std::vector<uint32_t> words(static_cast<size_t>(bytes)/4);file.seekg(0);file.read(reinterpret_cast<char*>(words.data()),bytes);
        if(!file || words[0]!=0x07230203) throw std::runtime_error("Invalid SPIR-V");
        VkApplicationInfo app{VK_STRUCTURE_TYPE_APPLICATION_INFO};app.apiVersion=VK_API_VERSION_1_2;
        VkInstanceCreateInfo ici{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};ici.pApplicationInfo=&app;
        VkInstance instance;ok(vkCreateInstance(&ici,nullptr,&instance));uint32_t n=0;ok(vkEnumeratePhysicalDevices(instance,&n,nullptr));
        if(!n) throw std::runtime_error("No Vulkan device");
        std::vector<VkPhysicalDevice> devices(n);ok(vkEnumeratePhysicalDevices(instance,&n,devices.data()));auto physical=devices[0];
        vkGetPhysicalDeviceQueueFamilyProperties(physical,&n,nullptr);std::vector<VkQueueFamilyProperties> qs(n);vkGetPhysicalDeviceQueueFamilyProperties(physical,&n,qs.data());
        uint32_t family=n;for(uint32_t i=0;i<n;++i)if(qs[i].queueCount && (qs[i].queueFlags&VK_QUEUE_COMPUTE_BIT)){family=i;break;}
        if(family==n) throw std::runtime_error("No compute queue");
        float priority=0;VkDeviceQueueCreateInfo qci{VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO};qci.queueFamilyIndex=family;qci.queueCount=1;qci.pQueuePriorities=&priority;
        VkDeviceCreateInfo dci{VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO};dci.queueCreateInfoCount=1;dci.pQueueCreateInfos=&qci;
        VkDevice device;ok(vkCreateDevice(physical,&dci,nullptr,&device));VkQueue queue;vkGetDeviceQueue(device,family,0,&queue);
        VkBufferCreateInfo bci{VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO};bci.size=64;bci.usage=VK_BUFFER_USAGE_STORAGE_BUFFER_BIT;
        VkBuffer buffer;ok(vkCreateBuffer(device,&bci,nullptr,&buffer));VkMemoryRequirements req;vkGetBufferMemoryRequirements(device,buffer,&req);
        if(req.size>(1u<<20))throw std::runtime_error("Unexpected allocation size");
        VkPhysicalDeviceMemoryProperties mp;vkGetPhysicalDeviceMemoryProperties(physical,&mp);uint32_t type=mp.memoryTypeCount;
        for(uint32_t i=0;i<mp.memoryTypeCount;++i)if((req.memoryTypeBits&(1u<<i))&&(mp.memoryTypes[i].propertyFlags&VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT)){type=i;break;}
        if(type==mp.memoryTypeCount)throw std::runtime_error("No host memory");
        VkMemoryAllocateInfo ai{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO};ai.allocationSize=req.size;ai.memoryTypeIndex=type;
        VkDeviceMemory memory;ok(vkAllocateMemory(device,&ai,nullptr,&memory));ok(vkBindBufferMemory(device,buffer,memory,0));
        void *mapped;ok(vkMapMemory(device,memory,0,VK_WHOLE_SIZE,0,&mapped));
        std::array<uint32_t,16> initial;initial.fill(0xdeadbeef);std::memcpy(mapped,initial.data(),64);
        VkMappedMemoryRange range{VK_STRUCTURE_TYPE_MAPPED_MEMORY_RANGE};range.memory=memory;range.size=VK_WHOLE_SIZE;ok(vkFlushMappedMemoryRanges(device,1,&range));
        VkDescriptorSetLayoutBinding binding{};binding.binding=0;binding.descriptorType=VK_DESCRIPTOR_TYPE_STORAGE_BUFFER;binding.descriptorCount=1;binding.stageFlags=VK_SHADER_STAGE_COMPUTE_BIT;
        VkDescriptorSetLayoutCreateInfo slci{VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO};slci.bindingCount=1;slci.pBindings=&binding;
        VkDescriptorSetLayout set_layout;ok(vkCreateDescriptorSetLayout(device,&slci,nullptr,&set_layout));
        VkPushConstantRange push{VK_SHADER_STAGE_COMPUTE_BIT,0,4};VkPipelineLayoutCreateInfo plci{VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO};plci.setLayoutCount=1;plci.pSetLayouts=&set_layout;plci.pushConstantRangeCount=1;plci.pPushConstantRanges=&push;
        VkPipelineLayout layout;ok(vkCreatePipelineLayout(device,&plci,nullptr,&layout));
        VkShaderModuleCreateInfo sci{VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO};sci.codeSize=words.size()*4;sci.pCode=words.data();
        VkShaderModule shader;ok(vkCreateShaderModule(device,&sci,nullptr,&shader));VkComputePipelineCreateInfo pci{VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO};
        pci.layout=layout;pci.stage.sType=VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO;pci.stage.stage=VK_SHADER_STAGE_COMPUTE_BIT;pci.stage.module=shader;pci.stage.pName="main";
        VkPipeline pipeline;ok(vkCreateComputePipelines(device,VK_NULL_HANDLE,1,&pci,nullptr,&pipeline));
        VkDescriptorPoolSize size{VK_DESCRIPTOR_TYPE_STORAGE_BUFFER,1};VkDescriptorPoolCreateInfo dpci{VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO};dpci.maxSets=1;dpci.poolSizeCount=1;dpci.pPoolSizes=&size;
        VkDescriptorPool descriptors;ok(vkCreateDescriptorPool(device,&dpci,nullptr,&descriptors));VkDescriptorSetAllocateInfo dsai{VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO};dsai.descriptorPool=descriptors;dsai.descriptorSetCount=1;dsai.pSetLayouts=&set_layout;
        VkDescriptorSet set;ok(vkAllocateDescriptorSets(device,&dsai,&set));VkDescriptorBufferInfo info{buffer,0,64};VkWriteDescriptorSet write{VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET};write.dstSet=set;write.descriptorCount=1;write.descriptorType=VK_DESCRIPTOR_TYPE_STORAGE_BUFFER;write.pBufferInfo=&info;vkUpdateDescriptorSets(device,1,&write,0,nullptr);
        VkCommandPoolCreateInfo cpci{VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO};cpci.queueFamilyIndex=family;VkCommandPool pool;ok(vkCreateCommandPool(device,&cpci,nullptr,&pool));
        VkCommandBufferAllocateInfo cbai{VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO};cbai.commandPool=pool;cbai.commandBufferCount=1;cbai.level=VK_COMMAND_BUFFER_LEVEL_PRIMARY;VkCommandBuffer command;ok(vkAllocateCommandBuffers(device,&cbai,&command));
        VkCommandBufferBeginInfo begin{VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};ok(vkBeginCommandBuffer(command,&begin));vkCmdBindPipeline(command,VK_PIPELINE_BIND_POINT_COMPUTE,pipeline);vkCmdBindDescriptorSets(command,VK_PIPELINE_BIND_POINT_COMPUTE,layout,0,1,&set,0,nullptr);
        uint32_t offset=0;vkCmdPushConstants(command,layout,VK_SHADER_STAGE_COMPUTE_BIT,0,4,&offset);vkCmdDispatch(command,1,1,1);
        VkMemoryBarrier barrier{VK_STRUCTURE_TYPE_MEMORY_BARRIER};barrier.srcAccessMask=VK_ACCESS_SHADER_WRITE_BIT;barrier.dstAccessMask=VK_ACCESS_HOST_READ_BIT;vkCmdPipelineBarrier(command,VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,VK_PIPELINE_STAGE_HOST_BIT,0,1,&barrier,0,nullptr,0,nullptr);ok(vkEndCommandBuffer(command));
        VkFenceCreateInfo fci{VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};VkFence fence;ok(vkCreateFence(device,&fci,nullptr,&fence));VkSubmitInfo si{VK_STRUCTURE_TYPE_SUBMIT_INFO};si.commandBufferCount=1;si.pCommandBuffers=&command;ok(vkQueueSubmit(queue,1,&si,fence));ok(vkWaitForFences(device,1,&fence,VK_TRUE,4000000000ull));
        ok(vkInvalidateMappedMemoryRanges(device,1,&range));std::array<uint32_t,16> output;std::memcpy(output.data(),mapped,64);
        bool guard=true;for(unsigned i=1;i<16;++i)guard&=output[i]==0xdeadbeef;
        bool pass=output[0]==9212400 && guard;
        std::cout<<"{\"environment\":\"host-vulkan\",\"expected\":9212400,\"actual\":"<<output[0]<<",\"guard_words_intact\":"<<(guard?"true":"false")<<",\"outcome\":\""<<(pass?"pass":"fail")<<"\"}\n";
        vkUnmapMemory(device,memory);vkDestroyFence(device,fence,nullptr);vkDestroyCommandPool(device,pool,nullptr);vkDestroyDescriptorPool(device,descriptors,nullptr);vkDestroyPipeline(device,pipeline,nullptr);vkDestroyShaderModule(device,shader,nullptr);vkDestroyPipelineLayout(device,layout,nullptr);vkDestroyDescriptorSetLayout(device,set_layout,nullptr);vkDestroyBuffer(device,buffer,nullptr);vkFreeMemory(device,memory,nullptr);vkDestroyDevice(device,nullptr);vkDestroyInstance(instance,nullptr);
        return pass?0:1;
    } catch(const std::exception &error) { std::cerr<<error.what()<<'\n';return 1; }
}
