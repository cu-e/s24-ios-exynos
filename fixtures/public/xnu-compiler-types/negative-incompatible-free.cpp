// Genuine selected pointer-compatibility assertion must reject different shape.
#include <kern/kalloc.h>
struct PointerObject { void *pointer; };
struct DataObject { unsigned long long data; };
void check_wrong_free(PointerObject *pointer) {
    KALLOC_TYPE_ASSERT_COMPATIBLE_POINTER(pointer, DataObject);
}
