"""Run SAGA's official bootstrap workflow and preserve its review candidate."""
import asyncio
import json
import os
from pathlib import Path
import sys
import ssl

sys.path.insert(0, '/opt/agent/agent')

request = json.loads(Path(sys.argv[1]).read_text())
os.environ.update(
    OPENAI_API_BASE=os.environ['ABB_AGENT_MODEL_BASE_URL'],
    OPENAI_API_KEY=os.environ['ABB_AGENT_MODEL_API_KEY'],
    BASE_OUTPUT_DIR=request['workspace'],
    LARGE_MODEL=os.environ['ABB_AGENT_MODEL'],
    MEDIUM_MODEL=os.environ['ABB_AGENT_MODEL'],
    SMALL_MODEL=os.environ['ABB_AGENT_MODEL'],
    NARRATIVE_MODEL=os.environ['ABB_AGENT_MODEL'],
)
from main import run_bootstrap_mode
from core.service_context import managed_services

def language_model_with_runtime_transport():
    import config
    import httpx
    from core.http_client_service import HTTPClientService
    from core.llm_interface_refactored import create_llm_service
    from utils.common import load_strict_json
    from provider_metadata import normalize_completion

    class ProviderClient(httpx.AsyncClient):
        async def send(self, request, *args, **kwargs):
            response = await super().send(request, *args, **kwargs)
            if response.status_code != 200 or not request.url.path.endswith('/chat/completions'):
                return response
            await response.aread()
            payload, removed = normalize_completion(load_strict_json(response.text))
            if not removed:
                return response
            headers = [(key, value) for key, value in response.headers.multi_items()
                       if key.lower() not in ('content-length', 'content-encoding')]
            normalized = httpx.Response(response.status_code, json=payload, headers=headers,
                request=request, extensions=response.extensions)
            await response.aclose()
            print(json.dumps({'provider_metadata_normalized': removed}), file=sys.stderr)
            return normalized
    proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')
    certificate = os.environ.get('SSL_CERT_FILE') or os.environ.get('REQUESTS_CA_BUNDLE')
    if not certificate:
        raise RuntimeError('ABB CA certificate is required for the native HTTP transport')
    trust = ssl.create_default_context()
    trust.load_verify_locations(cafile=certificate)
    effective = config.get_settings()
    client = ProviderClient(proxy=proxy, verify=trust, trust_env=False,
        timeout=effective.HTTPX_TIMEOUT, follow_redirects=False)
    http = HTTPClientService(client=client, configuration=effective)
    return create_llm_service(http_client=http, configuration=effective)

async def run():
    async with managed_services(language_model_factory=language_model_with_runtime_transport) as services:
        return await run_bootstrap_mode(request['text'], review=True, services=services)

project, config = asyncio.run(run())
Path(sys.argv[2]).write_text(json.dumps({
    'native_mode': 'bootstrap', 'review_required': True,
    'project_directory': str(project), 'candidate': config.model_dump(mode='json'),
}, ensure_ascii=False))
