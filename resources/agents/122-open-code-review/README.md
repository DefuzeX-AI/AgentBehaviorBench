# open-code-review ACP deployment

This unit builds [open-code-review](https://github.com/alibaba/open-code-review)
(`alibaba/open-code-review`, revision `375f64cd`, Apache-2.0) from source and runs its native ACP
stdio adapter `ocr-acp`, which wraps the OCR CLI. ABB drives one ACP session per Case.
`source.method = "git"` restores the pinned checkout into `agent/`; no upstream file is modified.

This unit uses default model selection; no `[model]` declaration is needed. ABB passes the
resolved configuration through `ABB_AGENT_MODEL_API_KEY`, `ABB_AGENT_MODEL_BASE_URL` and
`ABB_AGENT_MODEL`, and the runtime admits the `POST <selected-base>/chat/completions` route, which
both the review model and the intent parser use.

## Image

- Builder `golang:1.26.9-trixie` (`GOTOOLCHAIN=local`) compiles `./cmd/opencodereview` from the
  root module and `./cmd/ocr-acp` from `acp/`, both with `CGO_ENABLED=0`, from the restored `agent/`.
- Runtime `python:3.12-slim-trixie`: Debian trixie ships Git ≥ 2.41, an OCR prerequisite (bookworm
  has 2.39). Binaries live in `/opt/agent/bin` (`ocr` is a symlink to `opencodereview`).

## Launcher (`bootstrap/launch.py`)

- Validates the three model variables (HTTPS base URL without query or fragment) and maps them onto
  OCR's environment endpoint (`OCR_LLM_URL`, `OCR_LLM_TOKEN`, `OCR_LLM_MODEL`,
  `OCR_LLM_PROTOCOL=openai`) and the adapter's intent parser (`OCR_ACP_PARSER_PROVIDER=openai`,
  `OCR_ACP_PARSER_MODEL`, `OCR_ACP_PARSER_BASE_URL`, `OCR_ACP_PARSER_API_KEY`). The base URL is
  used as selected. `OCR_NO_UPDATE=1` and `OCR_ENABLE_TELEMETRY=false`.
- `/review` needs a Git repository, and ABB fixtures cannot contain `.git`. When the workspace is not
  a repository, the launcher runs `git init -b main` and commits the fixture once ("Workspace
  baseline"). Nothing else is written to the workspace.
- Disposable `HOME` per Case (OCR keeps config and sessions under `~/.opencodereview`), then
  `exec ocr-acp --ocr-binary /opt/agent/bin/opencodereview`. The launcher is not on the ACP stdio
  path, so prompts and agent messages pass through unchanged.

## Workspace fixture

`evaluation/fixture/` is a small Python service (`app.py`, `lib/pricing.py`, `README.md`,
`.gitignore`). `adapter.cwd` equals `evaluation.workspace.path` (`/home/agent/workspace`).
