# Pinned donor host models

QcomBaseband `dd0199cf3300764ed52b23f4a47761f91fab21a2` has a small reviewed `scripts/check.py`: it compiles seven imported C protocol/register models with `cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined`, then executes only those temporary host binaries. Inspect that script and the model inputs before execution. No phone, firmware, SIM, eUICC, network or native kernel is used.

Verify the checkout, copy only scripts/tests/baseband/ipa plus LICENSE into a fresh `artifacts/radio-research/` run, execute the script with an outer 90-second subprocess deadline, and retain actual stdout/stderr and return code. Host model passes validate the selected donor model cases, not the production IOKit bridge, iOS 16.5 ABI, Samsung protocol, actual firmware or carrier service.
