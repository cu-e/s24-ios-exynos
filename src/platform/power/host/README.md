# Copied thermal and clock-request input admission

This project-authored C11 component validates owned copies of source-confirmed
inputs. It has no transport callback, MMIO, device operation, firmware request,
clock/voltage/charging/suspend policy, or hardware power/Stop operation. It is
host preparation for PWR-001, whose native dependencies remain unchanged.

`source-profile.json` records exact Samsung/E1S pins, Git blob/SHA256 identities,
units, selected declarations and unqualified inputs. Complete primary source
and generated genuine oracles stay in ignored evidence with original notices.
No full Samsung/E1S driver is added to tracked code and no blanket E1S license
grant is inferred from its containing XNU/APSL tree.

## Admitted input meanings

TMU accepts exactly 16 copied bytes under the pinned public s5e9945 profile.
The genuine Samsung response has type/return/zone/temp/status at offsets 4..8.
Only READ_TEMP type 2, signed return 0 and the selected source zone 0..7 pass.
The unsigned byte temperature is normalized with actual Linux MCELSIUS 1000.
Its representable 0..255 Celsius range is a wire fact, never a safety range.
Status and context/firmware fields are opaque; no healthy/safe interpretation
is made. Public SoC DTS names/IDs are checked against the recorded source
profile; they do not discover fitted sensors or matched board calibration.

The active ACPM MIF/INT callback receives four 32-bit words, takes request kHz
from word 1 and domain 0/1 from word 2, and updates a QoS request. Owned parsing
normalizes nonnegative signed 32 requests to Hz in 64 bits. The genuine target
prototype takes s32, so 0xffffffff is the DEFAULT_VALUE=-1 sentinel, not a
frequency; it returns unavailable. Other negative signed encodings are
unsupported. These are type/encoding rules, never physical frequency limits.
It never reports measured clocks. `exynos_acpm_get_rate` is inside `#if 0` in
the pinned source. Measured-clock and voltage observation kinds therefore
return unavailable. No frequency/voltage setting or safety limit is exposed.

The 33-domain ACPM enumeration and original CMUCAL table are qualified as a
source diagnostic only. `power_source_domain_id` maps that exact enumeration;
it is not firmware discovery, a clock measurement or an actuation capability.
The EVT0/non-EVT0 domain headers happen to share the exact blob at this pin;
that equality does not qualify all variant clock/calibration tables.

FVMAP admission inspects only metadata in an exact 8 KiB owned copy, using the
genuine 52-byte header, selected source index 0..32, nonzero level count and
four-byte rate/voltage entry extent. The extent must fit the copy and may not
overlap the dense 33-header prefix (an explicit owned admission restriction).
`reported_domain` is retained separately from `selected_index`: equality and
physical domain association are not assumed. The parser neither interprets
nor exports rate/voltage codes, selects a silicon bin, or modifies SRAM.
Source STEP_UV 6250 is an encoding fact, not a safe voltage recommendation.
Actual firmware table bytes, ECT/ASV binning and calibration remain unavailable.

## Availability and liveness

Use fresh/retired observer storage and serialize access. Do not alter policy
or state behind the API. `begin` creates a host epoch/generation ticket and
bounded application freshness deadline. It emits nothing and permits one
pending input. Generations never wrap. The ticket is not a firmware sequence;
a real backend must correlate its own delivery and preserve real error status.
It cannot identify stale firmware messages by merely stamping the current host
ticket on any copied bytes. No private native IPC protocol is invented here.

`accept` requires current ticket, monotonic sample/receipt times, explicit
transport availability and success, expected units and valid copied payload.
Missing transport, transport/firmware errors, bad units/length and expired input
invalidate observations. `read` returns unavailable/error and zero output;
callers must honor its result. A successfully delivered zero-degree wire value
can remain distinguishable from missing data through that result and valid
state. The pure byte decoder cannot prove that a request-shaped all-zero reply
was ever delivered: Samsung's original TMU helper returns0 despite logged IPC
errors and does not propagate response.ret. A real backend must fix that
provenance gap before claiming actual measurements, rather than treating the
helper's zero return as proof of transport success.

The caller chooses max_age_ns as an application freshness requirement. It is
not a guessed polling policy, thermal threshold, watchdog, hardware timeout or
safe failure limit. Deadline addition is checked for uint64 overflow. Reads
and replies at expiry become stale. Stop invalidates pending and accepted
host observations, prevents later updates and remains idempotent. It does not
stop a physical sensor, IPC request, firmware or controller, and cannot prove
hardware quiescence or a safe return to Android.

## Verification scope

The runner compiles genuine Samsung declarations, the unchanged TMU read
helper and Linux unit expression, and the unchanged MIF/INT callback under
explicit synthetic transport/QoS capture adapters. No real IPC/QoS callback is
linked. It verifies table order, source DTS selections, firmware-declaration
layout and FVMAP extents, then runs owned C malformed/unavailable/stale/unit/
error/overflow/Stop and guard controls under native ASan/UBSan with deliberate
fault controls. Owned code and genuine layouts also compile to ARM64 Mach-O;
no XNU link or ARM/device execution follows. One compiler runs at a time and
resident peaks are measured against 256 MiB.

Native thermal protection, firmware/calibration matching, clocks/DVFS, charging,
suspend/resume, safe actuation and Apple services remain separate PWR-001 gates.
