/* Deliberately invalid host-only controls; never linked with the adapter. */
#include <limits.h>
#include <stdlib.h>
int main(int argc, char **argv) {
    if (argc > 1 && argv[1][0] == 'a') {
        volatile int index = 8;
        volatile char *p = malloc(4);
        if (!p) return 2;
        p[index] = 1;
        free((void *)p);
    } else {
        volatile int a = INT_MAX, b = 1;
        volatile int value = a + b;
        (void)value;
    }
    return 0;
}
