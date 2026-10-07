"""\u667a\u80fd\u4f53\u4e4b\u95f4\u7684\u901a\u4fe1\u539f\u8bed (Message + MessageBus).

\u8ddf Gym / LangGraph \u89e3\u8026, \u53ef\u72ec\u7acb\u5355\u6d4b, \u4e5f\u53ef\u5728\u4efb\u4f55 case \u91cc\u590d\u7528.
"""

from __future__ import annotations

import json
import uuid
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from typing import Any

from app.modules.envs.task_id import beijing_iso


@dataclass
class Message:
    """\u667a\u80fd\u4f53\u4e4b\u95f4\u4f20\u9012\u7684\u4e00\u6761\u6d88\u606f."""

    sender: str
    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    receiver: str | None = None
    msg_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    in_reply_to: str | None = None
    timestamp: str = field(default_factory=lambda: beijing_iso())

    def reply(self, type: str, payload: dict[str, Any] | None = None) -> "Message":
        """\u6784\u9020\u4e00\u4e2a\u671d\u5411\u539f\u53d1\u9001\u8005\u7684\u56de\u590d\u6d88\u606f, \u81ea\u52a8\u586b ``in_reply_to``."""

        return Message(
            sender=self.receiver or "system",
            receiver=self.sender,
            type=type,
            payload=dict(payload or {}),
            in_reply_to=self.msg_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def __repr__(self) -> str:  # pragma: no cover
        target = self.receiver or "*"
        return f"<Msg {self.sender}\u2192{target} {self.type} id={self.msg_id[:6]}>"


class MessageBus:
    """\u6240\u6709 agent \u5171\u4eab\u7684\u8fdb\u7a0b\u5185 pub-sub \u603b\u7ebf.

    \u7ebf\u7a0b\u4e0d\u5b89\u5168, \u5355\u4e8b\u4ef6\u5faa\u73af\u4f7f\u7528. \u5173\u952e\u64cd\u4f5c:

    * :meth:`register` \u2014 agent \u767b\u8bb0\u540d\u5b57\u4ee5\u4fbf\u63a5\u6536\u5e7f\u64ad
    * :meth:`send`     \u2014 \u6295\u9012\u6d88\u606f (``receiver=None`` \u8868\u793a\u5e7f\u64ad\u7ed9\u9664\u81ea\u5df1\u5916\u7684\u5168\u90e8\u8ba2\u9605\u8005)
    * :meth:`drain`    \u2014 \u4e00\u6b21\u6027\u53d6\u8d70\u67d0 agent \u7684\u5168\u90e8\u672a\u8bfb\u6d88\u606f
    * :meth:`history`  \u2014 \u5168\u91cf\u5ba1\u8ba1 / \u843d\u76d8
    """

    def __init__(self) -> None:
        self._inboxes: dict[str, deque[Message]] = defaultdict(deque)
        self._history: list[Message] = []
        self._subscribers: set[str] = set()

    def register(self, agent_name: str) -> None:
        self._subscribers.add(agent_name)

    def subscribers(self) -> list[str]:
        return sorted(self._subscribers)

    def send(self, message: Message) -> None:
        self._history.append(message)
        if message.receiver is None:
            for name in self._subscribers:
                if name != message.sender:
                    self._inboxes[name].append(message)
        else:
            self._inboxes[message.receiver].append(message)

    def drain(self, agent_name: str) -> list[Message]:
        if agent_name not in self._inboxes:
            return []
        msgs = list(self._inboxes[agent_name])
        self._inboxes[agent_name].clear()
        return msgs

    def peek(self, agent_name: str) -> list[Message]:
        return list(self._inboxes.get(agent_name) or [])

    def history(self) -> list[Message]:
        return list(self._history)

    def history_json(self) -> str:
        return json.dumps([m.to_dict() for m in self._history], ensure_ascii=False)
