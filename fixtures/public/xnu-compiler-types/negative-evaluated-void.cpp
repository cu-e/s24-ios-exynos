// A runtime void dereference remains rejected by this experimental compiler.
void bad_void_read(void *pointer) { *pointer; }
