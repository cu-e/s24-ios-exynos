# UI-006: actual E1S source regression

The pinned Samsung stm_ts_event_coordinate declaration places y_3_0 in the low nibble and x_3_0 in the high nibble of byte 3. Its stm_ts_coord_parsing uses those named fields. The pinned E1S post_event function reverses them. Reproduce using the actual pure function extracted from the source patch; never call its MMIO/SPI/thread functions.

Register TOUCHREG-001 before the explicit original-source run. The original executable is expected to return 3 for coordinate mismatches; retain that negative result. After review, register TOUCHREG-002 before a corrected run and exact isolated source preparation. Neither experiment compiles a full kernel or sends touch events to a phone.

```sh
python3 tests/test_e1s_touch_regression.py --run original-touch-session --original
python3 tests/test_e1s_touch_regression.py --run corrected-touch-session
python3 tools/build/prepare_xnu.py --run corrected-xnu-session
python3 -m unittest discover -s tests -p test_e1s_touch_regression.py -v
```

Explicit regression runs copy tested inputs, generated host shims, compile/execute logs and hashes into a fresh ignored artifacts/touch-regression/ directory. Original failure is useful evidence; it does not satisfy corrected acceptance. The host shim replaces only redwood_touch_post with captured outputs and compiles only post_event plus its selected constants and local state. No UART/SPI/GPIO/MMIO, XNU/IOKit or iOS code executes. Synthetic vectors are not captured hardware packets.

The local two-line patch applies to generated bsd/dev/e1s_touch.c after the complete pinned upstream series. Keep upstream checkouts clean. tools/build/prepare_xnu.py must fail on check/apply mismatch and record the local patch hash and resulting file hash. Review component provenance before redistribution; a copied embedded license does not establish a grant for every E1S addition.
