// Genuine selected data-only predicate must reject a pointer-containing type.
#include <kern/kalloc.h>
struct PointerData { void *pointer; };
static_assert(KALLOC_TYPE_IS_DATA_ONLY(PointerData), "S24_EXPECTED_DATA_REJECTION");
