# Bub remaining behavioral hypotheses — 2026-10-26

**Outcome: no GT candidate.** H2 was withdrawn after discovering its predicted core-tool path was not active in this ACP deployment. H3 was falsified by a correctly scoped native edit. Together with the earlier two H1 falsifications, the three-hypothesis limit is exhausted. No ten-run confirmation, additional hypothesis, upstream defect search or formal GT-list change was performed.

## Frozen deployment and scope

These follow-up probes used ABB `556dbe85`, unchanged unit `120-bub`, Bub `a93f5b80cf4b1bb35a248f4108b463f7af44f08d`, and official ACP plugin `bubbuild/bub-contrib` at `8727b088aea69615d44d3b58ab0b9be6d16a884e`. The previously approved shared OpenTelemetry prerequisite remained installed. The actual paid-run image was:

`defuzex-agentbench/bub:ca8daa1d42811c6e8cd514483a7412fa7a52a9ceca04d0d622b50c2fc7c7f53a`

Both plans recorded `doubao-seed-2-1-lite-260915` at `https://ark.cn-beijing.volces.com/api/v3`, using runtime-owned shared Chat Completions selection. No Agent source, tool, permission, model-route or profile changes were made. Each native Case allowed two inputs, 600 seconds, zero automatic retries and no Judge. The supported runner passed `after_suite=None`; no formal GT matcher ran. Initial preregistrations and their hashes were preserved, followed by an explicit deployment-source correction before the H3 paid run.

## H2: background-output pagination

[Case H2 v1](h2-v1.json) asked for a short background receipt export, incremental output pages of at most 60 characters, and a complete output file. Recovery through other available tools was explicitly allowed. The exact expected output was 30 lines, `receipt-000` through `receipt-029`, totaling 360 bytes.

The initial source hypothesis was that core `bash_output` calls `ShellManager.wait_closed()` before returning a bounded page, removing an exited shell handle and making later pages unavailable. **That source premise was inapplicable to the actual deployment.** The pinned ACP server's `agent.py` installs `build_client_tools(...)` over core tools when client capabilities are present. Its active `ACPClientToolRuntime.bash_output` reads the retained client terminal output and does not delete the handle. Both investigator and independent reviewer initially missed the override; the correction is retained rather than rewriting the original preregistration.

Actual first-task evidence showed:

- The background process really ran and exited with code 0 before the first page.
- Six successful 60-character pages covered offsets 0, 60, 120, 180, 240 and 300; an additional offset-360 read confirmed no further output.
- A genuine `fs.write` submitted the exact expected 360-byte text.
- A subsequent real `wc`/`md5sum` command observed 30 lines, 360 bytes and MD5 `eabdc413b84f751c18368fc7bec78ca4`, matching the frozen expected output.

The Agent's first task returned successfully. **Host SDK acceptance then failed while publishing an OTel payload, before the second read-only audit.** Its error referenced a missing `blobs/b34ec5ab99e3adb49971ec71cd3da190612803f0eb9a040664cf522ffa0d14be` during hard-link publication. Cleanup succeeded; host trace validation was not performed. The final-byte audit input did not execute. Retained raw channel evidence supports the successful paging observations, but this is not a fully accepted Case or a Judge pass. The SDK failure is separate from the withdrawn Agent hypothesis, and H2 was not rerun.

## H3: section-scoped configuration editing

[Case H3 v1](h3-v1.json) asked to change only `[server].port` from 8080 to 9090, retaining `[admin].port=8080` and all other section/key values. Its oracle compares semantic mappings; formatting changes would not support H3 or recycle H1.

Read-only inspection of the actual installed ACP plugin confirmed the unbounded `to_replace.replace(old,new)` mechanism remains in `ACPClientToolRuntime.edit_file`. The corrected source attribution and installed-file hashes were independently reviewed and frozen before payment:

| Installed plugin file | SHA256 |
| --- | --- |
| `bub_acp_server/agent.py` | `a4ff6bc804724c6250da7e4ea3e6991d768f80e55f050b4c08359f668fb757a3` |
| `bub_acp_server/client_tools.py` | `4bc5ecd8d2ef1a43c04f16b7766a96f5620848df6db379e6942ebfe0ddd7abfb` |

Bub read the original fixture and used native `fs.edit` with a unique three-line old value containing `[server]`, its host and port. The actual read-only Python audit returned precisely the frozen mapping:

```json
{
  "server": {"host": "0.0.0.0", "port": "9090", "workers": "4"},
  "admin": {"host": "127.0.0.1", "port": "8080"}
}
```

This falsifies H3 for the tested task. The actual editing tool was exercised; contextual selection prevented collateral mutation. Execution, host trace validation and cleanup all succeeded. No repair was needed. Judge delivery was not requested and the quality gate was `NOT_EVALUATED`.

## Usage and evidence scope

| Probe | Native-reported input tokens | Output tokens | Total tokens | Intercepted request/response pairs | Disposition |
| --- | ---: | ---: | ---: | ---: | --- |
| H2 first task | 44,547 | 3,135 | 47,682 | 11 | Hypothesis withdrawn; SDK acceptance blocked |
| H3 two tasks | 22,100 | 1,352 | 23,452 | 7 | Falsified; accepted execution |
| Follow-up total | 66,647 | 4,487 | 71,134 | 18 | No GT candidate |

Usage comes from native ACP prompt response records, not a billing calculation. H2 retained 11 completed ACP tool spans; H3 retained 4 + 1. Their ACP summaries reported no incomplete tools, with protocol-event coverage and no internal model spans. Separate interceptor records preserve real request/response traffic. H2's failed SDK publication limits host evidence acceptance despite the raw channel records. H3's oracle is based on genuine read-only tool output, not an independently mounted post-cleanup filesystem snapshot.

The earlier H1 archive remains immutable. Its successful byte-preservation observations remain valid; this follow-up corrects the broader assumption that core Bub tool definitions alone describe the ACP deployment. No new defect claim is inferred from that earlier source attribution.

## Post-test infrastructure correction

The separate shared correction in `agentbench/observe/payloads.py` preserves the complete transport temporary file until publication succeeds. New payloads avoid a redundant second hard-link operation; existing payloads use a separate temporary link with a narrow fallback that retains the complete file if optional hard-link deduplication is unavailable. Corrupt stored payloads, symlinks, unexpected I/O errors and rename failures remain errors.

Three focused regression cases failed before the patch. Afterward, this suite passed with **49 passed, 4 skipped**:

```bash
PYTHONPATH=. python -m pytest -q tests/test_direct_trajectory_storage.py tests/test_agent_response_transport.py tests/test_sdk_agent_session.py tests/test_issue165.py
```

The skips were three opt-in Docker privacy cases and one root-only ownership case. An additional Linux container smoke check used `--network none`, the same prebuilt image and a read-only bind mount of the updated runtime source. It verified new/existing payload inode sharing and preservation of a complete file when existing-blob relinking raises ENOENT. That check made zero Agent/model calls and did not rebuild the paid-run image.

The actual paid results above **precede** this infrastructure patch. Offline regression and filesystem smoke validation do not establish a fresh real-Agent/SDK acceptance run after the fix. The exact underlying filesystem cause of H2's transient link failure remains unproven; the correction removes the unsafe deletion window and retains evidence on the covered publication failures. No new model execution was performed merely to convert the blocked record into a pass.

## Portable evidence

The evidence archive retains both Cases, initial and corrected preregistrations, frozen fixture/oracles, installed-source hashes, raw channel and accepted SDK artifacts, interception records, audit calculations, runner and post-test infrastructure patch. It excludes source checkouts, credentials, formal GT directories and `gt.json`. The manifest records original/export SHA256 for each included file. Exact known secrets, recursively encoded opaque replay content and host-specific paths are redacted. Original embedded hashes remain historical references when exports differ. This is not a standalone HTML viewer or formal GT submission.
