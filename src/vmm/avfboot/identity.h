/* Placeholder identity for building scion-avf avfboot (a6f4bc3) without an IPSW, written for s24vmm.
 * Same shape as the output of xnuloader/mkidentity.py --placeholder: one empty property per table and
 * no Apple device-tree data. Enough for the open kernel with an Apple-free PID 1; not for Darwin userland. */
struct identity_prop { const char *name; unsigned offset, length; };

static const struct identity_prop identity_root[] = { { "hakios-placeholder", 0, 0 } };
static const unsigned char identity_root_data[] = { 0 };
static const struct identity_prop identity_product[] = { { "hakios-placeholder", 0, 0 } };
static const unsigned char identity_product_data[] = { 0 };
static const struct identity_prop identity_haptics[] = { { "hakios-placeholder", 0, 0 } };
static const unsigned char identity_haptics_data[] = { 0 };
static const struct identity_prop identity_camera[] = { { "hakios-placeholder", 0, 0 } };
static const unsigned char identity_camera_data[] = { 0 };
