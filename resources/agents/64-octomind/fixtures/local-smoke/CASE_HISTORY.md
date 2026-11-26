# Filesystem Smoke Case versions

V1 is preserved under `history/v1/` and in the frozen run archives. Native execution, Trace validation and cleanup succeeded on its second independent run. The Local Judge returned pass with two evidence gaps, which the strict parser correctly rejected. The missing observations were an independent pre/post workspace listing and a directly observed working directory.

V2 adds those actual observations and absolute-path execution with explicit process exit status. It does not supply an expected Agent answer or a Judge verdict, remove a tool, change Agent logic, relax the Judge, or change the model. All failed attempts remain retained. This is integration Smoke evidence, not a GT candidate.

V2 also completed natively with host Trace/cleanup success, but its Local Judge pass-with-gaps was rejected. The current native SDK request/result omit independent host filesystem snapshots; an empty workspace also cannot exercise preservation of pre-existing files. Neither filesystem Case is presented as a passing quality gate.

V3 is a deliberately narrower native-shell integration Smoke: execute a concrete Python calculation using the unchanged native shell, then report the command and actual stdout. It does not certify file preservation or other filesystem behavior. The original Agent, all 20 tools, shared SDK and strict Judge remain unchanged. Failed V1/V2 reports stay retained; V3 is not a GT claim or a replacement Agent.
