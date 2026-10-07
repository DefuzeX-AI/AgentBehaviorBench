"""\u667a\u80fd\u4f53\u62bd\u8c61 + \u7528\u6237\u53ef\u6269\u5c55\u7684\u6d88\u606f\u5904\u7406\u94a9\u5b50.

\u7c7b\u5c42\u7ea7
======

* :class:`BaseAgent` \u2014 \u62bd\u8c61\u57fa\u7c7b, \u5b9a\u4e49\u6240\u6709\u667a\u80fd\u4f53\u5171\u540c\u7684 gym-like \u63a5\u53e3:
  ``reset / process_inbox / act / on_message / send``. \u6846\u67b6\u5176\u4ed6\u90e8\u5206
  (\u4f8b\u5982 :class:`MultiAgentRuntime`) \u53ea\u4f9d\u8d56\u8fd9\u4e2a\u57fa\u7c7b.

* :class:`GenericAgent` \u2014 \u9ed8\u8ba4\u5b9e\u73b0, \u628a\u51b3\u7b56\u59d4\u6258\u7ed9\u4e00\u4e2a\u5916\u90e8 :class:`PerAgentPolicy`.
  \u7edd\u5927\u591a\u6570 case (\u914d\u9001 / \u706d\u706b / \u536b\u661f\u89c2\u6d4b ...) \u7528\u8fd9\u4e2a\u5c31\u591f.

* :class:`PerAgentPolicy` (Protocol) \u2014 \u5355\u673a\u7b56\u7565\u5951\u7ea6;
  \u5b9e\u73b0\u8005\u53ea\u9700\u63d0\u4f9b ``async def act(self, observation, inbox, scenario, history)``
  \u2192 ``(action, outgoing_messages)``.
"""

from __future__ import annotations

import inspect
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol

from app.modules.envs.multiagent.messaging import Message, MessageBus

logger = logging.getLogger(__name__)

Action = dict[str, Any]
Observation = dict[str, Any]
HandlerFn = Callable[["MessageContext"], Awaitable[Message | None] | Message | None]


@dataclass
class MessageContext:
    """\u6d88\u606f\u5904\u7406\u56de\u8c03\u62ff\u5230\u7684\u4e0a\u4e0b\u6587."""

    message: Message
    agent: "BaseAgent"
    inbox: list[Message]


class PerAgentPolicy(Protocol):
    """\u5355\u673a\u7b56\u7565\u5951\u7ea6. \u5b9e\u73b0\u8005\u65e0\u9700\u7ee7\u627f; \u9e2d\u5b50\u7c7b\u578b\u5373\u53ef."""

    async def act(
        self,
        observation: Observation,
        inbox: list[Message],
        scenario: Any,
        history: list[dict[str, Any]],
    ) -> tuple[Action, list[Message]]: ...


class BaseAgent(ABC):
    """\u6240\u6709\u667a\u80fd\u4f53\u7684\u62bd\u8c61\u57fa\u7c7b \u2014 gym-like \u63a5\u53e3.

    \u6bcf\u4e2a step \u7531 :class:`MultiAgentRuntime` \u6309\u987a\u5e8f\u8c03\u7528:

    1. :meth:`process_inbox` \u2014 \u5904\u7406\u4e0a\u8f6e\u6d88\u606f;
    2. :meth:`act` \u2014 \u770b\u89c2\u6d4b\u51b3\u7b56, \u8fd4\u56de (action, outgoing_messages).

    \u7528\u6237\u7ee7\u627f\u672c\u7c7b\u81ea\u5b9a\u4e49 agent \u65f6\u53ea\u9700\u91cd\u5199 ``act``; \u63a8\u8350\u7528 :class:`GenericAgent`.
    """

    def __init__(self, name: str, bus: MessageBus) -> None:
        self.name = name
        self.bus = bus
        self.bus.register(name)
        self.handlers: dict[str, HandlerFn] = {}
        self.default_handler: HandlerFn | None = None
        self.history: list[dict[str, Any]] = []
        self.outgoing_log: list[Message] = []
        self.incoming_log: list[Message] = []

    def on_message(self, type: str) -> Callable[[HandlerFn], HandlerFn]:
        def decorator(fn: HandlerFn) -> HandlerFn:
            self.handlers[type] = fn
            return fn

        return decorator

    def on_any_message(self, fn: HandlerFn) -> HandlerFn:
        self.default_handler = fn
        return fn

    def send(
        self,
        type: str,
        payload: dict[str, Any] | None = None,
        *,
        receiver: str | None = None,
        in_reply_to: str | None = None,
    ) -> Message:
        msg = Message(
            sender=self.name,
            type=type,
            payload=dict(payload or {}),
            receiver=receiver,
            in_reply_to=in_reply_to,
        )
        self.bus.send(msg)
        self.outgoing_log.append(msg)
        return msg

    async def _invoke_handler(self, fn: HandlerFn, ctx: MessageContext) -> Message | None:
        result = fn(ctx)
        if inspect.isawaitable(result):
            result = await result
        return result if isinstance(result, Message) else None

    async def process_inbox(self) -> list[Message]:
        inbox = self.bus.drain(self.name)
        if not inbox:
            return []
        self.incoming_log.extend(inbox)
        for msg in inbox:
            handler = self.handlers.get(msg.type) or self.default_handler
            if handler is None:
                continue
            try:
                ctx = MessageContext(message=msg, agent=self, inbox=inbox)
                reply = await self._invoke_handler(handler, ctx)
            except Exception as exc:  # noqa: BLE001
                logger.exception("[%s] handler %s \u62a5\u9519: %s", self.name, msg.type, exc)
                continue
            if reply is not None:
                if not reply.sender:
                    reply.sender = self.name
                self.bus.send(reply)
                self.outgoing_log.append(reply)
        return inbox

    @abstractmethod
    async def act(
        self,
        observation: Observation,
        scenario: Any,
        last_inbox: list[Message],
    ) -> tuple[Action, list[Message]]: ...

    def reset(self) -> None:
        """\u5141\u8bb8 runtime \u5728\u65b0 episode \u5f00\u59cb\u524d\u6e05\u7a7a\u5185\u90e8\u72b6\u6001."""

        self.history.clear()
        self.outgoing_log.clear()
        self.incoming_log.clear()

    def stats(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "sent": len(self.outgoing_log),
            "received": len(self.incoming_log),
            "handlers": sorted(self.handlers),
        }


class GenericAgent(BaseAgent):
    """\u9ed8\u8ba4 agent \u5b9e\u73b0: \u628a\u51b3\u7b56\u59d4\u6258\u7ed9\u4e00\u4e2a :class:`PerAgentPolicy`."""

    def __init__(self, name: str, policy: PerAgentPolicy, bus: MessageBus) -> None:
        super().__init__(name=name, bus=bus)
        self.policy = policy

    async def act(
        self,
        observation: Observation,
        scenario: Any,
        last_inbox: list[Message],
    ) -> tuple[Action, list[Message]]:
        action, outgoing = await self.policy.act(observation, last_inbox, scenario, self.history)
        sent: list[Message] = []
        for msg in outgoing or []:
            if not msg.sender:
                msg.sender = self.name
            self.bus.send(msg)
            self.outgoing_log.append(msg)
            sent.append(msg)
        self.history.append(
            {
                "observation": observation,
                "action": action,
                "outgoing": [m.to_dict() for m in sent],
            }
        )
        return action, sent
