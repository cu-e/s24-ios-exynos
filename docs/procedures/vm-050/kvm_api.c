/* Opens /dev/kvm and reads KVM_GET_API_VERSION. Performs no other KVM ioctl and creates no VM. */
#include <errno.h>
#include <fcntl.h>
#include <linux/kvm.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

int main(void) {
    int fd = open("/dev/kvm", O_RDWR | O_CLOEXEC);
    if (fd < 0) {
        int saved = errno;
        printf("{\"opened\":false,\"errno\":%d,\"error\":\"%s\"}\n", saved, strerror(saved));
        return 2;
    }
    int version = ioctl(fd, KVM_GET_API_VERSION, 0);
    int saved = errno;
    close(fd);
    if (version < 0) {
        printf("{\"opened\":true,\"api_version\":null,\"errno\":%d,\"error\":\"%s\"}\n", saved, strerror(saved));
        return 3;
    }
    printf("{\"opened\":true,\"api_version\":%d}\n", version);
    return 0;
}
