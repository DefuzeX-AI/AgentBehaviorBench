# Waveloom ACP deployment

This unit installs the pinned [Waveloom](https://github.com/Menfre01/waveloom) release
`0.9.1` (tag `v0.9.1`, commit `daccab5d`, Apache-2.0) as the upstream prebuilt Linux
binary and runs its built-in ACP server (`waveloom acp`). ABB invokes it over ACP
stdio and keeps each Case in a separate empty workspace. No upstream source is
vendored or modified.

This unit uses default model selection; no `[model]` declaration is needed. ABB passes
the resolved configuration through `ABB_AGENT_MODEL_API_KEY`, `ABB_AGENT_MODEL_BASE_URL`,
`ABB_AGENT_MODEL` and `ABB_AGENT_MODEL_PROVIDER`; the runtime admits the exact
`POST <selected-base>/chat/completions` route.

## Distribution

`install/distribution.json` pins `waveloom_linux_amd64.tar.gz` from the `v0.9.1`
GitHub release by sha256 (`02a44fee…c75412c`, the value in the release's
`checksums.txt`). The Dockerfile downloads it, checks it with `sha256sum -c` and
installs the single `waveloom` binary to `/opt/waveloom/bin`.

## Launcher behavior

`bootstrap/launch.py` validates the model variables (HTTPS base URL without query or
fragment), creates a disposable `HOME` per Case, and writes a `settings.json` with
`llm.provider` (`deepseek` or `glm` when selected, otherwise `openai`), `llm.model`
and `llm.base_url`. `llm.api_key` stays empty; Waveloom reads the credential from
`LLM_API_KEY`, which the launcher sets from `ABB_AGENT_MODEL_API_KEY`, so the key is
never written to disk. It then execs:

```
waveloom acp --settings <home>/settings.json --session-dir <home>/acp-sessions --model <model> --no-sandbox
```

ACP mode always activates Waveloom's bubblewrap sandbox; `--no-sandbox` is the
upstream switch documented for already-isolated Docker/CI environments. Waveloom's
permission Guard (deny rules, high-risk commands, dangerous paths) still applies;
ACP mode auto-allows the remaining operations because ACP v1 has no permission
prompt (docs/acp.en.md).
