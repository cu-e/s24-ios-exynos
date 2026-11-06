# Independent VM044 findings

## R1: final project-budget sampling failure can retain a passing command

Priority P1. Integrator INT002 discovered the retained witness; reviewer EQ independently inspected the actual command and accepted source. This is a prospective resource-qualification issue, not evidence that the object bytes are invalid or that a memory ceiling was exceeded.

Immutable witness: `worktrees/vm-014-profile-v1-20261106/artifacts/avf-object-shards/libkern/profile-v1/build-001/evidence.json`, SHA256 `31d820a4413a8a5711ac1e20481bd1086576cd75f9e7eacda7dbd85376698c00`. Command index 12 (OSKext.cpo), exit code 0, has `project_after_error = "ValueError('Project budget lock acquisition timed out')"` and `outcome = "pass"`. The physical source is AF193, SHA256 `af193e91ef5a7c24cbba0f797415cc1f2944673e62aadc6d4ace4511810582e0`.

In `run_child`, the exception handler around the final `budget.sample()` stores only `project_after_error`. It leaves `stop_reason` unset. The outcome expression then selects `pass` from the zero child exit code, allowing subsequent object acceptance despite an unqualified final project-resource boundary. Earlier in-child sampling errors already set `project-admission` and defer the command.

Requested correction: preserve the real child exit, logs and object bytes, but fail closed for prospective qualification when the final budget sample fails. Exercise a real tiny child and real finite lock refusal at this boundary. The original capsule and its source must remain unchanged; no compiler replay or retroactive claim is required. Sent to author EP and root before the source freeze.
