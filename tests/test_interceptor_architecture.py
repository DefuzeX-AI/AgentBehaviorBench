from __future__ import annotations

import sys
from pathlib import Path

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib  # type: ignore[no-redef]


REPO_ROOT = Path(__file__).resolve().parents[1]
INTERCEPTOR_CONTEXT = REPO_ROOT / "services" / "model-interceptor"
INTERCEPTOR_SRC = INTERCEPTOR_CONTEXT / "src"
sys.path.insert(0, str(INTERCEPTOR_SRC))

from defuzex_model_interceptor.auth import (  # noqa: E402
    AnthropicApiKeyAuthentication,
    BearerTokenAuthentication,
    InterceptorAuthenticationError,
)
from defuzex_model_interceptor.events import redact  # noqa: E402
from defuzex_model_interceptor.entrypoint import _configure_netfilter  # noqa: E402
from defuzex_model_interceptor.config import Route, ServiceConfig, Target  # noqa: E402
from defuzex_model_interceptor.protocols import (  # noqa: E402
    OPENAI_CHAT_PROTOCOL,
)
from defuzex_model_interceptor.targets import OPENROUTER_TARGET  # noqa: E402

from agentbench.runtime.docker.interceptor_image import (  # noqa: E402
    LocalInterceptorImageProvider,
    default_interceptor_image_provider,
)
from agentbench.runtime.docker.interceptor_policy import InterceptorPolicy  # noqa: E402
from agentbench.runtime.interception import StaticInterceptorImageProvider  # noqa: E402


class RecordingImageBuilder:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def build(self, **kwargs: object) -> str:
        self.calls.append(kwargs)
        return "defuzex-agentbench/model-interceptor:test"


def test_interceptor_has_an_independent_mitmproxy_service() -> None:
    metadata = tomllib.loads(
        INTERCEPTOR_CONTEXT.joinpath("pyproject.toml").read_text(encoding="utf-8")
    )

    assert metadata["project"]["name"] == "defuzex-model-interceptor"
    assert any(item.startswith("mitmproxy") for item in metadata["project"]["dependencies"])
    assert "defuzex.model_interceptor.protocols" in metadata["project"]["entry-points"]
    assert "defuzex.model_interceptor.auth" in metadata["project"]["entry-points"]
    assert "defuzex.model_interceptor.targets" in metadata["project"]["entry-points"]


def test_interceptor_image_build_is_scoped_to_service_context() -> None:
    builder = RecordingImageBuilder()
    provider = LocalInterceptorImageProvider(builder, INTERCEPTOR_CONTEXT)  # type: ignore[arg-type]

    assert provider.resolve_image() == "defuzex-agentbench/model-interceptor:test"
    assert builder.calls == [
        {
            "context": INTERCEPTOR_CONTEXT,
            "dockerfile": INTERCEPTOR_CONTEXT / "Dockerfile",
            "repository": "model-interceptor",
        }
    ]


def test_deployment_can_supply_an_interceptor_image() -> None:
    builder = RecordingImageBuilder()
    provider = default_interceptor_image_provider(
        builder,  # type: ignore[arg-type]
        {"DEFUZEX_MODEL_INTERCEPTOR_IMAGE": "registry.example/interceptor:1.2.3"},
    )

    assert isinstance(provider, StaticInterceptorImageProvider)
    assert provider.resolve_image() == "registry.example/interceptor:1.2.3"
    assert builder.calls == []


def test_interceptor_policy_is_separate_and_minimally_privileged() -> None:
    arguments = InterceptorPolicy().run_arguments()

    assert "--cap-drop=ALL" in arguments
    assert "--cap-add=NET_ADMIN" in arguments
    assert "--cap-add=NET_RAW" in arguments
    assert "--read-only" in arguments


def test_bearer_auth_replaces_only_the_temporary_token() -> None:
    headers = {"authorization": "Bearer temporary"}

    BearerTokenAuthentication().authorize(
        headers,
        temporary_token="temporary",
        upstream_secret="provider-secret",
    )

    assert headers["authorization"] == "Bearer provider-secret"

    with pytest.raises(InterceptorAuthenticationError):
        BearerTokenAuthentication().authorize(
            {"authorization": "Bearer wrong"},
            temporary_token="temporary",
            upstream_secret="provider-secret",
        )


def test_anthropic_auth_converts_temporary_api_key_to_openrouter_bearer() -> None:
    headers = {"x-api-key": "temporary", "anthropic-version": "2023-06-01"}

    AnthropicApiKeyAuthentication().authorize(
        headers,
        temporary_token="temporary",
        upstream_secret="openrouter-secret",
    )

    assert "x-api-key" not in headers
    assert headers["authorization"] == "Bearer openrouter-secret"
    assert headers["anthropic-version"] == "2023-06-01"


def test_openai_protocol_decodes_json_and_sse() -> None:
    request = OPENAI_CHAT_PROTOCOL.decode_request(
        b'{"model":"example","messages":[{"role":"user","content":"hello"}]}',
        "application/json",
    )
    response = OPENAI_CHAT_PROTOCOL.decode_response(
        b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\ndata: [DONE]\n\n',
        "text/event-stream",
    )

    assert request["model"] == "example"  # type: ignore[index]
    assert response == {"events": [{"choices": [{"delta": {"content": "hi"}}]}]}


@pytest.mark.parametrize(
    ("protocol", "source_path", "target_path"),
    [
        ("openai-chat", "/v1/chat/completions", "/api/v1/chat/completions"),
        ("openai-responses", "/v1/responses", "/api/v1/responses"),
        ("anthropic-messages", "/v1/messages", "/api/v1/messages"),
    ],
)
def test_openrouter_target_rewrites_endpoint_model_and_optional_headers(
    protocol: str,
    source_path: str,
    target_path: str,
) -> None:
    request = type(
        "Request",
        (),
        {
            "scheme": "https",
            "host": "api.openai.com",
            "port": 443,
            "path": source_path,
            "content": b'{"model":"gpt-source","messages":[]}',
            "headers": {"authorization": "Bearer upstream"},
        },
    )()
    route = Route(
        route_id="chat",
        host_patterns=("api.openai.com",),
        ports=(443,),
        methods=("POST",),
        path_patterns=(source_path,),
        protocol_plugin=protocol,
        credential_id="primary",
    )
    target = Target(
        provider_id="openrouter",
        target_plugin="openrouter",
        base_url="https://openrouter.ai/api/v1",
        model="openai/gpt-4.1-mini",
        headers={"X-OpenRouter-Title": "AgentBench"},
    )

    prepared = OPENROUTER_TARGET.prepare_request(
        request,
        route=route,
        target=target,
    )

    assert request.host == "openrouter.ai"
    assert request.path == target_path
    assert request.headers["host"] == "openrouter.ai"
    assert request.headers["X-OpenRouter-Title"] == "AgentBench"
    assert prepared.source_model == "gpt-source"
    assert prepared.target_model == "openai/gpt-4.1-mini"
    assert b'"model":"openai/gpt-4.1-mini"' in request.content


def test_trace_redaction_covers_headers_fields_and_literal_secrets() -> None:
    payload = {
        "authorization": "Bearer provider-secret",
        "messages": [{"content": "do not print temporary"}],
        "nested_api_key": "provider-secret",
    }

    assert redact(payload, ("temporary", "provider-secret")) == {
        "authorization": "[REDACTED]",
        "messages": [{"content": "do not print [REDACTED]"}],
        "nested_api_key": "[REDACTED]",
    }


def test_netfilter_covers_all_non_root_tcp_and_blocks_untranslated_egress(monkeypatch) -> None:
    commands = []
    monkeypatch.setattr("defuzex_model_interceptor.entrypoint.subprocess.run", lambda command, **kwargs: commands.append(command))
    _configure_netfilter()
    redirects = [c for c in commands if "REDIRECT" in c]
    assert len(redirects) == 1 and "--dport" not in redirects[0]
    assert "--uid-owner" in redirects[0] and "!" in redirects[0]
    assert any(c[0] == "ip6tables" and "REJECT" in c for c in commands)
    assert any(c[0] == "iptables" and "REJECT" in c for c in commands)
