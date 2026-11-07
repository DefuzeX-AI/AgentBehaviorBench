"""One-shot ABB matcher transport. Never calls an evaluation SDK."""
import json
import urllib.request
import urllib.error
from agentbench.sdk.plugin.local.relay import judge_model, json_object


def model_config(environ):
    configured = {k: v for k, v in environ.items() if not k.startswith('ABB_LOCAL_JUDGE_')}
    for suffix in ('BASE_URL', 'MODEL', 'API_KEY'):
        if environ.get('ABB_GT_' + suffix):
            configured['ABB_LOCAL_JUDGE_' + suffix] = environ['ABB_GT_' + suffix]
    return judge_model(configured)


def ask_once(model, *, system, payload, on_response=None):
    body = json.dumps({'model': model.model, 'temperature': 0, 'max_tokens': 4096,
                       'messages': [{'role': 'system', 'content': system},
                                    {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}]}).encode()
    request = urllib.request.Request(model.base_url + '/chat/completions', data=body,
                headers={'content-type': 'application/json', 'authorization': 'Bearer ' + model.api_key})
    try:
        with urllib.request.urlopen(request, timeout=model.timeout) as response:
            raw = json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f'ABB GT matcher HTTP {exc.code}; no automatic retry') from None
    except OSError:
        raise RuntimeError('ABB GT matcher connection failed; no automatic retry') from None
    if on_response is not None:
        on_response(raw)
    try:
        return json_object(raw['choices'][0]['message'].get('content') or '')
    except (KeyError, IndexError, TypeError):
        raise ValueError('ABB GT matcher returned no JSON decision') from None
