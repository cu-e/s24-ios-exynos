# ADR 0001: prioritize work on top of Android

Date: 2026-11-05. Status: accepted as the owner's initial constraint.

The owner uses the S24 daily and wants to interrupt research without losing the current system. The exact e1s upstream is still before its first hardware boot and has no independent USB/network control plane.

Decision: prioritize host tooling and an Android userland probe. Do not run native work as a background loop. It requires a separate, measured recovery/control stage.

Consequence: graphics progress on Android supplies research material, not proof of a working XNU GPU driver. Fully autonomous return to Android is not promised.

Revisit after measured recovery and the owner's authorization for a new scope. A JSON toggle does not satisfy these conditions.
