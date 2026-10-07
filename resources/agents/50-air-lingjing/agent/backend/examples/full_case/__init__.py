"""\u591a\u65e0\u4eba\u673a\u914d\u9001\u5bfc\u822a \u2014 \u5b8c\u6574 Gym-style \u7528\u6237\u6848\u4f8b.

case \u5185\u5269\u4e0b\u7684\u6587\u4ef6 (\u5176\u4f59\u5171\u7528\u62bd\u8c61\u5df2\u63d0\u5230\u4e3b\u6846\u67b6, \u89c1 ``app.modules.envs.*``):

* :mod:`scenario`   \u2014 \u6784\u5efa\u573a\u666f (``ScenarioDefinition`` \u7c7b\u5f62\u6001)
* :mod:`policy`     \u2014 \u96c6\u4e2d\u5f0f / \u5206\u5e03\u5f0f\u4e24\u79cd\u591a\u6a21\u6001 LLM \u7b56\u7565
* :mod:`engines`    \u2014 \u8fdb\u7a0b\u5185 Mock \u5f15\u64ce + \u771f\u5b9e WebSocket \u6865\u7684\u8584\u5c01\u88c5
* :mod:`fake_engine`\u2014 \u6d4b\u8bd5\u7528 fake LJ-ENGINE WS \u5ba2\u6237\u7aef (--realtime \u624d\u7528\u5f97\u5230)
* :mod:`run_case`   \u2014 \u7aef\u5230\u7aef\u5165\u53e3, gym-style API

\u4e3b\u6846\u67b6\u5bf9\u5e94:

* env / EpisodeHandle / make_env  \u2192
  :mod:`app.modules.envs.envs.multi_drone_delivery_env`
* evaluator ``delivery_v1``       \u2192
  :mod:`app.modules.envs.evaluators.user.delivery_v1`
* Message / MessageBus / Agent / Runtime \u2192
  :mod:`app.modules.envs.multiagent`
* LLMClient / QwenVLClient / parse_action_json \u2192
  :mod:`app.modules.ai.clients`
"""
