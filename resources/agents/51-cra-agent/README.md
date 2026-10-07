# CRA Compliance Monitoring Agent (LangGraph unit)

Upstream: [kulkarnirohit123/cra-agent](https://github.com/kulkarnirohit123/cra-agent) at
`4d819a56d825ca14013997958eeb3d0e13ab7ebb`. The checkout is acquired from Git
(`[source] method = "git"`) and is not committed: `prepare_agent_source()` restores this
exact revision into `agent/` before an evaluation opens, the same way
`resources/agents/12-minimax-code` does. No descriptor was added because upstream builds
its graph in Python rather than from a `langgraph.json`, so `agent.toml` declares the
outer binding `bindings/bridge.py:create_graph` with `output_key = "answer"`.

Upstream is Apache-2.0 (`LICENSE` ships with the checkout). Nothing under `agent/` is
modified: the revision in `[source]` is the provenance record, and the build consumes the
restored tree unchanged.

## What runs

Upstream has no single request/response entrypoint. `src/main.py` starts a git polling
loop beside a FastAPI webhook server, and `GitHubPollingAgent` polls the GitHub API; both
run until killed. The application logic behind them is
`src/agents/orchestrator.CRAOrchestrator`, a LangGraph state machine over `AgentState`
whose public method is `run(commit_info, changed_files)`:

```
scan_commit -> filter_suppressed -> (findings?) -> triage_findings
            -> create_jira_tickets -> (fixable?) -> auto_fix -> END
```

The binding calls that method once per Case input. The Case text is written to
`submission.py` in a throwaway git workspace and treated as a single added file -- the
smallest faithful stand-in for the commit a daemon would otherwise hand to
`CRAOrchestrator.run`. `src/main.py`, `src/webhook/`, `src/core/git_monitor.py`,
`src/core/github_poller.py` and `src/dashboard/` are not exercised.

Five agents are upstream code and stay untouched: `ScannerAgent`, `TriageAgent`,
`JiraAgent`, `FixerAgent` and the two condition functions that route between them. Only
`TriageAgent` (`TRIAGE_PROMPT_TEMPLATE`) and `FixerAgent` (`FIX_PROMPT_TEMPLATE`) reach a
model, both through `LLMClient.generate_json`.

## An upstream defect this unit works around

`CRAOrchestrator._build_graph` anchors two conditional edges on names it never registers:

```python
workflow.add_edge("filter_suppressed", "should_triage")
workflow.add_conditional_edges("should_triage", self._should_triage_condition, {...})
workflow.add_edge("create_jira_tickets", "should_fix")
workflow.add_conditional_edges("should_fix", self._should_fix_condition, {...})
```

`should_triage` and `should_fix` are never passed to `add_node`. They appear only in the
class docstring's ASCII diagram, where they mark where a decision is taken. Compilation
therefore fails outright, on any langgraph version:

```
ValueError: Found edge starting at unknown node 'should_fix'
```

`bindings/bridge.py` subclasses the orchestrator and restates the same graph with each
decision marker folded into the conditional edge of the node preceding it --
`add_conditional_edges("filter_suppressed", self._should_triage_condition, {...})` and the
equivalent for `create_jira_tickets`. The node bodies, both condition functions, all four
agents and every prompt are the upstream ones; only those two edge registrations differ.
The subclass exists so `agent/` stays byte-identical to the published revision. Upstream
has no test covering `CRAOrchestrator` (`tests/test_agents/` contains only `__init__.py`),
which is consistent with the defect surviving publication.

## A second upstream defect, left as published

`FixerAgent._generate_fix` builds its prompt with

```python
language=finding.file_extension.lstrip(".") or "text",
```

but `finding` is a `TriagedFinding`, and `file_extension` is a field of `FileChange`, not
of `Finding`. Every auto-fix attempt therefore raises

```
AttributeError: 'TriagedFinding' object has no attribute 'file_extension'
```

which `FixerAgent.fix_finding` catches and turns into `Action(success=False, error=...)`.
The auto-fix step is unreachable in the published revision.

Unlike the graph defect this one is deliberately **not** worked around. The graph defect
blocks compilation, so nothing runs without fixing it; this one lets the workflow complete
and report the failure. Substituting an extension would mean the binding supplying a
judgement the upstream code never makes, and it would hide a real defect behind a green
run. The Agent's report shows the failed fix attempts as failed, which is what the
published code actually does.

## Scanners

`ScannerAgent` defaults to the dependency/SAST/secrets trio, and each one shells out to an
external CLI. In this deployment only the secrets scanner is provisioned:

| Scanner | Tool | Provisioned | Effect |
|---|---|---|---|
| secrets | gitleaks (static binary) | yes | produces findings; fully offline |
| dependency | pip-audit | no | `BaseScanner.run` catches the failure and returns no findings |
| SAST | semgrep | no | same |

pip-audit resolves advisories against OSV or PyPI over the network on every call, and
semgrep fetches the `p/owasp-top-ten` and `p/cwe-top-25` registry rulesets on first use.
Neither has a route declared in `agent.toml`, so neither can succeed here. Their absence
is left visible rather than stubbed: a scanner that cannot run contributes no findings,
and the report says how many findings survived rather than claiming a clean result.

`SecretsScanner` reports at `Severity.HIGH` and above and screens out obvious placeholders
(`EXAMPLE_KEY`, `xxx`, `changeme`, ...). gitleaks output is parsed, and the matched secret
is masked in the snippet before it reaches any prompt.

## Environment

- `OPENAI_API_KEY` (intercepted credential; ABB injects a placeholder and substitutes the
  target key). Both model call sites go through `LLMClient`, which builds a `ChatOpenAI`
  against `https://api.openai.com/v1` -- the route declared for
  `POST /v1/chat/completions`. Run ABB with the target model variables
  (`OPENROUTER_API_KEY` / `OPENROUTER_BASE_URL` / `OPENROUTER_MODEL`).
- No Jira, GitHub or EUVD credential, and none is requested.

## Network

Only the model route `POST api.openai.com /v1/chat/completions`. No tool route is
declared, so a Case that makes the Agent reach Jira, a forge or the advisory databases
hits an undeclared host -- the intended, expected result.

## Not deployed

`src/main.py` and the daemons it starts, the FastAPI webhook server, the Streamlit
dashboard, the GitHub App integration, the EUVD scheduler and the auto-fix push/PR path.
Ticket creation, branch creation and commits do run, but with no ticket server and no
remote: `JiraAgent.create_ticket` returns its own `FAILED` ticket, `GitClient.push`
returns `False`, and `GitClient.create_pull_request` is upstream's own placeholder that
returns a constructed URL without contacting a forge.
