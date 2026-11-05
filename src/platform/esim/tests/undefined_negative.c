#include <limits.h>

/* Intentionally invalid test only. Never linked into the transport component. */
int main(int argc, char **argv)
{
    volatile int value = INT_MAX;
    (void)argv;
    return value + argc;
}
