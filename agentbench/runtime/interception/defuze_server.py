"""Resolve the Defuze model gateway without giving its credential to the Agent."""
from dataclasses import dataclass
from types import MappingProxyType

from .config import InterceptionConfigurationError
from .providers import ModelTargetConfig, ModelClientConfig
from .target_routing import _validate_target

FAMILIES = {'deepseek': 'deepseek-flash', 'minimax': 'minimax/minimax-m3'}
ENDPOINTS = ('/chat/completions', '/responses', '/messages',
             '/messages/count_tokens', '/responses/input_tokens')


@dataclass(frozen=True)
class DefuzeServerProvider:
    model: str | None = None

    def resolve(self, environ):
        family = environ.get('DEFUZE_MODEL_FAMILY', 'deepseek').strip()
        if family not in FAMILIES:
            raise InterceptionConfigurationError('DEFUZE_MODEL_FAMILY must be deepseek or minimax')
        model = (self.model or environ.get('ABB_MODEL') or environ.get('DEFUZE_MODEL') or FAMILIES[family]).strip()
        if not model or any(c.isspace() for c in model):
            raise InterceptionConfigurationError('Defuze model must be non-empty without whitespace')
        origin = (environ.get('KUMA_BASE_URL') or 'https://defuzex.ai/api/agentdefuze').strip().rstrip('/')
        client = ModelClientConfig(
            environ.get('DEFUZE_CLIENT_PROVIDER', 'deepseek').strip(),
            environ.get('DEFUZE_CLIENT_MODEL', 'deepseek-chat').strip(),
            environ.get('DEFUZE_CLIENT_BASE_URL', 'https://api.deepseek.com').strip().rstrip('/'))
        target = ModelTargetConfig('defuze_server', 'defuze_server', origin, model, 'KUMA_API_KEY')
        _validate_target(target)
        _validate_target(ModelTargetConfig(client.provider_id, 'compatible-json', client.base_url,
                                          client.model, 'KUMA_API_KEY'))
        if not client.provider_id or not client.model or any(c.isspace() for c in client.model):
            raise InterceptionConfigurationError('Defuze client provider and model must be configured')
        return ModelTargetConfig('defuze_server', 'defuze_server', f'{origin}/sdk/models/{family}',
                                 model, 'KUMA_API_KEY', endpoint_paths=MappingProxyType(
                                     {path: path for path in ENDPOINTS}), client=client)
