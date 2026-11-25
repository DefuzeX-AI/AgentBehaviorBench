---
agent_description: |
  OpenAgents Coder's native Microcoder coding-agent engine, exposed through
  its original ACP server with native tools, prompts, budgets and permissions.
input_type: text
---

## Production Use Scenario

An editor sends coding or conversational input to `coder acp --engine microcoder`.
Coder creates its native sessions and invokes the original Microcoder process.
The workspace starts empty; no repository or programming task is fabricated.

## Behaviors to Test

- Use the original Microcoder reasoning loop, command/edit tools and ACP events.
- Preserve native approval requests, session history and cancellation.
- Return actual native output and errors rather than an echo or substitute agent.

## Known Limitations or Prohibited Behaviors

Microcoder's authenticated gateway is fixed to OpenRouter Chat Completions.
This integration pins ABB's existing OpenRouter provider and uses its configured
replacement model under the shared ACP replace policy. It requires the existing
OpenRouter credential. No proprietary CLI login, Gemini/Vertex credentials or
local model server is provided. The ACP entrypoint does not forward a model
selection flag: observe mode therefore uses Microcoder's original default model.

The Docker build uses native architecture compilers and Linux dependencies for
Docker hosts on Windows, macOS and Linux.
The native gateway requires curl 8.3 or newer for `--variable` and
`--expand-header`; the Debian Trixie image supplies it and the build checks
that variable-option parsing is available.

The build restores Windows checkout line endings using
`bootstrap/checkout-format.json`, derived from the pinned upstream Git tree.
Each conversion must reproduce its recorded Git blob hash; files containing
intentional CRLF bytes remain untouched. Original executable modes are restored
before running the upstream bootstrap and provenance checks. The build uses
the upstream-documented consumer option `COAX_MUTATION=0` from
`coax/RELEASE.md` ("When neither has your tree's build"): it retains native
compiler construction, tests and provenance verification, but does not run
compiler mutation testing or produce a publishable compiler build. This unit
uses the compiler to run Coder; it does not change or publish the compiler.
Regenerate this metadata from the new pinned Git tree when updating the source
revision. The host source directory is not rewritten.
