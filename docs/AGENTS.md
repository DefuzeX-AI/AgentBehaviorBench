# Agent Documentation Guide

Before changing AgentBench, read the documentation that matches the task scope.

## CLI

If you need to understand, use, or modify the AgentBench CLI, read
[`CLI.md`](./CLI.md) first. That file is the source of truth for the CLI and
covers:

- complete usage for `run`, `view`, and `certify`;
- all positional arguments, options, defaults, and compatibility forms;
- interactive prompts, exit codes, JSON results, and viewer lifecycle;
- certification and Registry update rules from `adapting` to `ready`;
- the CLI feature registration structure and implementation rules for new
  commands.

When changing CLI behavior, arguments, defaults, output files, or exit codes,
update `CLI.md` and the relevant tests in the same change.

## Adding Agents

If you need to add, port, or validate an Agent, read
[`How To Add Agent.md`](./How%20To%20Add%20Agent.md). It is the short entry
point for the onboarding flow and reading path.

For the current internal beta's built-in KUMA evaluator, users must download the SDK from
[`Defuze-SDK` dev branch](https://github.com/DefuzeX-AI/Defuze-SDK/tree/dev)
into a sibling `Defuze-SDK` checkout, or supply its path through `sdk_source`.
The KUMA container adapter installs that source in its image. Other evaluation
SDKs have their own requirements and do not require KUMA. See `SDK.md` and
`SDK替换.md` when adapting another evaluator or Case source.

Continue reading based on the task scope:

- A downloaded Agent has not been converted yet: read
  [`Agents/Factory.md`](./Agents/Factory.md).
- Docker, package data, native Agent API behavior, or the Model Interceptor is involved:
  read [`Agents/Runtime.md`](./Agents/Runtime.md).
- You need to understand `certify`, `ready`, Judge FAIL, or result files:
  read [`Agents/Certify.md`](./Agents/Certify.md).
- You already have a concrete error message: start with
  [`Agents/Troubleshooting.md`](./Agents/Troubleshooting.md).
- You need the complete background: read
  [`Agents/Reference.md`](./Agents/Reference.md).

When Agent onboarding involves `agentbench certify` or normal batch selection
rules, read `CLI.md` as well.
