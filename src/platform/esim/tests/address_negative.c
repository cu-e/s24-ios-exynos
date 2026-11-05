#include <stdlib.h>

/* Deliberate invalid access. Test-only executable, never part of the module. */
int main(int argc, char **argv)
{
    char *bytes = malloc(8);
    volatile int index = argc + 8;
    int result;
    (void)argv;
    if (!bytes) return 2;
    bytes[index] = 42;
    result = bytes[index];
    free(bytes);
    return result;
}
