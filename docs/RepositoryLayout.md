# Repository directory responsibilities

| Directory | Responsibility |
| --- | --- |
| `agentbench/cli/` | Commands, argument parsing and terminal presentation |
| `agentbench/harness/` | Registry and benchmark orchestration |
| `agentbench/adapter/` | Framework loading and invocation contracts |
| `agentbench/runtime/` | Container delivery, image building, lifecycle and host-side interception configuration |
| `agentbench/observe/` | Observe orchestration, framework observation, trace storage and review |
| `agentbench/environment/` | External evaluation environment lifecycle |
| `agentbench/sdk/` | Evaluation SDK integration |
| `resources/agents/<agent>/` | A portable Agent unit: original `agent/` source, manifest, Dockerfile and Agent-specific `bindings/` |
| `services/model-interceptor/` | Separately packaged network interceptor implementation |
| `tests/` | Automated regression tests, fixtures and shared test support |
| `tests/acceptance/` | Explicitly invoked acceptance checks with their local build resources |
| `examples/` | User-facing sample inputs |
| `web/` | Trace viewer source, frontend tests and its server support |
| `docs/` | Usage, architecture and validation documentation |
| `results/` | Generated execution artifacts |

## Company SDK acceptance relocation

| Previous path | Current path |
| --- | --- |
| `tools/verify_company_sdk.py` | `tests/acceptance/company_sdk/run.py` |
| `tools/company_sdk/Dockerfile` | `tests/acceptance/company_sdk/Dockerfile` |
| `tools/company_sdk/verify_imports.py` | `tests/acceptance/company_sdk/verify_imports.py` |
| `tools/company_sdk/README.md` | `tests/acceptance/company_sdk/README.md` |

Run the acceptance check using the command in its
[README](../tests/acceptance/company_sdk/README.md). It installs and imports
Company and the local SDK together; it does not execute research or an SDK Run.
Keep it explicitly invoked so ordinary test collection does not build images.

## Placement rules

- Keep each Agent's special handling in its own `bindings/`; the generic
  framework loader reads the configured binding inside the container. A Company
  binding does not belong in the generic framework package.
- Keep the container worker and invocation delivery in `runtime/`; an acceptance
  script is not a replacement for that execution path.
- Keep framework trace observation in `observe/` and network interception in the
  separately packaged interceptor. Moving files alone does not improve their contracts.
- Place reusable test support in `tests/support/`, fixture data in `tests/fixtures/`,
  and resources exclusive to an acceptance check beside that check.
- Do not add a root directory for a single verification script. Prefer its owning
  module or `tests/acceptance/` according to whether it serves production or validation.
- `.venv/`, `node_modules/`, `dist/`, `__pycache__/` and test caches are generated
  local artifacts, not source modules to reorganize.
