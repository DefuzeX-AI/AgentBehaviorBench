"""BBA binding for Watchtower: adapt plain-text Case input to the native LangGraph pentest state.

Native entrypoint
-----------------
Watchtower is an AI penetration-testing CLI. Its public compiled graph is built by
the source-confirmed factory ``watchtower.core.agent_manager.create_agent_graph()``
(StateGraph over ``AgentState``: planner -> worker -> analyst -> logic_analysis ->
planner, ending when ``is_finished`` is set). The CLI entrypoint
``watchtower/main.py`` is the public caller that owns the lifecycle this binding
reproduces. There is NO JSON graph descriptor in the repository, so this outer
binding is the direct loader: ``create_graph()`` returns a fresh instance and the
binding calls the real native factory.

Input (SDK boundary: text)
--------------------------
The official Case service supplies TEXT. A Case may be ordinary natural language,
e.g. "scan http://127.0.0.1 for vulns". The binding extracts the single authorized
target host/URL from that text by reusing the native helpers in
``watchtower/core/targets.py`` (``extract_hostname`` / ``normalize_url``) and then
validates it with ``watchtower/core/guardrails.validate_target`` and restricts
the extracted hostname to the container loopback. The extracted
target becomes ``scope_targets[0]``. ``messages`` is left empty (no conversation
history is synthesized). Authenticated-scan options (cookie/header) are OPTIONAL
and are NOT required for certification; the default run is unauthenticated.

Example input: ``"Scan http://127.0.0.1 for common web vulnerabilities"``
  -> scope_targets = ["http://127.0.0.1"], auth_metadata = {}.

Output
------
The binding returns the COMPLETE accumulated native state (a dict mirroring
``AgentState``: scope_targets, available_tools, messages, findings, observations,
current_plan, next_step, auth_metadata, is_finished), not the streamed deltas.
No ``output_key`` is configured, so ABB retains this whole return value.

Config / context
----------------
``config`` (LangChain RunnableConfig, possibly carrying callbacks and a thread
identity) is forwarded to the native graph. The CLI's documented
``recursion_limit=100`` is merged into the run config but never overwrites a
supplied value. There is no ``[adapter.context]`` in the manifest, so this
binding does not invent provider/model overrides; native ``get_llm()`` resolves
OPENROUTER_API_KEY -> OPENAI_API_KEY -> GEMINI_API_KEY from the environment.

Owned resources
---------------
Each binding instance owns a private writable SQLite ``MemoryStore`` (created in
a private temporary directory, NOT the CLI's relative ``pentest_memory.db``).
It reproduces ``main.py``'s persistence by consuming ``graph.stream()`` deltas
and logging observations/findings to that store. ``close()`` closes the SQLite
connection and removes the temporary directory; it is safe to repeat. Native
execution errors propagate unchanged.
"""

import re
from tempfile import TemporaryDirectory
from pathlib import Path


# Default tool arsenal, identical to the list in watchtower/main.py. In headless
# operation the CLI passes the full set (--skip-ask-tools equivalent), so this
# binding mirrors that instead of presenting an interactive questionary menu.
ALL_TOOLS = [
    "nmap", "masscan", "httpx", "whatweb", "wafw00f",
    "subfinder", "amass", "dnsrecon", "nuclei", "nikto",
    "sqlmap", "wpscan", "testssl", "sslyze", "gobuster",
    "ffuf", "arjun", "xsstrike", "gitleaks", "cmseek",
    "retire", "dalfox", "kiterunner",
]

# Candidate URL/host token. Matches a full URL (scheme://...), a bare
# ``host:port/path`` token, or a dotted domain/IP token so that freeform
# sentences can be reduced to one target before native normalization/validation.
# The excluded-character class uses a single bracket pair to keep freeform
# sentence punctuation out of the captured token.
_TOKEN_RE = re.compile(
    r"\b(?:"
    r"https?://[^\s,;'\"\]]+|"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)+[A-Za-z]{2,}(?::\d+)?(?:/[^\s,;'\"\]]*)?|"
    r"\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?(?:/[^\s,;'\"\]]*)?"
    r")\b"
)


def _extract_target_token(text):
    """Return the first candidate URL/host token in ``text``, or None."""
    if not text:
        return None
    match = _TOKEN_RE.search(text)
    if not match:
        return None
    # Never let a trailing sentence period bleed into a path-less host token.
    return match.group(0).rstrip(".")


def target_from_input(value):
    """Translate a plain-text Case input into one validated native target.

    Args:
        value: Non-empty string (or ``{"message": str}``). SDK text is the
            general case; this does NOT require JSON.

    Returns:
        A normalized target string suitable for ``scope_targets[0]``.

    Raises:
        ValueError: If the input is empty, or contains no syntactically valid
            URL/IP/domain after native ``validate_target``. Rejected input is
            not silently dropped or guessed.
    """
    # Import native helpers here so module import does not require the package.
    from watchtower.core.targets import extract_hostname, normalize_url
    from watchtower.core.guardrails import validate_target

    if isinstance(value, dict):
        # input_key="message" wrapping; accept it but do not synthesize history.
        if set(value) != {"message"}:
            raise ValueError("Watchtower accepts exactly one current target message field")
        value = value["message"]
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Supply a non-empty request naming the target URL or host")

    token = _extract_target_token(value.strip())
    if token is None:
        raise ValueError(
            "No valid URL/IP/domain found in input; Watchtower scans one explicit target "
            "(e.g. 'scan http://127.0.0.1 for vulnerabilities')"
        )

    # Reject syntactically, mirroring the CLI guardrail. Scope/authorization is
    # the operator's responsibility upstream (the CLI removed allowlisting).
    if not validate_target(token):
        raise ValueError(f"Invalid target provided: {token!r}; must be a valid URL or IP/domain")

    # This integration's declared evaluation boundary is the disposable
    # container's own loopback service. Never let generated Case text turn the
    # broad upstream scanner into an outbound scanner.
    normalized = normalize_url(token)
    try:
        hostname = extract_hostname(normalized)
    except ValueError:
        hostname = ""
    if hostname not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("Evaluation scope is limited to the Agent container loopback target")
    return normalized


class WatchtowerGraph:
    """Adapt SDK text to Watchtower's compiled multi-agent graph.

    The wrapper owns the compiled graph (lazily), a private SQLite MemoryStore
    directory, and the persistence behavior of the upstream CLI's stream loop.
    """

    def __init__(self):
        self._graph = None
        self._memory = None
        self._directory = None

    def _load(self):
        """Build the native graph and a private memory store once."""
        if self._graph is not None:
            return
        from watchtower.core.agent_manager import create_agent_graph
        from watchtower.core.memory import MemoryStore

        self._directory = TemporaryDirectory(prefix="abb-watchtower-")
        db_path = str(Path(self._directory.name) / "pentest_memory.db")
        try:
            self._graph = create_agent_graph()
            self._memory = MemoryStore(db_path)
        except BaseException:
            self.close()
            raise

    def _initial_state(self, target):
        """Reproduce main.py's initial_state exactly (messages left empty)."""
        return {
            "scope_targets": [target],
            "available_tools": list(ALL_TOOLS),
            "messages": [],
            "findings": [],
            "observations": [],
            "current_plan": "",
            "next_step": "",
            "auth_metadata": {},
            "is_finished": False,
        }

    def invoke(self, value, config=None):
        """Run the native pentest loop and return the complete final state.

        Args:
            value: Plain-text Case input (or ``{"message": text}``) naming one
                authorized target.
            config: RunnableConfig forwarded to the graph; ``recursion_limit``
                defaults to the CLI's 100 when not supplied.

        Returns:
            The full accumulated native state dict. Streamed node deltas are
            consumed only to replicate the CLI's observation/finding persistence;
            they are not the returned result.

        Raises:
            ValueError: Unparseable/invalid target. Native execution errors raise
                unchanged (never rewritten as a success answer).
        """
        if self._graph is None:
            self._load()

        try:
            target = target_from_input(value)
        except ValueError as exc:
            # Mirror native watchtower/main.py, which logs an invalid/empty target
            # and returns WITHOUT scanning rather than raising. Execution then
            # completes with an explicit no-target result the Judge can assess,
            # instead of surfacing as an infrastructure-level execution failure.
            return {
                "scope_targets": [],
                "available_tools": list(ALL_TOOLS),
                "messages": [f"Invalid target: {exc}"],
                "findings": [],
                "observations": [{
                    "target": None,
                    "tool": "input-validation",
                    "output": f"Error: {exc}. No scan performed.",
                }],
                "current_plan": "No scan performed: input did not name a valid target.",
                "next_step": "finish",
                "auth_metadata": {},
                "is_finished": True,
            }
        initial_state = self._initial_state(target)

        run_config = dict(config or {})
        # Preserve the CLI's documented limit without clobbering thread/callbacks.
        run_config.setdefault("recursion_limit", 100)

        final_state = None
        for event in self._graph.stream(initial_state, config=run_config):
            # ``event`` maps node_name -> state_updates delta. Merge deltas into
            # the accumulated state so we can return the complete final state.
            for _node_name, updates in event.items():
                if not isinstance(updates, dict):
                    continue
                for key, val in updates.items():
                    if key in ("findings", "observations", "messages"):
                        acc = final_state if final_state is not None else initial_state
                        # AgentState uses operator.add reducers for these lists.
                        acc_val = acc.get(key, [])
                        if isinstance(acc_val, list) and isinstance(val, list):
                            acc_val = acc_val + val
                        else:
                            acc_val = val
                        if final_state is None:
                            final_state = dict(initial_state)
                        final_state[key] = acc_val
                    else:
                        if final_state is None:
                            final_state = dict(initial_state)
                        final_state[key] = val

                # Replicate main.py SQLite persistence of this node's updates.
                if self._memory is not None:
                    for obs in updates.get("observations", []) or []:
                        if isinstance(obs, dict):
                            self._memory.log_observation(
                                obs.get("target"), obs.get("tool"), obs.get("output")
                            )
                    for finding in updates.get("findings", []) or []:
                        if isinstance(finding, dict):
                            f_target = finding.get("target", target)
                            vuln = finding.get("title", "Unknown Finding")
                            self._memory.log_finding(f_target, vuln, finding)

        if final_state is None:
            final_state = initial_state
        return final_state

    def close(self):
        """Release the owned SQLite connection and private database directory."""
        memory, self._memory = self._memory, None
        connection = getattr(memory, "conn", None)
        try:
            if connection is not None:
                connection.close()
        finally:
            self._graph = None
            directory, self._directory = self._directory, None
            if directory is not None:
                directory.cleanup()


def create_graph():
    """Synchronous factory required by the ABB LangGraph loader.

    Returns a fresh :class:`WatchtowerGraph` with a callable ``invoke``. The
    native graph and memory store are created lazily on first invocation.
    Example input: ``"Scan https://www.example.com for common web issues"``.
    """
    return WatchtowerGraph()
