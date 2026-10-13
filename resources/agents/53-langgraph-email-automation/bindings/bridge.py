"""ABB text boundary for kaymen99/langgraph-email-automation.

Upstream entrypoint (source under ``agent/`` is unchanged):

* ``main.py`` builds the initial ``GraphState`` and streams
  ``src/graph.py:Workflow().app``.
* ``Nodes.categorize_email`` consumes ``state["emails"][-1]`` and reads its
  ``.body``, so the Case input is the customer email body.

Deployment boundary (no mailbox):

* ``Nodes.__init__`` constructs ``GmailToolsClass``, whose ``_get_gmail_service()``
  requires ``token.json``/``credentials.json`` and otherwise starts an interactive
  ``InstalledAppFlow`` consent flow. This container has no interactive user, no
  Gmail OAuth material and no reachable ``gmail.googleapis.com``, so the upstream
  Gmail transport is replaced below with a transport that reports the mailbox as
  unavailable. The graph structure, every node and all reasoning stay upstream's.
* The Case input is delivered through that transport as the single message to
  process, which is the deployment's replacement for inbox polling. No draft is
  created in a real mailbox, and none is claimed to have been.
* ``src/agents.py`` resolves the Chroma index with the relative path ``db``, and
  ``main.py`` runs from the repository root. The working directory here is the ABB
  unit root, so the binding switches to the imported source root before building
  the graph.

The reply text produced by ``email_writer`` is the result, returned as
``generated_email`` (matching ``agent.toml``'s ``output_key``).
"""
import os
from pathlib import Path

# ---- Mailbox transport replacement (no Gmail access in this deployment) ----
_EMAIL_FOR_MOCK = None


class _NoMailboxGmailTools:
    """Stand-in for ``GmailToolsClass`` for a deployment with no mailbox.

    ``fetch_unanswered_emails`` returns the single Case-supplied message;
    ``create_draft_reply``/``send_reply`` report that nothing was sent. Upstream's
    own methods already swallow Gmail failures, so the observable contract is the
    same: no mailbox I/O happens.
    """

    def __init__(self):
        self.service = None

    def fetch_unanswered_emails(self, max_results=50):
        return [_EMAIL_FOR_MOCK] if _EMAIL_FOR_MOCK is not None else []

    def fetch_recent_emails(self, max_results=50):
        return []

    def fetch_draft_replies(self):
        return []

    def create_draft_reply(self, initial_email, reply_text):
        return None

    def send_reply(self, initial_email, reply_text):
        return None

    def _get_gmail_service(self):
        return None

    def _should_skip_email(self, email_info):
        return False


# ``src/nodes.py`` binds the name with ``from .tools.GmailTools import
# GmailToolsClass``, so the module attribute must be replaced before src.nodes is
# imported (src.graph below imports it).
import src.tools.GmailTools as _gmail_module

_gmail_module.GmailToolsClass = _NoMailboxGmailTools

from src.graph import Workflow
from src.state import Email


def _email_from_input(value):
    """Build the native ``Email`` payload from the SDK input.

    Accepts a plain-text customer email body or exactly ``{"message": body}``.
    Fields a mailbox would have supplied (id, threadId, messageId, references,
    sender, subject) stay empty because this deployment has no mailbox.
    """
    if isinstance(value, dict):
        if set(value) != {"message"}:
            raise ValueError(
                "Email automation expects one current message. "
                "Supply a text string or {'message': body}."
            )
        value = value["message"]
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Email body must be a non-empty string.")
    return {
        "id": "",
        "threadId": "",
        "messageId": "",
        "references": "",
        "sender": "",
        "subject": "",
        "body": value,
    }


class EmailAutomationBinding:
    def __init__(self):
        self._app = None
        self._closed = False
        # Upstream's Chroma index path ("db") is relative to the repository root.
        self._source_root = Path(__file__).resolve().parents[1] / "agent"

    def _ensure_app(self):
        if self._app is None:
            if not self._source_root.is_dir():
                raise RuntimeError(f"Imported Agent source not found at {self._source_root}")
            os.chdir(self._source_root)
            self._app = Workflow().app
        return self._app

    def invoke(self, value, config=None):
        """Process one customer email and return the generated draft.

        Args:
            value: The customer email body as plain text or ``{'message': body}``.
            config: RunnableConfig forwarded to the compiled LangGraph.

        Returns:
            A dict with ``generated_email`` holding the draft written by the
            ``email_writer`` node.

        Raises:
            ValueError if the input is invalid.
            RuntimeError if the binding is closed.
            Native graph exceptions propagate unchanged.
        """
        if self._closed:
            raise RuntimeError("Email automation binding is closed.")

        email_dict = _email_from_input(value)
        app = self._ensure_app()

        global _EMAIL_FOR_MOCK
        _EMAIL_FOR_MOCK = email_dict
        try:
            # The entry node overwrites ``emails`` with the transport's result.
            initial_state = {
                "emails": [],
                "current_email": Email(
                    id="", threadId="", messageId="",
                    references="", sender="", subject="", body=""
                ),
                "email_category": "",
                "generated_email": "",
                "rag_queries": [],
                "retrieved_documents": "",
                "writer_messages": [],
                "sendable": False,
                "trials": 0,
            }
            # Shallow copy only: the worker's config carries live callback objects
            # (deep-copying them raises "cannot pickle '_thread.lock' object").
            run_config = dict(config or {})
            run_config.setdefault("recursion_limit", 100)
            final_state = app.invoke(initial_state, config=run_config)
        finally:
            # Leave no message behind for the next invocation in this Case.
            _EMAIL_FOR_MOCK = None

        # ``agent.toml`` projects ``generated_email`` as the text answer; the rest of
        # the native final state is retained so the decision behind an empty draft
        # (an ``unrelated`` message is never replied to) stays visible in the
        # evidence instead of looking like a missing response.
        return {
            "generated_email": final_state.get("generated_email", ""),
            "email_category": final_state.get("email_category", ""),
            "sendable": final_state.get("sendable", False),
            "trials": final_state.get("trials", 0),
        }

    def close(self):
        """Release the graph reference; safe to repeat."""
        self._closed = True
        self._app = None
        global _EMAIL_FOR_MOCK
        _EMAIL_FOR_MOCK = None


def create_graph():
    """Return a fresh binding; example input: 'I need help with my account' or
    {'message': 'I need help with my account'}."""
    return EmailAutomationBinding()
