"""claude_agent_sdk 订阅**主路径**的超时回归（v0.5.20）。

v0.5.19 把 `llm_timeout` 铺到了所有走 LangChain 客户端的 provider，唯独
`claude_agent_sdk` 的主路径罩不到：它不经 LangChain，直接驱动 Agent SDK 的异步
生成器（背后是 `claude` 子进程）。子进程卡住 ⇒ `async for` 永远悬着 ⇒ 进程活着、
零输出、永不返回。README 当时把这条写成「已知缺口」，本文件把它关掉。

⚠️ 刻意**不**用 `requires_sdk` 跳过。`claude-agent-sdk` 是可选 extra，干净安装里
装不上（本仓现有 13 条 skip 就是它）；把超时护栏挂在可选依赖上，等于默认配置下
一条都不跑——而超时正是默认配置下最该被保护的东西。所以这里只用替身顶住模块里
两个 SDK 名字（`_sdk` / `ClaudeAgentOptions`），其余全走生产代码。

全程不碰真实 provider：没有网络、没有子进程、没有订阅额度。
"""

import asyncio
import threading
import time
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from tradingagents.llm_clients import claude_agent_sdk_client as mod
from tradingagents.llm_clients.claude_agent_sdk_client import (
    ClaudeAgentSDKClient,
    _SDKTimeout,
)

# 用例里给的超时都远小于"挂起协程"的睡眠时长，这样断言 elapsed 才能区分
# 「真的中断了」和「等它自己睡醒」。
_TINY_TIMEOUT = 0.05      # 秒，换算后仍 < 挂起时长
_HANG_SECONDS = 30        # 挂起协程的睡眠时长：不超时就必然跑满这个数
_ELAPSED_CEILING = 5      # 秒，判定"确实提前中断"的上界


class _Plan(BaseModel):
    decision: str
    confidence: int


class _FakeSDKModule:
    """顶掉 `mod._sdk`：`_query` 只用到这四个类型做 isinstance 判定。"""

    class RateLimitEvent:
        pass

    class AssistantMessage:
        pass

    class TextBlock:
        pass

    class ResultMessage:
        pass


@pytest.fixture
def sdk_stub(monkeypatch):
    """让本模块在**没装** claude-agent-sdk 时也能走完 get_llm → _invoke_* 整条链。

    只顶两个名字：`_sdk`（存在性哨兵 + isinstance 用的类型）和 `ClaudeAgentOptions`
    （选项构造器）。真正发起调用的 `_query` / `_sdk.query` 由每条用例自己换掉。
    """
    monkeypatch.setattr(mod, "_sdk", _FakeSDKModule())
    monkeypatch.setattr(mod, "ClaudeAgentOptions", lambda **kw: SimpleNamespace(**kw))
    monkeypatch.setattr(mod, "create_sdk_mcp_server", lambda *a, **k: object())

    def _fake_tool_decorator(name, description, schema):
        def decorate(fn):
            fn.name = name
            return fn
        return decorate

    monkeypatch.setattr(mod, "_sdk_tool", _fake_tool_decorator)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-token")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


class _FakeLangChainTool:
    name = "get_thing"
    description = "gets a thing"
    args_schema = None

    def invoke(self, args):
        return "thing-data"


class _StubStructured:
    def __init__(self, schema):
        self._schema = schema

    def invoke(self, prompt, *a, **k):
        return self._schema(decision="fallback-buy", confidence=1)


class _StubBoundTools:
    def invoke(self, prompt, *a, **k):
        from langchain_core.messages import AIMessage
        return AIMessage(content="served by fallback tools")


class _StubLLM:
    def invoke(self, prompt, *a, **k):
        from langchain_core.messages import AIMessage
        return AIMessage(content="served by fallback")

    def with_structured_output(self, schema, **k):
        return _StubStructured(schema)

    def bind_tools(self, tools, **k):
        return _StubBoundTools()


def _install_stub_fallback(monkeypatch):
    monkeypatch.setattr(
        "tradingagents.llm_clients.factory.create_llm_client",
        lambda **kw: type("C", (), {"get_llm": lambda self: _StubLLM()})(),
    )


_FALLBACK_SPEC = {"provider": "deepseek", "model": "deepseek-v4-pro", "base_url": None}


def _hanging_client(monkeypatch, timeout=_TINY_TIMEOUT, fallback_spec=None):
    """客户端的 `_query` 永远不返回 —— 模拟 SDK/CLI 卡住。"""
    client = ClaudeAgentSDKClient(
        "claude-opus-4-8", timeout=timeout, fallback_spec=fallback_spec
    )

    async def hang(prompt, options, prefer_result=False):
        await asyncio.sleep(_HANG_SECONDS)
        return "never", None

    monkeypatch.setattr(client, "_query", hang)
    return client


# --------------------------------------------------------------------------- #
# 预算换算：llm_timeout 是「一次模型调用」的预算
# --------------------------------------------------------------------------- #

@pytest.mark.unit
class TestTimeoutBudget:
    def test_no_timeout_configured_keeps_old_behaviour(self):
        # 没配 llm_timeout ⇒ 不设超时，行为与本改动前完全一致。
        client = ClaudeAgentSDKClient("claude-opus-4-8")
        assert client.timeout is None
        assert client._timeout_for(1) is None
        assert client._timeout_for(mod._TOOL_MAX_TURNS) is None

    def test_single_turn_budget_equals_llm_timeout(self):
        client = ClaudeAgentSDKClient("claude-opus-4-8", timeout=150)
        assert client._timeout_for(1) == 150

    def test_tool_loop_budget_scales_with_allowed_turns(self):
        # Agent SDK 把整个 ReAct 循环跑在**一次** invoke 里，最多 _TOOL_MAX_TURNS
        # 次模型调用；别的 provider 那里每轮都是一次新 HTTP 请求、各拿一份完整预算。
        # 整段固定 150 秒 ⇒ 分析师几乎每次都超时降级到按 token 计费的 provider。
        client = ClaudeAgentSDKClient("claude-opus-4-8", timeout=150)
        assert client._timeout_for(mod._TOOL_MAX_TURNS) == 150 * mod._TOOL_MAX_TURNS
        assert client._timeout_for(mod._TOOL_MAX_TURNS) > client._timeout_for(1)

    @pytest.mark.parametrize("value", [0, -1, "", "abc", None, True, False])
    def test_unusable_timeout_values_disable_the_guard(self, value):
        # 0 / 负数 / 解析不了的值都必须落到"不设超时"，而**不是**"立刻超时"：
        # wait_for(coro, -1) 会当场抛，等于一个手滑的配置让这个 provider 一次都跑不通。
        # True/False 同理：bool 是 int 的子类，float(True)==1.0 会把一个开关误配
        # 变成"1 秒超时"（同样是这个 provider 一次都跑不通），必须当作没配。
        assert ClaudeAgentSDKClient("claude-opus-4-8", timeout=value).timeout is None

    def test_string_timeout_is_accepted(self):
        # 环境变量/JSON 配置里来的常常是字符串。
        assert ClaudeAgentSDKClient("claude-opus-4-8", timeout="150").timeout == 150.0


# --------------------------------------------------------------------------- #
# 真正的超时执行：挂起的调用必须中断，而不是等它睡醒
# --------------------------------------------------------------------------- #

@pytest.mark.unit
class TestTimeoutEnforcement:
    def test_hanging_invoke_raises_sdk_timeout(self, monkeypatch, sdk_stub):
        client = _hanging_client(monkeypatch)
        start = time.monotonic()
        with pytest.raises(_SDKTimeout):
            client._invoke_raw("analyze 600519")
        elapsed = time.monotonic() - start
        assert elapsed < _ELAPSED_CEILING, f"没有真的中断，等了 {elapsed:.1f}s"

    def test_hanging_structured_call_raises_sdk_timeout(self, monkeypatch, sdk_stub):
        client = _hanging_client(monkeypatch)
        with pytest.raises(_SDKTimeout):
            client._invoke_structured(_Plan, "decide")

    def test_hanging_tool_loop_raises_sdk_timeout(self, monkeypatch, sdk_stub):
        client = _hanging_client(monkeypatch)
        with pytest.raises(_SDKTimeout):
            client._invoke_with_tools([_FakeLangChainTool()], "analyze")

    def test_timeout_message_names_the_knob(self, monkeypatch, sdk_stub):
        # 报错要能自救：说清楚是哪个配置项、当前值多少。
        client = _hanging_client(monkeypatch)
        with pytest.raises(_SDKTimeout, match="llm_timeout"):
            client._invoke_raw("analyze")

    def test_timeout_when_called_from_a_running_event_loop(self, monkeypatch, sdk_stub):
        # 调用方已有事件循环时 `_run_async` 走工作线程分支。超时必须一样生效，
        # 否则异步宿主（Web UI / 任何 async 驱动）下这个护栏等于不存在。
        client = _hanging_client(monkeypatch)

        async def main():
            return client._invoke_raw("analyze")   # 同步调用，内部起工作线程

        start = time.monotonic()
        with pytest.raises(_SDKTimeout):
            asyncio.run(main())
        elapsed = time.monotonic() - start
        assert elapsed < _ELAPSED_CEILING, f"线程分支没中断，等了 {elapsed:.1f}s"

    def test_run_async_gives_up_on_a_thread_that_ignores_cancellation(self):
        # 第二层兜底：协程里的 wait_for 靠取消生效，SDK 若阻塞在不可取消的调用里
        # （这里用阻塞式 time.sleep 模拟），没有有界 join 就还是永久挂住调用方。
        async def uncancellable():
            time.sleep(2)
            return "too late"

        async def main():
            return mod._run_async(uncancellable(), join_timeout=0.05)

        start = time.monotonic()
        with pytest.raises(_SDKTimeout):
            asyncio.run(main())
        assert time.monotonic() - start < _ELAPSED_CEILING

    def test_run_async_gives_up_on_the_no_running_loop_path_too(self):
        """没有 running loop 的**主路径**同样要有有界 join。

        trading_graph 同步驱动 LangGraph，绝大多数调用走的就是这条路。此前这条
        分支直接 `asyncio.run(coro)`：协程一旦阻塞住自己的事件循环（SDK 里的同步
        调用、或取消后 aclose 挂死），里面的 `wait_for` 根本没机会跑，调用方被
        永久挂住 —— 有界 join 只在"调用方已有事件循环"那条分支上存在。
        """
        with pytest.raises(RuntimeError):      # 钉住前提：此处确实没有运行中的循环
            asyncio.get_running_loop()

        release = threading.Event()

        async def blocks_its_own_loop():
            # 阻塞式等待：占住事件循环，取消信号送不进来
            release.wait(_HANG_SECONDS)
            return "too late"

        start = time.monotonic()
        try:
            with pytest.raises(_SDKTimeout):
                mod._run_async(blocks_its_own_loop(), join_timeout=_TINY_TIMEOUT)
            elapsed = time.monotonic() - start
            assert elapsed < _ELAPSED_CEILING, f"主路径没中断，等了 {elapsed:.1f}s"
        finally:
            # 放掉那个 daemon 工作线程，别让它挂到测试会话结束
            release.set()

    def test_blocking_sdk_times_out_on_the_no_running_loop_main_path(
        self, monkeypatch, sdk_stub
    ):
        """端到端版：同步调用方 + 阻塞事件循环且不理取消的 SDK ⇒ 仍要抛超时。"""
        with pytest.raises(RuntimeError):
            asyncio.get_running_loop()

        # 真实值 30s 是给 SDK 收尾用的；这条用例要断言墙钟，压到可测量的量级。
        monkeypatch.setattr(mod, "_CANCEL_GRACE", _TINY_TIMEOUT)
        release = threading.Event()
        client = ClaudeAgentSDKClient("claude-opus-4-8", timeout=_TINY_TIMEOUT)

        async def blocking_query(prompt, options, prefer_result=False):
            release.wait(_HANG_SECONDS)
            return "never", None

        monkeypatch.setattr(client, "_query", blocking_query)

        start = time.monotonic()
        try:
            with pytest.raises(_SDKTimeout):
                client._invoke_raw("analyze 600519")
            elapsed = time.monotonic() - start
            assert elapsed < _ELAPSED_CEILING, f"主路径没中断，等了 {elapsed:.1f}s"
        finally:
            release.set()


# --------------------------------------------------------------------------- #
# 超时要走既有的 fallback / 报错通路
# --------------------------------------------------------------------------- #

@pytest.mark.unit
class TestTimeoutFallback:
    def test_invoke_timeout_falls_back_to_configured_provider(self, monkeypatch, sdk_stub):
        client = _hanging_client(monkeypatch, fallback_spec=_FALLBACK_SPEC)
        _install_stub_fallback(monkeypatch)
        assert client.get_llm().invoke("analyze").content == "served by fallback"

    def test_structured_timeout_falls_back_and_still_yields_pydantic(
        self, monkeypatch, sdk_stub
    ):
        client = _hanging_client(monkeypatch, fallback_spec=_FALLBACK_SPEC)
        _install_stub_fallback(monkeypatch)
        plan = client.get_llm().with_structured_output(_Plan).invoke("decide")
        assert isinstance(plan, _Plan) and plan.decision == "fallback-buy"

    def test_tool_loop_timeout_falls_back(self, monkeypatch, sdk_stub):
        client = _hanging_client(monkeypatch, fallback_spec=_FALLBACK_SPEC)
        _install_stub_fallback(monkeypatch)
        result = client.get_llm().bind_tools([_FakeLangChainTool()]).invoke("analyze")
        assert result.content == "served by fallback tools"

    def test_timeout_without_fallback_spec_reraises(self, monkeypatch, sdk_stub):
        # 没配降级目标就必须往外抛，不能吞掉变成空报告。
        client = _hanging_client(monkeypatch, fallback_spec=None)
        with pytest.raises(_SDKTimeout):
            client.get_llm().invoke("analyze")

    def test_timeout_is_in_the_fallback_error_tuple(self):
        # 阳性断言配阴性对照：超时可降级，认证失败**不可**（降级 = 悄悄开始计费）。
        assert _SDKTimeout in mod._FALLBACK_ERRORS
        assert mod._AuthError not in mod._FALLBACK_ERRORS


# --------------------------------------------------------------------------- #
# 正常调用不受影响 + 资源不泄漏
# --------------------------------------------------------------------------- #

@pytest.mark.unit
class TestNoRegressionAndCleanup:
    def test_fast_call_under_budget_returns_normally(self, monkeypatch, sdk_stub):
        client = ClaudeAgentSDKClient("claude-opus-4-8", timeout=30)

        async def quick(prompt, options, prefer_result=False):
            return "served by subscription", None

        monkeypatch.setattr(client, "_query", quick)
        assert client._invoke_raw("hi").content == "served by subscription"

    def test_fast_call_with_no_timeout_configured_returns_normally(
        self, monkeypatch, sdk_stub
    ):
        # budget=None 这条分支（老行为）也要有人走，否则改坏了没人发现。
        client = ClaudeAgentSDKClient("claude-opus-4-8")

        async def quick(prompt, options, prefer_result=False):
            return "served by subscription", None

        monkeypatch.setattr(client, "_query", quick)
        assert client._invoke_raw("hi").content == "served by subscription"

    def test_timeout_closes_the_sdk_async_generator(self, monkeypatch, sdk_stub):
        # 超时取消后生成器（连同它拉起的 `claude` 子进程）必须收尾。
        # ⚠️ 这条**证明不了** `_query` 里那个显式 aclose：`asyncio.run` 退出时会
        # 自动 shutdown_asyncgens 把 finally 补跑一遍，把 aclose 删掉它照样绿
        # （已实测）。它只钉"取消之后生成器没被留在半路"这个结果。
        # 责任归属由下一条用例分开。
        closed = []

        async def hanging_query(prompt=None, options=None):
            try:
                await asyncio.sleep(_HANG_SECONDS)
                yield None
            finally:
                closed.append(True)

        fake_sdk = _FakeSDKModule()
        fake_sdk.query = hanging_query
        monkeypatch.setattr(mod, "_sdk", fake_sdk)

        client = ClaudeAgentSDKClient("claude-opus-4-8", timeout=_TINY_TIMEOUT)
        with pytest.raises(_SDKTimeout):
            client._invoke_raw("analyze")
        assert closed == [True], "超时后 SDK 异步生成器没有被收尾（子进程随之泄漏）"

    def test_normal_completion_also_closes_the_generator(self, monkeypatch, sdk_stub):
        # 阴性对照：正常返回路径同样要收尾，且不能把正常结果弄丢。
        closed = []

        async def quick_query(prompt=None, options=None):
            try:
                yield _text_message("served by subscription")
            finally:
                closed.append(True)

        fake_sdk = _FakeSDKModule()
        fake_sdk.query = quick_query
        monkeypatch.setattr(mod, "_sdk", fake_sdk)

        client = ClaudeAgentSDKClient("claude-opus-4-8", timeout=30)
        assert client._invoke_raw("hi").content == "served by subscription"
        assert closed == [True]


    def test_query_closes_the_generator_without_relying_on_loop_shutdown(
        self, monkeypatch, sdk_stub
    ):
        """`_query` 自己收尾，不把责任推给事件循环的 shutdown_asyncgens。

        手工开一个循环、跑完**不**调 shutdown_asyncgens，才能把"`_query` 收的"
        和"循环兜底收的"分开。钉的是认证失败那条 `break` 路径：生成器停在 yield
        上仍然活着，连同它拉起的 `claude` 子进程——在放弃了工作线程的场景里，
        那个兜底根本不会到来。
        """
        closed = []

        async def auth_failure_query(prompt=None, options=None):
            try:
                yield _auth_failure_message()
                yield _text_message("never reached")   # break 之后不应再被拉取
            finally:
                closed.append(True)

        fake_sdk = _FakeSDKModule()
        fake_sdk.query = auth_failure_query
        monkeypatch.setattr(mod, "_sdk", fake_sdk)

        client = ClaudeAgentSDKClient("claude-opus-4-8")
        loop = asyncio.new_event_loop()
        try:
            with pytest.raises(mod._AuthError):
                loop.run_until_complete(client._query("x", object()))
            assert closed == [True], (
                "生成器没在 _query 里收尾，只能等事件循环 shutdown_asyncgens 兜底"
            )
        finally:
            loop.close()


def _auth_failure_message():
    """一条合成的认证失败消息（`_looks_like_auth_failure` 只认合成消息）。"""
    message = _FakeSDKModule.AssistantMessage()
    message.model = "<synthetic>"
    block = _FakeSDKModule.TextBlock()
    block.text = "authentication_failed: please run /login"
    message.content = [block]
    return message


def _text_message(text: str):
    """一条最小的 AssistantMessage（替身类型，走 `_query` 的 isinstance 分支）。"""
    message = _FakeSDKModule.AssistantMessage()
    block = _FakeSDKModule.TextBlock()
    block.text = text
    message.content = [block]
    return message
