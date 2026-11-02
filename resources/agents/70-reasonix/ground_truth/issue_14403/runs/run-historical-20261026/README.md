# Archived historical reproduction

The retained baseline inserted a bare LF into a CRLF settings.ini. The edit_file call used old_string `retries=3` and new_string containing a line break before `timeout=30`; the recorded `od -c` output shows the resulting mixed line endings. This is an existing experiment from 2026-10-26, copied on 2026-10-28; the Agent was not rerun for this archive.

[Baseline trajectory](trajectory/cbfe63c1f831434ba249930b75fe08f4/trajectory.json) · [Archive index](archive.json) · [File integrity manifest](file-integrity.json)

The historical test used a pre-created CRLF fixture and the unit name `verify-reasonix14403-before`. The Case explicitly permits this baseline alias for the registered `reasonix` Agent; the raw trajectory retains its original identifier. A partial trajectory status describes capture and association limits, not whether the byte-level defect was observed.
