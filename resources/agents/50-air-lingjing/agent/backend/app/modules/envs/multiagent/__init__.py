"""\u901a\u7528\u591a\u667a\u80fd\u4f53\u62bd\u8c61 \u2014 \u9879\u76ee\u4e3b\u6846\u67b6\u53ef\u590d\u7528\u7684\u6838\u5fc3.

\u6a21\u5757
----

* :mod:`messaging` \u2014 ``Message`` + ``MessageBus`` \u901a\u4fe1\u539f\u8bed
* :mod:`agent`     \u2014 ``BaseAgent`` \u62bd\u8c61 + ``GenericAgent`` \u9ed8\u8ba4\u5b9e\u73b0 + ``PerAgentPolicy`` \u534f\u8bae
* :mod:`runtime`   \u2014 ``MultiAgentRuntime`` \u4e09\u9636\u6bb5\u8c03\u5ea6 (inbox \u2192 act \u2192 env.step)

\u8c03\u5ea6\u65f6\u5e8f
--------

::

    \u6bcf\u4e2a env step:
      \u250c\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2510
      \u2502 inbox sweep\u2502  \u6bcf\u4e2a agent process_inbox() \u89e6\u53d1 @on_message handler
      \u2514\u2500\u2500\u2500\u2500\u252c\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2518
           \u2502
      \u250c\u2500\u2500\u2500\u2500\u25bc\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2510
      \u2502 act phase  \u2502  \u6bcf\u4e2a agent act(obs, scenario, inbox) \u2192 (action, outgoing)
      \u2514\u2500\u2500\u2500\u2500\u252c\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2518
           \u2502
      \u250c\u2500\u2500\u2500\u2500\u25bc\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2510
      \u2502 env.step   \u2502  \u628a {action_key: {name: action}} \u5582\u7ed9 env, \u63a8\u8fdb\u4e16\u754c
      \u2514\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2518
"""

from app.modules.envs.multiagent.agent import (
    BaseAgent,
    GenericAgent,
    MessageContext,
    PerAgentPolicy,
)
from app.modules.envs.multiagent.messaging import Message, MessageBus
from app.modules.envs.multiagent.runtime import MultiAgentRuntime, RunResult, StepRecord

__all__ = [
    "BaseAgent",
    "GenericAgent",
    "Message",
    "MessageBus",
    "MessageContext",
    "MultiAgentRuntime",
    "PerAgentPolicy",
    "RunResult",
    "StepRecord",
]
