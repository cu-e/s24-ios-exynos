# Reproduce display/input source review

Use research/sources.json and fixtures/public/display-input-research/source-manifest.json for exact pins and file hashes. The selected donor source is data; do not execute upstream install, firmware, preview or flash scripts.

```sh
python3 tools/sources.py fetch s24-port s24-linux s24-bsp-reference hakios
python3 tools/sources.py verify s24-port s24-linux s24-bsp-reference hakios
```

Existing sparse checkouts need explicit newly registered text paths before verification. Keep historical pins and checkouts clean. Read the actual generated retail r13 touch node and firmware override, sec_input coordinate-max conversion, stm_dev bitfields and stm_core field extraction. Compare these to E1S post_event; the independent source regression is UI-006, not an upstream string-presence test.

Read the physical s6e3fae 60 Hz mode including DSC, DPU SysMMU/IRQ declarations, loader framebuffer discovery/fallback, E1S diagnostic display probe, embedded MiniIOSurface/MiniIOMobileFramebuffer and redwood input queue. Current HakiOS input review/inject code is a separately pinned comparison; do not mix renamed headers/device nodes or adopt newer offsets as an exact ABI match.

The historical stm_ts IRQ association is derived only from existing ignored DEV-001 interrupts.txt. It confirms Android gpa1 pin 2 activity, not native GIC42 operation. Public fixtures contain the minimum association and source digest; no complete dump or new phone operation.

Record failed Reddit keyword searches and actual direct-post/comment coverage. A screenshot, author performance claim or missing archived comment is not a device measurement. Keep archive bytes private. Apple IOSurface web content may require JS; successful search/page discovery is not private selector-layout verification. No Apple binary/SDK was fetched or used here.
