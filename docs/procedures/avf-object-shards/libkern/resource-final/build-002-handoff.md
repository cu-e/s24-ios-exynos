# VM-014 grant31 actual libkern77 handoff

Original owner `codex-guest-exec-20261106-cw` executed exactly one new
`VMLIBRESOURCEFINAL-002` attempt under root grant31 in branch
`team/vm-014-resource-final-20261106`. The separate source plan remains
`83581cb34eb526f32c609beb4910dd86a90723b34121460593b4d03f5cf2ab17`;
root explicitly authorized its unchanged source authority for the new actual
experiment and fresh `resource-final/build-002` output.

The exact root command used canonical frozen EV9929 with the unchanged
1,200-second launcher directly through `python3.12 -s`. The actual controller
was PID 170726, start token 59872737, tool session 4171. The outer command
returned exit 0. All 77 commands and objects passed; all command resource
qualifications passed, with no command accounting errors, top-level error or
reservation-release error. Input binding remains `295e6edab63199b6ee1bcd245d43ede66dcb1c1429edc599389bc53f10307406`.

The raw capsule at
`artifacts/avf-object-shards/libkern/resource-final/build-002/evidence.json`
has SHA256 `e18f2ca1fd6420b010a6d47174855f19f5e66f81a63ce1ad08cdb8275263f310`.
The actual execution plan has SHA256
`80cdd0d41e0ea5b034c6f50eba50a66bec6a61f9f7ed449083db1b3b5b6148c2`.
The conventional [result](build-002-result.json) binds the exact command,
root grant, approval, allocation, source and actual plans, raw capsule, log,
provenance, resource observations and [cleanup receipt](build-002-cleanup.json).

Controller exec-image high water was 178,458,624 bytes; maximum combined owned
RSS was 274,001,920 bytes, under the 536,870,912-byte cap. Maximum observed
project RSS in this executor's samples was 789,696,512 bytes and project swap
was zero. These samples do not establish whole-wave peaks or attribute host
swap activity. The maximum child elapsed time was 4.581121466995683 seconds,
under the 120-second child deadline. The completed VM-014 reservation and
current PID/start identities, retained sessions and descendants yielded zero
live owned survivors. The worker did not release the global queue.

Preserve grant30's `VMLIBRESOURCEFINAL-001` precompiler refusal and build-001
unchanged. Preserve the original 75 passes / two genuine Firehose-header
failures and the later old77 object passes with incomplete OSKext post-child
accounting. The new experiment adopts none of those objects or old keys.

Next: independent bounded review by CN, then root/integrator acceptance and
fresh common/publication checks. VM-014 remains open under its original
owner. This packet grants no rerun, compilation, global release, common test,
publication, task closure, full kernel link, QEMU or device operation.
