# Mbed TLS component attribution

Minimal dependency closure of software AES from Mbed TLS3.6.7,
https://github.com/Mbed-TLS/mbedtls at
068ff080b369adfac81509f9b57b2afabaf82dc5. Copyright The Mbed TLS Contributors.
Apache-2.0 OR GPL-2.0-or-later; this project selects Apache-2.0 for this component.
Complete upstream LICENSE and original per-file notices are preserved.
provenance.json pins every reused byte; the sole common.h include-only port
patch and both original/local hashes are preserved in common-freestanding.patch. No Apple corecrypto implementation is
redistributed. xts.c owns the interface glue and adapts XEX/GF progression from
this revision's library/aes.c; that source's attribution and license apply to
the adapted construction. profile.h is project configuration.
