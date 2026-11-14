# NAT-171: how stock Android sets the CPU cluster frequency on s5e9945

Evidence kind: source-review only. No device, ADB, MMIO or IPC was used.
Source: `references/s24-linux` at `417484173abc2c4fa93e738ea82ad9f2e84911b1`
(Samsung e1s kernel). Paths below are relative to that tree. Line numbers were
read with `git show HEAD:<path>`.
**S** = the source states it. **I** = inference, not yet checked on the phone.

The E1S path is Samsung ACPM IPC. The Qualcomm EPSS path behind
`redwood_cpufreq` `cpufreq=1` has no counterpart here and must never run on E1S.

## 1. Cores, clusters, domain of cpu0

- **S** `arch/arm64/boot/dts/exynos/s5e9945-cpu.dtsi`:
  - The `cpu-map` (134-173) has four clusters: cluster0 = cpu0-3,
    cluster1 = cpu4-6, cluster2 = cpu7-8, cluster3 = cpu9. The matching
    `#define`s are at 45-49.
  - cpu0 is `arm,heyes` (Cortex-A520) with `reg = <0x0 0x0000>` (175-184).
    cpu4-6 are `arm,hunter-lf` (217...), cpu7-8 are `arm,hunter-hf` (247...)
    and cpu9 is `arm,hunter-elp` (267).
- **S** cpu0's DVFS domain is `exynos-cpufreq/cpufreq_domain0: domain@0`
  (450-491):
  - `sibling-cpus = "0-3"`
  - `cal-id = <ACPM_DVFS_CPUCL0>`
  - `dm-type = <DM_CPUCL0>`
  - `min-freq = <400000>`
  - `fast-switch`
  - `pm_qos-booting = <1440000>`
  - `freq-table`, 400000-2112000 kHz with 19 entries, including 1959000 (472-490)
- **S** `ACPM_DVFS_CPUCL0 = 0x0B040002` (`include/dt-bindings/clock/s5e9945.h:318`).
  This is `ACPM_VCLK_TYPE 0x0B040000` (`drivers/soc/samsung/cal-if/cmucal.h:58`)
  plus index 2. `GET_IDX` = `id & 0xFFFF` (cmucal.h:39,223), so the index sent
  to firmware is **2**. The enum order MIF,INT,CPUCL0,... is at
  `cal-if/s5e9945/acpm_dvfs_s5e9945.h:4-38`, and the vclk named "CPUCL0"
  (fine-grain=1) is at line 43.
- **S** `DM_CPUCL0 = 0x02` and `DM_DSU = 0x08`
  (`include/dt-bindings/soc/samsung/s5e9945-dm.h:17,23`). In the DVFS-manager
  node (`s5e9945-dm.dtsi:21-27`), `cpufreq_cl0` has `available = "true"`,
  `cal_id = <ACPM_DVFS_CPUCL0>` and `fast_switch`.
- **S** The DSU (cluster-shared L3) is a separate domain, `ACPM_DVFS_DSU`
  (0x0B040008, index 8; s5e9945.h:324). Its table runs 288000-2016000
  (`s5e9945-cpu.dtsi:885-912`). The `dm-tables/lit_dsu_perf` table
  (633-660) gives the DSU minimum per CPUCL0 step, e.g. 1440000 -> 960000 and
  2112000 -> 1392000.
- **S** CMU_CPUCL0 is at 0x1DC40000 (`s5e9945.dts:185`;
  `cal-if/s5e9945/cmucal/cmucal-sfr.c:17`). PLL_CPUCL0 PMS lives in PLL_CON3 at
  +0x10c (sfr.c:3166): ENABLE is bit 31, MDIV bits 16-25, PDIV bits 8-13 and
  SDIV bits 0-2 (sfr.c:18363-18366). The OSCCLK is 76.8 MHz
  (cmucal-node.c:6516).
- **S** The kernel PLL rate table for CPUCL0 is empty (cmucal-node.c:46-47).
  Per-level PMS values come from ECT/firmware, not from the kernel.

Build configuration, all **S**, in `arch/arm64/configs/e1s_defconfig`:

| Option | Setting | Line |
|---|---|---|
| `ARM_EXYNOS_CPU_FREQ` | m | 656 |
| `EXYNOS_ACPM` | m | 6668 |
| `EXYNOS_DVFS_MANAGER` | not set | 6670 |
| `EXYNOS_ESCA_DVFS_MANAGER` | m | 6671 |
| `ACPM_DVFS` | m | 6672 |
| `ECT` | m | 6676 |
| `EXYNOS_ESCA` | m | 6697 |
| `EXYNOS_ESCAV2` | not set | 6698 |

Because ESCAV2 is off, every `#if IS_ENABLED(CONFIG_EXYNOS_ESCAV2)` below takes
its `#else` branch.

## 2. Call path to hardware: ACPM IPC only, no CMU writes by the kernel

### Slow path

This is the one exynos-cpufreq uses for this device tree.

1. **S** In `drivers/cpufreq/exynos-cpufreq.c:522-537`, `exynos_cpufreq_target()`
   calls `scale_slowpath()` when `domain->dm_list` is empty.
   - `init_dm()` (929-1000) only fills that list from a `dm-constraints` child.
     No s5e9945/e1s DTS has `dm-constraints` (grep across `arch/arm64/boot/dts`),
     so the list stays empty (**S** for the DT, **I** for the runtime result).
2. **S** `scale_slowpath()` (307-350) calls
   `cal_dfs_set_rate(cal_id, kHz)` at line 328.
3. **S** In `drivers/soc/samsung/cal-if/cal-if.c:99-122`: `IS_ACPM_VCLK(id)` is
   true, so it calls `exynos_acpm_set_rate(GET_IDX(id)=2, rate, false)`. No
   `vclk_set_rate` or CMU write happens. On success it only caches `vrate`.
4. **S** In `drivers/soc/samsung/cal-if/acpm_dvfs.c:26-64`, a 16-byte message is
   sent with `acpm_ipc_send_data()` (`#else` branch, line 55), with
   `response = !fast_switch = true`:

   ```
   cmd[0] = 2                    /* domain index; transport ORs seq into bits 16..21 */
   cmd[1] = target rate in kHz
   cmd[2] = FREQ_REQ = 0         /* acpm_dvfs.h:20; FREQ_REQ_FAST = 7, MARGIN_REQ = 2 */
   cmd[3] = APM peri-timer value, or 0 if it reads 0xFFFF
   ```

   - Channel = `acpm_dvfs.ch_num`. `exynos_acpm_dvfs_init()` (374-395) reads it
     from the cal_if node's `acpm-ipc-channel = <0>` (`s5e9945.dts:190`; node set
     by `cal_if_init` -> `exynos_acpm_set_device`, cal-if.c:689, 766).
   - **I**: this assumes the cal_if probe runs before `exynos_acpm_dvfs_init`,
     as the register order at cal-if.c:760-766 suggests.
5. **S** Transport, in `drivers/soc/samsung/acpm/acpm_ipc.c`:
   - `acpm_ipc` is the APM instance (`is_mailbox_master = true`,
     `is_apm = true`; `acpm.c:465-469`, `acpm_ipc.c:1153-1154`).
   - Its mailbox is 0x12B90000 and its SRAM is 0x2055000 (size 0x3A000), with
     initdata at +0x9D00 and `interrupt-ch = <0>`
     (`s5e9945-acpm.dtsi:29-51`). The IRQ is GIC SPI 344
     (`INTREQ__MAILBOX_APM12AP`).
   - The send sequence (593-763) has these steps:
     - wait for a free TX slot;
     - pick a 6-bit seq in 1..63 and OR it into `cmd[0]` bits 16..21
       (669-670; `ACPM_IPC_PROTOCOL_SEQ_NUM = 16` in
       `include/soc/samsung/acpm_ipc_ctrl.h:22`);
     - copy the message to `tx_base + size*front` and write `front+1`;
     - write `(1<<ch)<<16` to INTGR0 (+0x08) (391-398).
   - For a polling channel, it then polls INTSR1 (+0x28) bit `ch` and looks in
     the RX queue for a slot whose seq matches (436-501, 684-713).
   - Channel 0 is an interrupt channel, so Linux waits on the IRQ completion
     instead (714-725).
   - On timeout Linux dumps state and expires the watchdog (730-753).
   - Queue geometry comes from SRAM `initdata->ipc_channels`, and TX/RX are
     swapped for the AP (962-1017). The repo's NAT-123 client already does this
     for channel 2.

### Fast path

This path is used when the governor fast-switches.

1. **S** `exynos_cpufreq_fast_switch()` (539-572) calls `DM_CALL(DM_CPUCL0, &freq)`.
2. **S** In `drivers/soc/samsung/dm/exynos-esca-dm.c:1200-1237`, because
   `fast_switch` is set, DM_CALL makes two calls:
   - `cal_dfs_set_rate_fast()` sends the same 4 words with `cmd[2] = 7`
     (FREQ_REQ_FAST) and no response. It goes on the **APM** channel
     `fast_ch_num = 11` (dm.dtsi:206-208), which is registered with
     `acpm_ipc_request_channel` (esca-dm.c:958-965) and
     `exynos_acpm_set_fast_switch` (acpm_dvfs.c:347-351).
   - `exynos_acpm_dm_set_freq_async()` (76-90) sends a DM message on
     `dm_req_channel = 7` (dm.dtsi:200-202) through `esca_ipc_send_data`. That
     goes to the **ESCA/ASM** mailbox at 0x12AB0000 (SRAM 0x208F000 size
     0x8000, initdata +0x6800; acpm.dtsi:243-259; `esca.c:175-179`
     `is_mailbox_master = false`).
3. **S** Completion comes back as a callback:
   - on channel 11, `cmd[1]` = domain and `cmd[2]` = freq (esca-dm.c:373-414);
   - or on `dm_sync_channel = 5` as `DM_FREQ_SYNC` (339-371).
4. **S** The ESCA `dm_scaler` (exynos-cpufreq.c:428-448) only records the new
   frequency. It writes no hardware.

### DM message layout

**S** `include/soc/samsung/exynos-dm-acpm-ipc.h`:

- The message is 16 bytes (37-75):
  - byte0 = msg
  - byte1 = dm_type
  - u16 fw_use (the transport's seq goes here)
  - three u32 payload words
- msg IDs (17-35): `DM_DATA_INIT 0`, `DM_REG_CONST_* 1-3`,
  `DM_POLICY_UPDATE 4`, `DM_FREQ_REQ 5`, `DM_FREQ_SYNC 6`,
  `DM_CHANGE_FREQ_TABLE 14`.
- At init, Linux sends `DM_DATA_INIT(min, max, cur)` (esca-dm.c:187-198, from
  cpufreq `init_dm` 951-952). On every policy change it sends
  `DM_POLICY_UPDATE(min, max)` (151-160, from cpufreq verify 512). Both go on
  `dm_channel = 1` (ESCA, with response).

**Conclusion (S):** the kernel never writes CPUCL0 CMU or PLL registers. It only
sends ACPM/ESCA IPC messages. The firmware does the PLL and voltage sequencing
(**I** for what the firmware does internally).

## 3. Frequency table and voltage source

- **S** Max and min come from the vclk, which is filled from ECT. Then the DT
  `min-freq` raises the minimum, and a DT `max-freq` (absent here) could lower
  the maximum (exynos-cpufreq.c:1506-1512). DT `freq-table` entries outside
  [min,max] are dropped (1514-1538).
- **S** ECT is a binary in reserved DRAM, `ect_binary` at PA 0x90000000, size
  0xC4000 (`s5e9945-rmem.dtsi:141-144`; `s5e9945-power.dtsi:21-24`;
  `ect_parser.c` probe 2623-2656, signature "PARA" 25, header parse 2509-2569).
  The kernel does not fill it, so the boot loader must place it (**I**).
- **S** `vclk_bind()` reads the ECT "DVFS" domain named "CPUCL0"
  (`vclk.c:432-533`). It takes max/min, `boot_level_idx`/`resume_level_idx`
  (parser v2+, `ect_parser.c:67-128`) and a per-level list of values. A GEN
  table "MCPUCL0", keyed by ASV table version, can override max/min/boot/resume
  (vclk.c:452-473, 508-517).
- **S** Voltages come from the fvmap in APM SRAM: `fvmap_offset = <0x30400>`
  (acpm.dtsi:23; acpm.c:54-69), so 0x2055000 + 0x30400 = 0x2085400 (**I**
  arithmetic).
  - Header struct is at `include/soc/samsung/fvmap.h:53-75`; each entry is
    rate:24 (kHz) and volt:8 (fvmap.h:88-91), with a volt step of 6250 µV
    (fvmap.c:18).
  - The kernel copies it (fvmap.c:415-510; the rate/volt copy at 498-506 sits
    under `CONFIG_EXYNOS_DEBUG_INFO`, which is `=y`, defconfig:6645). It
    interpolates per-OPP volts (321-366) **only for the OPP/energy model**
    (exynos-cpufreq.c:1558-1592).
- **S** The kernel never programs a CPU voltage:
  - exynos-cpufreq.c contains no `regulator` call (grep count 0);
  - the only voltage-related IPC is `MARGIN_REQ`, an offset (acpm_dvfs.c:126-166),
    sent when the `margin_*` / `volt_offset_percent` module parameters or the
    `percent_margin` sysfs files are set (fvmap.c:465-474, 190-219).
  - The power-rail debug map sends VDD_CPUCL0 to firmware DVFS domain 35,
    "DVFS_IP_CPUCL0" (acpm.dtsi:128,152-154). This is a different numbering
    from cal index 2 (**I**: the firmware maps logical domain 2 to a
    rail/IP domain itself).
- **S** fvmap `members` decode to the CMU SFR addresses the firmware touches,
  minus 0x90000000 (fvmap.c:476-490). That is a hint at the firmware's address
  view (**I**).

## 4. Boot/default frequency, min/max

- **S** Linux reads `boot_freq` and `resume_freq` from the vclk (ECT boot/resume
  level, or the GEN row). If the value is out of range it falls back to min
  (exynos-cpufreq.c:1600-1606; vclk.c:398-430). These numbers are **not** in
  source. Android prints them at probe as
  `CPUFREQ of domain0 boot freq = ... resume freq = ...` and
  `max freq ... min freq ...` (1259-1263).
- **S** DT gives a min of 400000. The max is the ECT maximum, which can be at
  most the top table entry, 2112000.
- **S** Boot boost: for 70 s after boot, min=max=`boot_qos`.
  - `boot_qos` is the domain max unless the `clk_limit_jig` module parameter is
    set; only then does `pm_qos-booting = 1440000` apply (1343-1362).
  - The boost is released by delayed work (1405-1407).
  - Stock Android therefore runs cluster 0 at its ECT max for the first ~70 s
    (**I** that the jig parameter is unset on the owner's phone).
- **S** The default governor is `cpufreq.default_governor=energy_aware`
  (`s5e9945.dts:114`). Whether it uses `target` or `fast_switch` was not
  reviewed (**I**).

## 5. Minimal stock-parameter steps for a non-Linux kernel

**Dependencies:**

- the APM mailbox 0x12B90000 and APM SRAM 0x2055000-0x208EFFF, mapped as
  device memory;
- parsing initdata at SRAM+0x9D00 to find the channel whose `id == 0` (and
  check element size 16 and the queue type), using the existing NAT-123 decoder;
- ECT parsing is **not** needed to issue the request, because the firmware owns
  the tables (**I**);
- the fvmap is needed only to choose a level that this chip actually exposes.

**Step A (read-only).** This should come first and needs a per-image decision
under 0044/0052/0061.

- Decode the channel 0 and channel 11 descriptors.
- Read fvmap entry 2. Assuming a 52-byte header (49 bytes padded to 4; **I**
  from the C layout), it sits at 0x2085400 + 2*52. Read its
  `num_of_lv` / `o_ratevolt` and the rate/volt list, and do the same for DSU
  (index 8).
- Read PLL_CPUCL0 CON3 at 0x1DC4010C. FOUT ≈ 76.8 MHz * M / (P << S), plus any
  fractional part (**I**; fractional register not identified, `ra.c:362-415`,
  `cal_data.c:78`).
- No IPC sends.
- Before any native work, these Android-userland reads give the ECT-derived
  numbers (`boot_freq` / `max_freq` / `min_freq`):
  - Android dmesg lines from exynos-cpufreq.c:1254-1274;
  - `/sys/devices/system/cpu/cpufreq/policy0/{cpuinfo_max_freq,cpuinfo_min_freq,scaling_available_frequencies}`.
  - Do not use debugfs (clk_summary crash precedent).

**Step B (one IPC message).** This matches stock `cal_dfs_set_rate`.

- On APM channel 0, send `{0x00000002 | seq<<16, kHz, 0, 0}`:
  - kHz must be a level present in both the DT table and the fvmap. Moderate
    first choice: 1440000, the stock jig boot value, rather than 2112000.
  - Ring INTGR0 `(1<<0)<<16`.
  - Poll INTSR1 bit 0 and the RX slot with the matching seq, with a bounded
    deadline and **no** retry storm.
- Verify through the CON3 readback and a CNTVCT-timed loop.
- The stock fast variant (channel 11, `cmd[2] = 7`, no response, paired with
  `DM_FREQ_REQ` on ESCA channel 7) is not needed for a single change.

**Risks and open questions:**

1. **(open)** Will the firmware honour FREQ_REQ when no `DM_DATA_INIT` /
   `DM_POLICY_UPDATE` was ever sent (Linux sends both on ESCA ch 1)? The
   firmware DM policy state left by S-Boot is unknown, so the request may be
   clamped or ignored. A readback after Step B resolves this.
2. **(open)** The response word semantics: whether `cmd[1]` of the reply carries
   the applied frequency or an error. This is not in the kernel source.
3. Channel 0 is an *interrupt* channel for Linux (acpm.dtsi:50; `channel_init`
   1005-1011 unmasks it). Reaching SPI 344 with no handler, or leaving it
   unmasked, could fault our kernel. Check INTMR1 (+0x24) before sending.
4. Thermal: stock cools via domain0 (`s5e9945-thermal.dtsi:391`), and
   ACPM/ESCA thermal firmware may also cap. Our kernel has no thermal loop, so
   the run must be time-bounded at a moderate level.
5. DSU coupling: stock expects the DSU minimum to follow CPUCL0
   (lit_dsu_perf). Raising only CPUCL0 may give less speed-up than expected.
   Under ESCA DM the kernel sends no DSU `cal_dfs_set_rate` at all
   (exynos-dsufreq.c:221-226 is under `CONFIG_EXYNOS_DVFS_MANAGER`, which is off).
6. Wrong-mailbox risk: the ESCA mailbox also has a channel 0
   (acpm.dtsi:236-241). DVFS FREQ_REQ must go to the **APM** mailbox
   (`acpm_ipc_send_data`, acpm_dvfs.c:55).
7. Never write a PMIC buck or CMU PLL directly for the CPU. The stock kernel
   never does, and the PMS and voltage tables are firmware-owned.
8. Volatility: a reboot into Android re-initializes DVFS (**I**). Restore
   follows the normal stock-RECOVERY procedure.

## 6. Android userland readback (2026-11-14, after the NAT-170 restore)

`adb shell cat /sys/devices/system/cpu/cpufreq/policy0/*`, read-only, no root, no debugfs (**S**, measured on this phone):

| File | Value |
| --- | --- |
| `related_cpus` | 0 1 2 3 |
| `cpuinfo_min_freq` / `cpuinfo_max_freq` | 400000 / **1959000** kHz |
| `scaling_available_frequencies` | 400000 576000 672000 768000 864000 960000 1056000 1152000 1248000 1344000 1440000 1536000 1632000 1728000 1824000 1920000 1959000 |
| `scaling_cur_freq` (idle Android) | 672000 |
| `scaling_governor` | energy_aware |

The DT entry 2112000 is not exposed: this chip's ECT maximum is 1959000. A `dmesg` grep for the probe lines returned nothing; the
ring had rotated.

Other measured facts from our own logs (NAT-170 kernel text, the NAT-123 ACPM client's channel scan):
- APM channel 0 is `type=1 len=8 elem=16 poll=1`, the same layout as channel 2, which our client already uses for the PMIC;
- channel 11 is `type=1 len=14 elem=16 poll=0`.
So a channel-0 `FREQ_REQ` can use the proven polled transport.

Plan: NAT-172 (host) builds an image that logs PLL_CPUCL0 CON3 and a timed dependent-add loop, then sends one stock FREQ_REQ
`{2, 1959000, 0, 0}` on APM channel 0 and logs the reply and the readbacks. NAT-173 runs it.
