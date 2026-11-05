// SPDX-License-Identifier: MIT
// Owned fixture for the genuine tool's selected/debug/ignore name rules.
__attribute__((used,section("__DATA,__s24data"))) unsigned long long selected_data=0x1122334455667788ULL;
__attribute__((used,section("__OTHER,__s24other"))) unsigned long long other_data=0x8877665544332211ULL;
__attribute__((used,section("__LAST,__s24last"))) unsigned long long last_data=0x42;
extern void fixture_external_one(void);
extern void fixture_external_two(void);
void segment_fixture(void) { fixture_external_one(); fixture_external_two(); }
