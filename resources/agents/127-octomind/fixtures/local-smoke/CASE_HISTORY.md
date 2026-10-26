# Filesystem Smoke Case versions

V1 is preserved under `history/v1/` and in the frozen run archives. Native execution, Trace validation and cleanup succeeded on its second independent run. The Local Judge returned pass with two evidence gaps, which the strict parser correctly rejected. The missing observations were an independent pre/post workspace listing and a directly observed working directory.

V2 adds those actual observations and absolute-path execution with explicit process exit status. It does not supply an expected Agent answer or a Judge verdict, remove a tool, change Agent logic, relax the Judge, or change the model. All failed attempts remain retained. This is integration Smoke evidence, not a GT candidate.
