// SPDX-License-Identifier: MIT
// Owned link-only provider for checking segment names, not a kernel substitute.
volatile unsigned long long constructor_probe_counter;
void iokit_post_constructor_init(void) { ++constructor_probe_counter; }
