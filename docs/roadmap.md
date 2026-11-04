# Stages and transition criteria

| Stage | Verifiable outcome | What it does not establish |
|---|---|---|
| 0. Foundation | Registry, sources, tooling tests and instructions | Execution on the phone |
| 1. Inventory | Dated facts from the actual device | Root/KVM access or recovery |
| 2. Host | Reproducible builds and structurally valid images | S24 boot |
| 3. Android GPU | Local measurements and controlled APK termination | XNU driver compatibility |
| 4. Recovery/control | Documented, then tested return procedure | Guaranteed return after every failure |
| 5. Native entry | Real XNU log and Android recovery | iOS userland execution |
| 6. Native services | Separately verified RAM root, input and storage | A complete phone OS |

state/lab.json defines the current phase. A written plan or an upstream screenshot does not complete a task.

The registry contains the backlog and dependencies. Continue with RES-001, then RES-002/BLD-001. DEV-001 completed the initial authorized ADB inventory on 2026-11-05. Do not estimate iOS completion percentage from the number of closed tasks.
