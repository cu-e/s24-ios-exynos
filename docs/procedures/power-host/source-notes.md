# PWR-003 source qualification

Samsung pin: 417484173abc2c4fa93e738ea82ad9f2e84911b1.
E1S pin: c8860decc62c6d6180e609036d027a2997972420.
Exact paths, direct pinned URLs, Git blobs and SHA256 are in the source profile.
These are declaration/source facts and synthetic host evidence, not phone data.

| Input | Established source meaning |
| --- | --- |
| `exynos_acpm_tmu.h` | Genuine 16-byte request/response/union, signed 8-bit return, unsigned 8-bit temperature, opaque status |
| `exynos_acpm_tmu.c` | READ_TEMP helper builds type 2/zone input, invokes transport, copies temp/status; it returns 0 and does not propagate response.ret |
| `exynos_tmu_v2.c`, `exynos_tmu.h` | Actual conversion is `*temp = acpm_temp * MCELSIUS`, macro 1000; conditional CONFIG_ECT parser can load AP_THERMAL/PIDTM data |
| `acpm_dvfs.c` | Four-word active MIF/INT QoS notification, word 1 kHz and word 2 domain 0/1; measured-clock FREQ_GET helper compiled out |
| `exynos_pm_qos.h` | Genuine callback target prototype takes s32; DEFAULT_VALUE=-1 is not a frequency. This prevents unsigned 0xffffffff from becoming a huge Hz request |
| `s5e9945/acpm_dvfs_s5e9945.h`, `cmucal.h` | 33 sequential ACPM IDs starting 0x0b040000, original CMUCAL list and order; selected domain declarations equal the EVT0 header blob at this pin |
| `framework.h`, exact E1S 0007 patch | Conditional S5E9945/ACPM channel_info 32 bytes and ipc_channel 48 bytes, matching donor stride 48; this does not identify current firmware |
| `fvmap.h`, `fvmap.c`, base ACPM DTS | 52-byte FV header, rate/voltage entry 4 bytes, 8 KiB source copy and STEP_UV 6250 encoding; source fvmap_offset 0x30400, actual firmware table unavailable |
| Base thermal DTS | Source IDs 0..7: BIG, MIDH, MIDL, LITTLE, G3D, ISP, NPU, CP. This is not Linux sysfs numbering or fitted sensor discovery |
| E1S board PM includes/generated retail overlay | Source board context includes separate external PMIC/thermistor data. An overlay alone is not a fully resolved/matched runtime DT/calibration table |

The owned API never calls any native source function. The test oracle compiles
genuine declarations and selected unchanged functions under explicit host
adapters: synthetic TMU reply copy and QoS capture with the genuine signed
prototype. No native IPC sender or real QoS update is linked. Original notices
remain in complete primary source copies and generated oracle headers.

Important gates before a native observation/backend or policy can use this:

- A successful TMU helper return 0 does not establish actual IPC delivery. Its
  sender logs errors but returns void, and the helper does not check signed
  firmware return. A request-shaped buffer can resemble a 0-degree reply.
  The real backend must propagate transport/firmware errors and correlate the
  actual response, rather than merely labeling the current host ticket OK.
- The selected TMU sender references ESCA; legacy E1S PMIC ACPM transport is a
  distinct service. Shared 16-byte shapes or repeated channel numbers do not
  establish interchangeable firmware endpoints or mailbox ownership.
- Static DTS trips, ECT selection, runtime FVMAP contents, silicon binning,
  ASV/voltage margins and sensor calibration are distinct inputs. Public
  threshold/voltage constants must not be promoted to safe policy values.
- Signed QoS representation bounds are not physical frequency bounds. Only
  nonnegative s32 requests normalize here; -1/default and negative encodings
  are unavailable/unsupported. No hardware frequency is measured or selected.
- FVMAP admission validates only the selected copied extent. It does not prove
  table contents, reported-domain association, firmware identity or suitability
  for the fitted device. It intentionally exports no voltage/frequency codes.
- Host tickets/timestamps are caller metadata. Actual firmware sequence and
  clock correlation, native liveness, external backend shutdown and safe
  hardware Stop remain unqualified. Host Stop only invalidates observations.

The exact BYH3 S9 BSP/firmware/DT/calibration inputs are unavailable to this task.
Native thermal protection, DVFS/charging/suspend policy, PHY/PMIC access, native
kernel execution and Apple-service compatibility remain outside this result.
