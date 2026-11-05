# Intentional descriptor byte mutation

The raw descriptor-whitespace negative fixture deliberately contains an extra
blank line. The parsed object is unchanged, and the real preflight rejects the
changed descriptor bytes with exit 1. Its source, bytes, report and SHA256 remain
unchanged. The first post-staging Git whitespace check consequently returned 2;
that output is preserved in intentional-whitespace-check.json. The scoped
.gitattributes exception applies only to this negative vector. A fresh Git
check passes. No production file, historical witness, test result or original
review evidence is rewritten; no host tests are repeated for this metadata fix.
