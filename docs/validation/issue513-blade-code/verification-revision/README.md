# Verification-failure revision for PR #574

The maintainer's [retest](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/574#issuecomment-6381730019) found that Blade Code's independent-verification gate could terminate an otherwise recorded ACP turn with an RPC exception, leaving ABB unable to judge the Case.

The revision keeps the native gate and its retry limit enabled. The outer unit-local relay recognizes only a tracked prompt's typed `verification_failed` error with the exact pinned SDK message `Internal error: Agent turn failed (verification_failed)`. It preserves streamed native text and the complete native error, emits a labeled adapter diagnostic, and returns ACP `refusal` with failed verification metadata. Other errors remain errors. No ABB core or upstream Agent source is modified.

## Evidence and environment

`smoke/` contains a real Docker Local run using `deepseek-chat`: one Case completed, local Judge `pass`, quality gate passed, CLI exit 0, complete evidence, successful host trace validation and cleanup. The Agent wrote, read and executed `hello.py`; three Agent model requests were intercepted.

`multifile/` uses three implementation modules (`calc.py`, `formatting.py`, `main.py`), a unittest module and actual CLI commands. The native gate genuinely reached `verification_failed`. ABB completed 1/1 Case with complete evidence, successful host trace validation and cleanup, and received an ACP refusal carrying the full original error plus the diagnostic. Thirteen Agent model requests were intercepted. This directly exercises the changed failure path; it is not a claim that native verification passed.

The multifile Local Judge's raw answer simultaneously returned `status="pass"` and a nonempty `evidence_gaps` list. ABB correctly rejected that contradictory response (`ValueError: Judge cannot pass with evidence gaps`), so no valid Judge report was delivered and the overall CLI exited 1 with quality gate failed. The unchanged raw Judge response and failed delivery record are included. The Case execution completed; the failed native verification and invalid Judge response remain separate recorded outcomes. No Agent rerun or edited Judge verdict was used to conceal either result.

Validation uses the pinned official `blade-code@0.11.23` package, ACP 0.12.1 on the ABB side, and ABB code synchronized with main `0ef4257b`. The host CLI runs as non-root UID 10001, matching the existing image's non-root UID, in a dedicated Linux runtime. A root launcher only creates and assigns that validation folder, then drops to UID 10001 before starting ABB. It changes no system account, global setting, container security option, source file or tool permission.

Seven Python launcher/ACP-host checks and nine Node transport checks passed. The Python protocol fixture is explicitly offline: it verifies that the real ABB ACP session accepts the refusal and retains the complete error metadata, without pretending to run Blade or a model. The registry loads and combined KUMA onboarding/unit validation passes, with the entry still disabled and `adapting`.

Each Case directory contains copied original SDK/host/result/Judge documents and unchanged selected ACP tool events. `contributor-index.json` is a contributor-generated index with counts and digests, not SDK certification. Complete original traces stay in the recorded local attempt directories. Model reasoning is omitted from the public excerpts. These are Local SDK checks; no official KUMA Case/Judge call or GT claim is made.

## Reproduction

Prepare the package-based unit normally, enable only Blade in a local registry while retaining `adapting`, and configure ABB's shared model credentials. The recorded selection was `ABB_MODEL_PROVIDER=deepseek`, `DEEPSEEK_MODEL=deepseek-chat`; the service's raw Judge response identifies its resolved model as `deepseek-flash`. No credential belongs in these files.

From the repository root, use a separate results directory for each invocation:

```bash
python -m pytest -q tests/test_issue513.py
node --test tests/test_issue513_transport.mjs
python -m agentbench evaluate blade-code --sdk local \
  --registry /absolute/path/to/local-registry.toml \
  --case-file docs/validation/issue513-blade-code/verification-revision/multifile/cases.json \
  --cases 1 --max-steps 1 --case-retries 0 --timeout 900 --no-view -y \
  --results-dir results/blade-verification-revision
```

Use `smoke/cases.json` for the small positive Smoke. The protocol test requires the existing ACP adapter dependencies; it is skipped when they are absent. The original evaluation allowed `ABB_LOCAL_JUDGE_MAX_CHARS=2000000` so the larger Case was not silently truncated. The Linux UID/storage prerequisites and failed alternatives above are part of the recorded environment, not a guarantee that every host will pass.

## Earlier unsuccessful revision attempts

`earlier-attempts/` retains bounded original records for all four attempts before the final error-format correction:

- `ext4-cleanup-blocked`: Agent and SDK execution, evidence validation and container cleanup succeeded, but the host's final `cleanup_transport` could not remove container-owned `done.json` from a directory owned by UID 10001 while the host CLI was UID 1000. No Judge report was produced. Matching the host CLI's non-root UID to the image's UID avoids this environment boundary; the failure is not hidden as a pass.
- `windows-longpath-blocked`: the controller encountered an input/output error reading the request/output bind mounts before any Agent model request.
- `windows-channel-blocked`: the shorter Windows runtime reached the channel but failed with `Operation not permitted` while preparing its close request. The final validation uses Linux storage.
- `multifile-first-attempt`: the native verification gate failed and the relay did not recognize the SDK's `Internal error: ` prefix. The Case was host-rejected and its Judge result was inconclusive. Inspecting the actual pinned native SDK serialization corrected the exact match and both protocol fixtures; the same multifile Case was then rerun. Original failed records remain unchanged.
