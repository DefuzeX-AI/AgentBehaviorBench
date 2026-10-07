"""\u7a7a\u5730\u534f\u540c\u706d\u706b \u2014 \u5b8c\u6574 Gym-style \u7528\u6237\u6848\u4f8b.

\u4efb\u52a1\u60c5\u8282
========

* \u57ce\u5e02\u90ca\u533a\u8d77\u706b, \u4e00\u67b6 UAV (``drone1``) \u5728\u9ad8\u7a7a\u5de1\u903b\u641c\u5bfb\u706b\u70b9;
* \u4e24\u53f0 UGV (``ugv1`` / ``ugv2``) \u5728\u5730\u9762\u5f85\u547d, \u63a5 UAV \u8b66\u62a5\u540e\u534f\u540c\u706d\u706b;
* \u706b\u70b9\u771f\u5b9e\u4f4d\u7f6e\u4ec5 env \u5185\u90e8\u5df2\u77e5, UAV \u5fc5\u987b\u7528\u89c6\u91ce\u63a2\u6d4b.

case \u6587\u4ef6 (\u6240\u6709\u5171\u7528\u62bd\u8c61\u5df2\u5728 ``app.modules.envs.*``):

* :mod:`scenario`   \u2014 UAV + 2 UGV \u7f16\u961f + \u9690\u85cf\u706b\u70b9\u7684\u573a\u666f\u5b9a\u4e49
* :mod:`policy`     \u2014 ``UAVSearchPolicy`` (\u5de1\u903b + \u62a5\u8b66) +
                       ``UGVExtinguishPolicy`` (\u54cd\u5e94 + \u706d\u706b)
* :mod:`engines`    \u2014 ``MockFireRescueBridge`` (\u8fdb\u7a0b\u5185\u706b\u707e\u4e16\u754c) +
                       ``UEFireRescueBridge`` (\u771f\u5b9e UE \u901a\u8fc7 WS)
* :mod:`fake_engine`\u2014 \u771f\u5b9e WS \u6d4b\u8bd5\u7528 fake LJ-ENGINE \u5ba2\u6237\u7aef
* :mod:`run_case`   \u2014 \u7aef\u5230\u7aef\u5165\u53e3, gym-style API

\u4e3b\u6846\u67b6\u5bf9\u5e94:

* env / EpisodeHandle / make_env  \u2192
  :mod:`app.modules.envs.envs.fire_rescue_env`
* evaluator ``fire_rescue_v1``    \u2192
  :mod:`app.modules.envs.evaluators.user.fire_rescue_v1`
* Message / MessageBus / Agent / Runtime \u2192
  :mod:`app.modules.envs.multiagent`
* LLMClient / QwenVLClient / parse_action_json \u2192
  :mod:`app.modules.ai.clients`
"""
