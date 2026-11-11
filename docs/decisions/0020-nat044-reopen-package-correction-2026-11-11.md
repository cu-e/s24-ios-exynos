# 0020 — Reopen NAT-044 to correct its RECOVERY package (2026-11-11)

Status: recorded by `claude-nat044-20261111-resetimg` under decision 0019 (owner full-automatic mode); the owner was not asked.
It authorizes only the registry reopen of NAT-044 and the correction below. It touches no device.

## What was wrong

NAT-044 was closed with evidence (`docs/procedures/nat-044/evidence.json`, commit c25bea2) whose package step packaged the loader-only
`Image` (217088 bytes) of each reset canary into a RECOVERY candidate. Runs 001-009 and NAT-036 packaged `Image.payload` (the loader
followed by the XNU payload and its ADT, 21771872 bytes for NAT-044); the loader checks that payload's header, so a RECOVERY without it
would not be the run-006 family image. The mistake was found while pinning the NAT-048 session driver to the package: the package's
`source_image_sha256` was the hash of `Image`, not of `Image.payload` as in `artifacts/nat-036/package-001/package.json`. No test looked
at the package, which is why 46 tests and 46 mutants did not catch it.

## Correction

A packaging script `docs/procedures/nat-044/package.py` packages `Image.payload`, verifies the payload verbatim at the image offset
and writes one record; a test and a mutant now cover it; the package is rebuilt as `artifacts/nat-044/package-002`; a new evidence
record `evidence-002.json` supersedes `evidence.json` (kept unchanged, as the registry's reopen history keeps its hash). The
`artifacts/nat-044/package-001` directory stays on disk as the record of the wrong package and must not be used.
