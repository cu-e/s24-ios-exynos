# MIG failure propagation

Base: markmentovai/bootstrap_cmds f337e600741638896fb6056ce87c6479f74b89a3, migcom.tproj/mig.sh. Preserve its Apple/CMU notices and repository APPLE_LICENSE; no project-wide license overrides those components.

The upstream shell front end pipes preprocessing into migcom and checks the pipeline status. Without pipefail, a failing preprocessor can be hidden by successful generation from partial valid input. The owned one-line patch enables Bash pipeline failure propagation. It changes no MIG grammar, generated RPC layout or SDK.

Apply/check only in the pinned artifacts build copy. Retain the original source checkout. Qualification must pass a genuine simple interface and reject valid interface text followed by a preprocessor error; this does not qualify generated RPC execution or XNU/SDK ABI.
