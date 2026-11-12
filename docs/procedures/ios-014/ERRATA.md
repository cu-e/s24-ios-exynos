# IOS-014 errata

`evidence.json` carries `recorded_at` 2026-11-12T17:58:30+00:00. The clock read 17:57:53 UTC when `task done IOS-014` accepted it, so the value is
about 35 seconds ahead of the real time it was written. It was not corrected afterwards because the registry holds the evidence hash and a changed
file fails `lab.py validate`. The content of the evidence is unaffected.
