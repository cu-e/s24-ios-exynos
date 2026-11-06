# Root92 actual metadata attempt 001

The exact root-granted `STR032META-001` attempt is a whole **FAIL**. Raw host-test
`generate-1/evidence.json` SHA256
`5fa14cf3f4c7ff19867e6cf5caab49ecfa02c9111e841a79aee34b25a72bc15d`
retains 24 actual command records, no survivors, released owned lease, and no
resource/cancellation stop. The outer invocation exited 1. No author rerun ran.

The first 21 genuine commands exited 0: original export/alias generation, nine
newvers Info updates, nine component symbolsets and the combined XML. Their 21
actual products are bound by `partial-generated-001.json`. All 17 source export
inputs and their order are retained; independent readback checked the generated
export/alias source-line closure, original Info authority/version and combined
nine-component order/data. The final binary symbolsets input is still absent.
All 37 ABI obligations remain separate and unresolved by metadata generation.

The next two actual libplist datatype-control conversions exited 0. Read-only
assessment verified their XML/binary/XML typed equality; these exact successful
products can be adopted without conversion replay. This does not complete the
portable serializer qualification.

The failing command was `reject-bad-xml`: actual exit **3**, exact diagnostic
`ERROR: Could not parse plist data (-3)`, and **no output**. Libplist rejected the
malformed input correctly. The original plan incorrectly allowed only exits 1/2;
its caller therefore rejected this result and preserved whole FAIL. This is an
expected-exit policy error, not a permissive parser. No diagnostic or old plan
is changed after execution.

Upstream libplist tag2.6.0 resolves to commit
`2117b8fdb6b4096455bd2041a63e59a028120136`. The exact source files are cached with
Git blob SHA1/SHA256 under `artifacts/e1s-development-link-metadata/libplist-source-2.6.0`:
[`tools/plistutil.c`](https://github.com/libimobiledevice/libplist/blob/2117b8fdb6b4096455bd2041a63e59a028120136/tools/plistutil.c)
maps `PLIST_ERR_PARSE` to exit3; its public header defines that error as -3.
The installed exact ELF/DSO hashes and RPM `libplist-2.6.0-5.fc43.x86_64` are bound;
the upstream source explains the independently observed installed behavior,
without claiming a reproducible Fedora binary build or SDK authority.

That same source handles an unsupported output-format argument by printing an
exact diagnostic and usage, then returning 0 before conversion or output opening.
A prospective negative control must record this raw zero exit honestly, require
the exact argument-refusal diagnostic/usage and absent output, and mark
`expected_rejection` separately from conversion success. Parse negatives require
exact exit3/parse diagnostic/absent output. No generic nonzero allowance, wrapper,
Python serializer or weakened negative is needed.

The owner source-review assessment preserves this whole failure and scopes the
21 successful outputs explicitly; it does not relabel raw host-test evidence.
The 167 bounded read-only checks are in `review-001/assessment.json`. Next is an
independently reviewed serializer-only continuation over hash-bound actual001
inputs. Successful genuine generators and positive conversions will not rerun.
Native-plutil oracle, portable final qualification, SDK/provider ABI, final image,
runtime and hardware remain unqualified.
