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

The model is the one ABB serves on the declared route (glm-5.3-flash by default). Defaults are
16 model starts, 3072 output tokens per response, 40 graph steps, 120 seconds per
model request, 60 seconds per shell command and 600 seconds per native utility
analysis (including Ghidra cold startup). The Agent wall-clock limit is 1800 seconds.
The Ghidra launcher uses a 512MiB heap and two JVM active processors to fit ABB's
1GiB/two-CPU runtime. Timeouts retain the actual partial output and terminate the
managed process group rather than leaving shell children running. The native rate-limit loop remains inside that attempt limit;
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

The disabled registry entry reserves two official Case slots for a bounded batch.
The explicit generation helper accepts only count=1 or count=2, with one
generation attempt per slot. Both passes and failures are retained; no candidate
filtering or automatic paid retries are used.

The image pre-indexes Ghidra/Jython framework caches on an unrelated throwaway
return-zero program at build time. The warm-up binary, source, analysis project
and output log are removed; no evaluation-binary analysis or answer is cached.

This deployment explicitly requests runtime.cpus=2. The optional per-unit CPU
request changes only the Docker CPU quota; memory, process, privilege, network
and mount policies remain unchanged. The effective quota is captured by ABB
before Case generation.

### Bounded public dependency downloads

The build-only `bootstrap/download_release.sh` resumes partial official GitHub release downloads for radare2 and Ghidra. It permits at most three attempts, with20-second connect and600-second per-request limits, retains partial bytes between failed requests, and verifies a fixed SHA256 before any installation/extraction. A checksum mismatch fails immediately rather than accepting a different artifact. The radare2 digest is the existing deployment pin; the Ghidra digest is `bcda0a9de8993444766cc255964c65c042b291ddaf6c50d654e316e442b441fa`, recorded from the previously verified official11.3.1 download. The historical GitHub asset has no API digest, so this is not described as a newly publisher-signed checksum. These build controls do not change native Agent source, tools, model selection, prompts, runtime quotas or Judge behavior.

A locked BuildKit cache mount retains only these public release archives between interrupted builds. Every complete cached file is rechecked against its fixed digest before reuse; invalid or partial cache contents never skip verification. Cache contents are not Agent source, model answers or evaluation workspaces.

`PIP_INDEX_URL` is a build-only argument and defaults to the official HTTPS PyPI index. A deployment may explicitly select an HTTPS package mirror for unreliable networks. Original native requirement constraints are unchanged; the argument does not set runtime proxy/model variables or disable TLS verification.
