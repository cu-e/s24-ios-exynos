// Owned Linux-only helper, compiled with real host libc headers in its own TU.
// It does not declare or implement any XNU/Apple interface.
#include <sys/mman.h>
#include <unistd.h>

extern "C" void *s24_guarded_byte()
{
    const long page = sysconf(_SC_PAGESIZE);
    if (page <= 0) return nullptr;
    void *base = mmap(nullptr, 2 * static_cast<size_t>(page),
                      PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (base == MAP_FAILED) return nullptr;
    if (mprotect(static_cast<char *>(base) + page, page, PROT_NONE)) {
        munmap(base, 2 * static_cast<size_t>(page));
        return nullptr;
    }
    return static_cast<char *>(base) + page - 1;
}
