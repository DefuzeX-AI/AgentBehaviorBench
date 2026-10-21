# DecompAI ABB integration (Issue #375)

Upstream: louisgthier/decompai, commit `0c2398c09e318be1bb6f6a52d13e572fac7c519b`.
This is a manual, bounded LangGraph integration. Registration is disabled/adapting;
static validation is not a claim of successful local or official evaluation.

## Source preparation

The upstream repository contains an absolute runtime alias,
`decompai_analysis_sessions -> /tmp/decompai_analysis_sessions`. ABB correctly rejects
external/directory symlinks in source snapshots. Therefore this unit declares
`source.method = "bundled"` and has a documented manual preparation step:

```sh
python resources/agents/63-decompai/prepare_source.py
```

The script checks the pinned source hashes, omits only `.git` and that exact runtime
alias, and creates an empty directory at the alias path. It never follows the link.
All 31 regular upstream files, including native prompts and tools, remain
byte-identical; source-provenance.json records each hash. An existing agent/ is
preserved rather than overwritten. Do not commit ignored agent/ contents.

## Deployment

`bindings/bridge.py:create_graph` prepares a session and invokes native
`src.main.graph`. It reads the native UI's literal system prompt from the pinned
source and returns the final native assistant answer. All native tool definitions
remain registered. The GUI is not launched.

Native utility command strings execute inside the existing non-root ABB Agent
container via `container_transport.py`. This replaces only the upstream Docker
transport: no Docker socket, privileged runner or host filesystem mount is supplied.
Persistent shell calls retain state. Tool timeouts/errors remain visible.

The image is x86-64 Debian, not the full Kali image. It installs objdump, file, GDB,
radare2 core and Ghidra 11.3.1. Optional r2dec/r2ghidra plugins are not provisioned.
GDB execution/ptrace can remain constrained under emulation/container policies.
The image preloads the native tiktoken encodings at build time; tool token counting
does not require runtime access to the tokenizer download host.
Those limitations are part of requirement.md; they must not be hidden from Cases.

Plain text analyzes the packaged ELF fixture compiled from fixtures/branch.c.
JSON text can select another binary already staged under the fixture/session root:

```json
{"request":"Disassemble classify and explain its two return values.","binary_path":"/opt/agent/fixtures/branch"}
```

Only x86/i386 or x86-64 little-endian ELF is accepted. There is no URL download or
upload endpoint. Native tools still inspect the disposable container; the input
path check is not advertised as confinement of every native tool.

The deployment uses opencode/glm-5.3-flash without model fallback. Defaults are
8 model attempts, 3072 output tokens per response, 24 graph steps and 60 seconds per
shell command. The native rate-limit loop remains inside that attempt limit;
ChatOpenAI transport retries are set to zero. Budget/truncation failures do not
produce a completed-answer claim. Required credentials stay in the runtime and
are absent from committed files.

## Validation

```sh
python -m pytest -q tests/test_issue375_decompai.py
```

The tests use isolated temporary files, no keys and no model/network calls. They
check input rejection, source hashes, factory contract, real stdout/stderr,
persistent shell state, explicit timeout and resource cleanup. Real Docker tool
checks and ABB/KUMA evaluations must be reported separately with actual run IDs.


### Container checks without model calls

After the standard ABB worker-overlay build, mount validation/preflight.py at
/tmp/check.py and run python /tmp/check.py with Docker network=none. It invokes
the native structured disassembly tool (including its token-count path), strings,
radare2 and Ghidra on the compiled fixture. This is a real tool check, not an LLM
or KUMA evaluation.

validation/local-case/ is a saved SDK custom Case collection for a one-step
binary-analysis smoke. Its origin is custom, not official KUMA generation. Use
its case-collection.json as the local SDK's case_collection option. The main
registry entry stays disabled/adapting; use an explicit private enabled registry
for evaluation rather than marking the shared entry ready.

The accompanying ABB observability repair projects real Pydantic tool arguments
before JSON encoding and credential redaction. Unsupported values remain omitted.
It does not change tool inputs/results or fabricate observations. Run the typed
argument regression in tests/test_issue375_trace.py to verify that the real SDK
receives both arguments and results.
