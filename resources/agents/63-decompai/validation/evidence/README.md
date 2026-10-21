# Local validation evidence, not official KUMA evaluation

These are actual outputs of one custom binary-analysis Local Smoke, after the
packaging and native typed-tool trace fixes. local-manifest.json and
local-judge.json are copied byte-for-byte. native-tool-spans.jsonl contains only
the real native tool-span records selected from the complete local trace;
it is not a full standalone Trace archive. File snapshot/diff/log capture was
disabled. Agent output is unedited. The prior attempt and its manually observed fixture-string
transcription discrepancy remain at commit 6cfc493. Local Judge remains pass.
The SDK Local Judge prompt/body/parser were preserved; only its host HTTP client
transport uses httpx for this endpoint. No KUMA credits were spent.
Official generation/Judge, a complete official Trace and maintainer acceptance
remain pending. Do not relabel these custom Case results as official KUMA.
