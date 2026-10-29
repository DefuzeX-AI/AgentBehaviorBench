# Archived historical reproduction

Baseline request-005.json contains four tool results without assistant calls; response-005.bin records HTTP 400. The repair control has matching calls/results and a working multiply function. Native sessions were used, not an ABB/ACP suite.

These are existing 2026-10-26 experiments, copied on 2026-10-28. No Agent was rerun.
Original artifacts and existing Issue runs were not modified. Baselines reproduce the defect; repair controls demonstrate its removal.

| Role | Local trajectory |
| --- | --- |
| baseline | [native-a75f9afc-bca](trajectory/native-a75f9afc-bca/trajectory.json) |
| repair_control | [native-bbac0ea4-446](trajectory/native-bbac0ea4-446/trajectory.json) |

[Archive index](archive.json) · [Verification summary](verification/verification-summary.json) · [File integrity manifest](file-integrity.json)

Trajectories were derived offline from the copied raw evidence. A partial trajectory status describes capture/association limitations, not whether the defect reproduced.
Historical reports are preserved verbatim under verification. Their old path strings are provenance, not the navigation index; use the local paths above.
