# Issue 561: fresh causal verification

Date: 2026-10-26 (America/Toronto).

## Verdict

**Correct for the tested fault locations and central root cause.** A fresh complete ABB before/after pair reproduced the incorrect date and repaired it by changing only the date-context assembly function. The original GT was not modified. Historical release claims (`reported_version=2.7.2`, `fixed_in=2.11.0`) were not independently re-established by this experiment.

## Version and isolation

The active launcher explicitly selects `/opt/vibe135/bin/vibe-acp`. Despite its directory name, this environment contains Vibe **2.10.1**, Python **3.13.17**. The other environment `/opt/vibe` contains 3.0.2 and was not selected. Both real ACP handshakes report 2.10.1.

The original installed `vibe/core/system_prompt.py` matches the source archive for commit `f71bfd3b8cdddbb4369c843da9c48d5f6c637ef7` byte-for-byte after text decoding. The CLI template also matches. The archive was already present in the cached historical image; no new upstream release validation was performed. See `probe-before.json`.

All experiment files, independent units, registry, patch and results are confined to this directory. Production configuration, shared source, `.env`, global registry and original GT are unchanged. Each Agent arm starts with an empty workspace. Model selection is OpenRouter `openai/gpt-4.1-mini`, with identical model configuration and non-message request parameters/tool definitions.

## Complete Agent evidence

The original single step is copied exactly into `case.json`:

> What is today's date? Answer with the exact calendar date.

| Observation | Before | After |
| --- | --- | --- |
| Suite | `suite_3b61ab2afd674e9a995981601a86fb0d` | `suite_73bcdcf0aa3f49989afd6205d5da6a18` |
| Real outgoing model requests | 1 | 1 |
| Current date in system context | Absent | `Today's date is 2026-10-26.` |
| Actual final answer | `2024-06-14` | `2026-10-26` |
| Tool calls | None | None |
| Host execution | COMPLETED, exit 0 | COMPLETED, exit 0 |

No Judge was requested. Evidence comes from intercepted model payloads, ACP events and actual result files, rather than Agent self-assessment or a Judge. There are no terminal/file operations to inspect because neither run calls a tool. The actual container date was 2026-10-26, also matching the user's local calendar date.

The outgoing system contexts differ only by the injected date and the random scratchpad directory assigned to each session. Non-message payloads are identical. The user prompt is identical in both requests. See `before-request.json`, `after-request.json`, `request.patch`, and `verification-summary.json`.

## Fault locations and repair

1. `vibe/core/system_prompt.py`, `get_universal_system_prompt`, original lines 298-384: **confirmed causal location**. The function begins at line 298 and assembles context without the date. The repair adds three lines immediately after the sections initialization at line 309:

```python
from datetime import date

sections.append(f"Today's date is {date.today().isoformat()}.")
```

2. `vibe/core/prompts/cli.md`, lines 1-3: **correct supporting omission, not a separately repaired causal site**. The template contains no current-date placeholder. The GT already correctly describes it as supporting evidence. The candidate does not edit it.

The Agent path demonstrably receives this function's repaired context: the unique inserted line appears in the intercepted outgoing request. ACP client terminal tools cannot account for the result, because no tool is invoked. This is not the CLI/ACP Bash-path ambiguity seen in other issues.

`probe-after-final-image.json` confirms that the installed source in the corrected built image differs from the pinned archive only by the candidate patch. It retains the original template. Independent calls to the real function with simulated dates 2024-02-29 and 2030-01-02 return those dates after the repair; the original returns only the baseline context. These function controls supplement the complete Agent pair.

## Experimental infrastructure and qualifications

An early candidate file was initially emitted with Windows default encoding. An independent probe of intermediate image `dc3de523cf9036919affa88f5c98ed161746703f14b41922ce1677382e8ae8a4` raised a UTF-8 SyntaxError. The file was corrected to explicit UTF-8. The complete first after suite subsequently finished successfully with the injected date; the early probe failure must not be represented as that suite's final status. Corrected image `e8ed832b3a71ce706f674d1cf22474fd11d89353ceb2dc7cebe3ec158946860b` passes the installed-source probe.

An additional run in `after-final-results` was BLOCKED before any model request: the host could not create a long Windows temporary pathname under `agent-request/execution-environment.json.*.tmp`. It completed 0/1 cases. This is a harness/path infrastructure failure, not evidence against the date-context repair. A further confirmation uses the short `a` results directory; it also completed successfully (exit 0), answering `2026-10-26` with one model request and no tool calls. Suite: `suite_6c3ab8b3edbc478f9f0fd8f3b7c0a190`. Its request equals the first successful after request apart from the session scratchpad path. See `confirmation.json`.

The candidate uses the container's local date. This experiment does not establish timezone semantics when the user's date differs from the container date, nor universal model compliance. Models can sometimes answer correctly from tools without the patch. The first upstream fixing release and the originally reported 2.7.2 version remain inherited historical metadata, not newly tested facts. The GT's existing limitations are appropriate; no change to its central fault locations or root-cause explanation is warranted.

## Evidence and reproduction

- `commands.ps1`: exact native evaluation commands; run from the project root using its active `.venv`.
- `gt-original.json`, `case.json`: GT snapshot and exact prompt.
- `verify561-before/`, `verify561-after/`, `registry.toml`: isolated runnable units and configuration.
- `before-results/`, `after-results/`: successful complete Agent pair.
- `before.log`, `after.log`: suite completion records.
- `verification-summary.json`, `summarize.py`: checked prompts, model, versions, tool counts and outputs.
- `before-request.json`, `after-request.json`, `before-system.txt`, `after-system.txt`, `request.patch`: actual model request evidence.
- `date.patch`, `patch.py`: minimal candidate change.
- `probe.py`, `probe-before.json`, `probe-after.json`, `probe-after-final-image.json`: real function, version, source and simulated-date controls.
- `after-final.log`, `after-final-results/`: retained host path-length failure.
- `a/`, `after-valid.log`: additional clean short-path confirmation.
