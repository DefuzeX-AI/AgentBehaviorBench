# Bub source-grounded behavioral probes — 2026-10-26

**Outcome: no GT candidate found.** One source-derived hypothesis was tested with two preregistered Case versions. Both real Agent executions falsified the hypothesis: the completed configuration edit preserved the exact expected bytes. No ten-run confirmation, upstream defect search, or formal GT-list change was warranted.

## Deployment and hypothesis

Issue #469, Step 2 testing. ABB base `8349406e`; unchanged Bub unit `120-bub`; source `a93f5b80cf4b1bb35a248f4108b463f7af44f08d`; official ACP plugin `bubbuild/bub-contrib` at `8727b088aea69615d44d3b58ab0b9be6d16a884e`. No upstream source, tool, permission, model-route or profile changes were made.

H1: native `fs.edit` reconstructs text using `splitlines()` and LF joins, potentially losing CRLF separators or a terminal newline during a targeted edit. Local text I/O can normalize separators as well. The deployed profile explicitly promises preserving unrelated formatting. The unchanged fixture `settings.ini` contains 122 bytes, 11 CRLF separators and a terminal CRLF. The legal task changes only `retries = 3` to `retries = 5`.

[Case v1](h1-v1.json) requested byte inspection and verification in the task. [Case v2](h1-v2.json) separated an ordinary edit from a subsequent read-only byte audit. It retained the same full preservation requirement and allowed any native editing tool and correction before edit completion. The revision rationale and both versions were frozen before their respective executions and independently reviewed. Only one hypothesis and two Case versions were used.

## Actual results

| Version | Dialogue inputs | Model requests/responses | Native-reported tokens | Result |
| --- | ---: | ---: | ---: | --- |
| H1 v1 | 1 | 4 / 4 | 13,377 | Falsified: byte-preserving Python edit |
| H1 v2 | 2 | 8 / 8 | 29,496 | Falsified: byte-preserving Python edit and read-only audit |

Total native-reported usage: **42,873 tokens** (40,220 input; 2,653 output), from the ACP prompt usage records. This is reported API usage, not a billing calculation. Actual native model selection was `openai:doubao-seed-2-1-lite-260915`, using the configured shared Volcengine Chat Completions endpoint through the runtime's OpenRouter configuration slot. No model alias or fallback was introduced.

For both versions, genuine tool-result `repr(bytes)` payloads were decoded independently and compared against the frozen original bytes with exactly one replacement. Both produced 122 bytes, 11 CRLF separators and the terminal CRLF, with SHA256:

`8762945d501e96f075d18e6eb766c78f4bb6941e6370d816f36e06f010e27f5d`

Bub selected Python binary reads/writes instead of the potentially lossy text tool. V2 encountered a missing optional `file` command, then completed through other native commands; that recovered tool error is neither a GT reproduction nor an excluded run. A presentation-only count of lines in the final prose is not promoted into an unregistered hypothesis.

Both runs completed with successful host trace validation and cleanup. ACP evidence contains 3 tool calls for v1 and 5 + 1 for v2, with no incomplete tools reported; actual arguments and result payloads are present. ACP capture covers protocol events, not internal model spans. Separate interceptor records contain the 12 real model request/response pairs. The byte oracle relies on genuine read outputs, not an independently mounted post-cleanup filesystem snapshot. No Judge was requested; the quality gate is `NOT_EVALUATED`, not a Judge pass. These two pilots do not establish a general reliability rate.

## Infrastructure failures and correction

Three attempts preceded the first valid behavioral run and remain retained as infrastructure exclusions:

1. Docker Hub base-image metadata request returned EOF during generation build; no Case/model call.
2. Same metadata failure on a replenishment; no Case/model call.
3. Worker startup raised `ModuleNotFoundError: No module named 'opentelemetry'` before any step/model call; cleanup succeeded.

The shared worker channel imports OpenTelemetry before loading the Agent adapter. Native SDK requirements said the shared builder installed it, but the shared runtime requirements omitted it. The separate correction adds `opentelemetry-sdk>=1.30,<2`, matching the existing `pyproject.toml` telemetry dependency range. It restores evidence instrumentation without changing Bub behavior. The rebuilt native SDK image was frozen before valid execution:

`defuzex-agentbench/bub:ca8daa1d42811c6e8cd514483a7412fa7a52a9ceca04d0d622b50c2fc7c7f53a`

Validation: clean pinned source preparation; official native SDK image build; network-disabled container imports of worker `WireExporter`/`WireSpanProcessor` and SDK `decode_span`; `tests/test_worker_build_cache.py tests/test_native_container.py` yielded 1 passed and 1 opt-in integration test skipped; actual native runs subsequently passed execution/trace/cleanup. `git diff --check` passed.

## Reproducibility and evidence boundaries

The supported native runner used `build_trace_suite_runner` and `run_benchmark_session(after_suite=None)`, no Judge, 600 seconds per Case and zero automatic retries. This omits the optional post-suite formal-GT matcher. The first two failing CLI attempts had automatically emitted empty matcher summaries with zero calls; investigators did not read their GT output or existing GT contents. No upstream issue, fix PR or previous defect report was consulted.

The portable evidence archive retains preregistrations, frozen hashes, both Cases, raw-byte oracle files, genuine execution/network/ACP/tool artifacts, infrastructure attempts, API runner, build logs and the dependency patch. It excludes credentials, upstream source checkouts and automatically created GT output directories. Its manifest records original and exported SHA256 for every included file. Secrets, opaque encrypted replay fields and host-specific absolute prefixes are redacted; export bytes can therefore differ from original evidence, and embedded original hashes remain historical references. The archive is not a standalone HTML viewer or a formal GT submission. Raw traces are release evidence, not committed source files.
