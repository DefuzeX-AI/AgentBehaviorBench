# Working on AgentBehaviorBench

This file guides contributors and coding assistants. User setup belongs in
[README.md](README.md); Agent onboarding commands belong in
[How to add agent](docs/How%20To%20Add%20Agent.md).

## Find the owner of a change

| Location | Responsibility |
| --- | --- |
| `agentbench/cli/features/` | CLI arguments and command dispatch through `CommandFeature` and `FEATURES`. |
| `agentbench/onboarding/` | Source import, discovery, reuse and optional configuration/certification workflow. |
| `agentbench/onboarding/build_agent_env/` | Planning, per-file generation, validation, persistence and registration. |
| `agentbench/adapter/` | Framework loading and native input/output invocation. |
| `agentbench/harness/` | Agent registry, suite scheduling, Case concurrency, recovery and results. |
| `agentbench/runtime/` | Generic Docker execution, runtime services and interception integration. |
| `agentbench/services/model-interceptor/` | Model protocol recognition, authentication, routing and traffic evidence. |
| `agentbench/sdk/plugin/<name>/` | SDK-specific Case generation, submission, judging and onboarding requirements. |
| `agentbench/sdk/contracts.py`, `agentbench/sdk/common/` | Shared SDK contracts and helpers. |
| `resources/agents/`, `resources/registry.toml` | Local Agent units and their registrations. |
| `web/` | Results viewer. |

Keep CLI handlers thin. Register commands through the existing feature registry;
do not add command-name branches to `cli/main.py`. Split substantial functionality
by responsibility and reuse existing contracts instead of building parallel paths.
Check nearby code and module documentation before changing an interface.

## Preserve the onboarding flow

```text
agentbench agent add REPOSITORY [-b] [-c]
    import/reuse source -> discover evidence
    -b: SDK context -> plan -> generate/validate/save each file -> register
    -c: invoke the certification workflow
```

Plain `add` imports a GitHub repository or absolute local directory and reports
discovered files. `-b` generates integration
configuration; Docker construction and execution belong to certification/runtime.
`-c` can also use manually prepared configuration.

- Keep upstream source under `resources/agents/NN-name/agent/`. Put `agent.toml`,
  `bindings/`, `Dockerfile`, `.dockerignore`, `requirement.md` and source provenance
  beside `agent/`, not inside it. Preserve upstream behavior and source files.
- Generate `agent.toml` programmatically from validated source facts and options.
  Other model-generated files are requested individually, validated and saved
  before advancing. `.dockerignore` comes from a local template.
- Keep each builder's prompts, examples and schemas with that builder. Prompts
  must explain the actual format and give usable examples, not assume the model
  knows BBA's interfaces. The existing binding builder is named `build_blinding/`.
- Keep framework-specific planning, rendering, validation and assets under
  `onboarding/build_agent_env/frameworks/<name>/`. Shared builders own orchestration,
  persistence and SDK policy; do not mix protocol-specific branches into them.
- Every complete generated LangGraph plan includes an outer Python binding. Its exported
  factory is synchronous and callable without arguments. The returned object
  exposes `invoke()` and may expose `ainvoke()`. Preserve native inputs, outputs,
  configuration, errors and resource cleanup; do not substitute a demo Agent.
- Supported frameworks must match registered runtime adapters and onboarding
  support. Do not label an unsupported framework as LangGraph to pass validation.
- Keep generation records and checkpoints under `cache/onboarding/`, outside
  distributable Agent units. Revalidate reusable files, preserve completed work
  after failure, and report conflicts instead of silently replacing manual files.
- Register new units as `adapting` after combined validation. Report configuration
  generation, static checks and real certification separately. A saved file or
  registry status alone does not prove a fresh successful execution.

See the [builder documentation](agentbench/onboarding/build_agent_env/README.md)
for stage ordering, checkpoints and extension points.

## Keep SDK and model boundaries explicit

- Discover evaluation SDKs from `agentbench/sdk/plugin/`. Keep their PyPI
  requirements beside the plugin; do not copy a local SDK checkout into BBA.
  Generic runtime code must not acquire SDK-specific responsibilities.
- The selected SDK owns its evaluation document contract. KUMA consumes the outer
  `requirement.md` as its Agent Profile. An `evaluation/` directory is optional for
  referenced schemas or fixtures; do not require an empty directory or restore
  the obsolete `evaluation/input-contract.json` marker.
- Ground Agent Profiles in the deployed tool definitions, binding and configuration.
  Enumerate what tools can actually do, what task data must be supplied and what is
  unavailable. Do not turn extensible architecture into claimed capabilities or
  describe installation/interception plumbing as behavioral test criteria. State
  how missing capabilities should be handled without claiming unperformed actions.
  Profile edits change future evaluation context; they do not add Agent tools or
  alter previously generated Cases. Validate with the pinned official SDK parser.
- Obtain available strategy groups through the SDK onboarding context, supply
  that catalog to generation and validate selections against the same snapshot.
  Do not invent or hardcode a strategy group ID in generic onboarding code.
- Preserve full response schemas for local validation. Project a separate
  provider-compatible schema for requests. Model replies still pass the full
  local contract and bounded repair loop before any generated file is installed.
- Keep protocol recognition in registered interceptor adapters. Explicit routes,
  authentication and tool egress rules remain separate concerns. Do not bypass
  interception, credential checks or evidence collection to make one Agent pass.
- Never send `.env` contents or actual credentials as source evidence, commit them,
  or expose them in errors. Keep API diagnostics useful and sanitized.

## Verify the changed behavior

Use the project's active Python environment. Read current dependencies from
`pyproject.toml` and the relevant SDK/service requirements rather than copying
version numbers from old reports.

```bash
agentbench --help
agentbench agent add --help
python -m pytest -q tests/test_agent_build*.py tests/test_agent_manifest*.py
python -m pytest -q tests/test_sdk_directory.py tests/test_kuma*.py
```

Choose checks relevant to the change. Run interceptor tests in an environment
with that service's dependencies installed. Add regressions for actual failures;
use `tests/test_issue<number>.py` when addressing a numbered repository issue.
Do not assume bundled Agent directories exist: use self-contained fixtures for
unit tests and explicit prerequisites for integration tests.

For SDK integration changes, also retain a real container acceptance artifact
containing the Case, Agent output and Judge result. Mock responses or generated
configuration alone do not demonstrate that the real Agent/SDK workflow works.
Distinguish a Judge's behavioral finding from an execution or evidence failure.
Report skipped, blocked and failed checks accurately; do not hide them to claim
the suite passes.

## Maintain the user documentation

Keep README's setup and onboarding links usable. Order the Agent addition guide
as environment setup, the runnable add command, then each file's purpose. Mark
automatic internal records separately from user-prepared configuration. Add
troubleshooting as issues are confirmed.

- Separate host CLI dependencies, frontend build dependencies, host SDK validation
  and Agent image/service dependencies. Derive versions from pyproject.toml,
  web/package-lock.json and plugin requirements; explain which workflows need them.
- Document Node/npm and `npm ci` / `npm run build` before promising a viewer.
  Headless runs do not need frontend assets; Python serves the built normal viewer.
- Verify installation with CLI help, SDK discovery and the zero-credential offline
  demo before asking users to configure paid services. Use the printed timestamped
  result path when demonstrating `view`.
- Verify commands against actual `--help`, configuration precedence against code,
  and local links against exact Git path spelling/case. Do not leave empty
  troubleshooting headings or links to removed reports/CLI guides.
- Keep unsuffixed public documentation entry points in English. Put translations
  under docs/otherLanguages/ with language suffixes and reciprocal language links.
  Maintain How To Add Agent in every README language, with the same environment,
  command and file-purpose structure. Each localized README must link to its own
  onboarding translation; label any remaining untranslated deeper references.
- Treat issue reports as claims to check against the current revision. Record
  documentation fixes separately from unresolved runtime/packaging issues; never
  claim that documenting a workaround resolves a code defect.
- Keep readiness, enabled state and Case counts in resources/registry.toml rather
  than duplicating transient acceptance claims in documentation.
- Explain execution status separately from Judge verdict. Do not equate a received
  report with host acceptance, evidence insufficiency with a proven Agent defect,
  or a JSON export with a standalone HTML/full-trace archive.
