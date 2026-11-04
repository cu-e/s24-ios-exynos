# S24 iOS / Exynos — Kanban

> Generated from state/lab.json. Use the CLI; do not edit this board or its task cards.

Phase: **device baseline captured; Android-preserving research**. Snapshot: 2026-11-04T22:26:04+00:00.

Registry SHA256: `588b1843c6df842ef692869c6187f4a7ab159ecdf3a821c7a6853b6f38bccf7d`. Run `python3 tools/lab.py board --check` to detect stale files.

[Workflow](docs/planning.md) · [All task details](planning/README.md) · [Machine view](state/board.json) · [Status](STATUS.md)

| Ready (1) | In progress (0) | Blocked (0) | Waiting (10) | Needs authorization (4) | Done (5) |
| --- | --- | --- | --- | --- | --- |
| [**RES-001**](planning/tasks/RES-001.md) · P50<br>Pin S24 upstream and document donor provenance<br>host · unassigned | — | — | [**RES-002**](planning/tasks/RES-002.md) · P50<br>Cross-check the e1s hardware map against primary sources<br>host · unassigned<br>Dependencies: RES-001 | [**GPU-003**](planning/tasks/GPU-003.md) · P50<br>Measure stock Vulkan on the S24 inside Android<br>android-app · unassigned<br>Scope not authorized: android-app; Dependencies: GPU-002 | [**LAB-001**](planning/tasks/LAB-001.md) · P80<br>Implement a file-based Kanban and agent coordination workflow<br>host · codex-coordination |
| — | — | — | [**BLD-001**](planning/tasks/BLD-001.md) · P50<br>Make the host loader and E1S delta build reproducible<br>host · unassigned<br>Dependencies: RES-001 | [**GPU-005**](planning/tasks/GPU-005.md) · P50<br>Compare the stock driver and Xclipse RADV in the test APK<br>android-app · unassigned<br>Scope not authorized: android-app; Dependencies: GPU-003, GPU-004 | [**FND-001**](planning/tasks/FND-001.md) · P50<br>Prepare and verify the project foundation<br>host · codex |
| — | — | — | [**TST-001**](planning/tasks/TST-001.md) · P50<br>Validate the boot package, ADT and memory boundaries on the host<br>host · unassigned<br>Dependencies: RES-002, BLD-001 | [**NAT-003**](planning/tasks/NAT-003.md) · P50<br>Run the first native BOOT session with logs and recovery<br>native · unassigned<br>Scope not authorized: native; Dependencies: NAT-002, BLD-001, TST-001 | [**DEV-001**](planning/tasks/DEV-001.md) · P50<br>Collect sanitized read-only S24 inventory<br>android-readonly · codex |
| — | — | — | [**GPU-001**](planning/tasks/GPU-001.md) · P50<br>Design an Android app for GUI/GPU measurements<br>host · unassigned<br>Dependencies: RES-002 | [**DRV-003**](planning/tasks/DRV-003.md) · P50<br>Validate minimal XNU drivers on hardware<br>native · unassigned<br>Scope not authorized: native; Dependencies: NAT-003, DRV-001, DRV-002 | [**DEV-002**](planning/tasks/DEV-002.md) · P50<br>Prepare an extended read-only technical profile collector<br>host · codex |
| — | — | — | [**GPU-002**](planning/tasks/GPU-002.md) · P50<br>Implement a minimal Android Vulkan probe<br>host · unassigned<br>Dependencies: GPU-001 | — | [**DOC-001**](planning/tasks/DOC-001.md) · P50<br>Make English the project and agent working language<br>host · codex |
| — | — | — | [**GPU-004**](planning/tasks/GPU-004.md) · P50<br>Validate a minimal Metal-to-Vulkan path on the host<br>host · unassigned<br>Dependencies: RES-001, GPU-001 | — | — |
| — | — | — | [**DRV-001**](planning/tasks/DRV-001.md) · P50<br>Prepare an STM SPI touch driver and host adapter<br>host · unassigned<br>Dependencies: RES-002 | — | — |
| — | — | — | [**DRV-002**](planning/tasks/DRV-002.md) · P50<br>Validate the read-only UFS/MCQ contract on the host<br>host · unassigned<br>Dependencies: RES-002, BLD-001 | — | — |
| — | — | — | [**NAT-001**](planning/tasks/NAT-001.md) · P50<br>Prepare a verifiable recovery plan for this exact S24<br>host · unassigned<br>Dependencies: RES-002 | — | — |
| — | — | — | [**NAT-002**](planning/tasks/NAT-002.md) · P50<br>Design control and return paths for a native test<br>host · unassigned<br>Dependencies: NAT-001, TST-001 | — | — |

## Claimed work and agent reports

Owner names identify cooperating agents, not authenticated processes. A recent report is not proof that an agent is running. Reports older than 30 minutes are marked stale at snapshot time; claims never expire automatically.

| Owner | Task | State | Last heartbeat (UTC) | Report | Progress / next step | Context |
|---|---|---|---|---|---|---|
| — | — | No claimed work | — | — | — | — |

## Recent activity

- 2026-11-04T21:45:51+00:00 · codex · task.add:DEV-002
- 2026-11-04T21:45:51+00:00 · codex · task.claim:DEV-002
- 2026-11-04T21:58:29+00:00 · codex · project.facts:DEV-001
- 2026-11-04T21:58:29+00:00 · codex · task.done:DEV-002
- 2026-11-04T21:58:29+00:00 · codex · task.done:DEV-001
- 2026-11-04T22:04:21+00:00 · codex · task.add:DOC-001
- 2026-11-04T22:04:21+00:00 · codex · task.claim:DOC-001
- 2026-11-04T22:07:58+00:00 · codex · project.language:English; user-requested translation, no new device measurements
- 2026-11-04T22:11:49+00:00 · codex · experiment.plan:LANGUAGE-001
- 2026-11-04T22:12:59+00:00 · codex · experiment.record:LANGUAGE-001
- 2026-11-04T22:12:59+00:00 · codex · task.done:DOC-001
- 2026-11-04T22:18:32+00:00 · codex-coordination · task.add:LAB-001
- 2026-11-04T22:18:32+00:00 · codex-coordination · task.claim:LAB-001
- 2026-11-04T22:22:57+00:00 · codex-coordination · task.update:LAB-001
  - LAB-001: Implemented generated Kanban/cards, atomic claim-next, owner reports, resume, priorities and path reservations; running behavioral checks
- 2026-11-04T22:25:00+00:00 · codex-coordination · task.refine:LAB-001 generated temporary-file exclusions
  - LAB-001: Implemented generated Kanban/cards, atomic claim-next, owner reports, resume, priorities and path reservations; running behavioral checks
- 2026-11-04T22:25:00+00:00 · codex-coordination · task.update:LAB-001
  - LAB-001: Initial 40 behavioral tests passed; added checks for overlapping-task races, partial publication and machine-view tampering
- 2026-11-04T22:25:00+00:00 · codex-coordination · experiment.plan:COORDINATION-001
- 2026-11-04T22:26:03+00:00 · codex-coordination · task.update:LAB-001
  - LAB-001: 42 tests, 99 local links and view consistency checks passed; original tasks/evidence and permissions preserved
- 2026-11-04T22:26:03+00:00 · codex-coordination · experiment.record:COORDINATION-001
- 2026-11-04T22:26:03+00:00 · codex-coordination · task.done:LAB-001
  - LAB-001: 42 tests, 99 local links and view consistency checks passed; original tasks/evidence and permissions preserved

Use a unique owner per agent session. Atomically take ready work:

```sh
python3 tools/lab.py task claim-next --owner agent-your-session --scope host
```
