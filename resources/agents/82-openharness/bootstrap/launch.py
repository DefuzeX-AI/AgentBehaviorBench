"""Native session configuration. Credentials remain in the child environment."""
import json,os,tempfile
from pathlib import Path

def prepare(environ):
    key=environ.get('ABB_AGENT_MODEL_API_KEY','').strip()
    model=environ.get('ABB_AGENT_MODEL','').strip()
    base=environ.get('ABB_AGENT_MODEL_BASE_URL','').strip().rstrip('/')
    if not key or not model or not base:
        raise ValueError('ABB_AGENT_MODEL_API_KEY, ABB_AGENT_MODEL and ABB_AGENT_MODEL_BASE_URL are required')
    # Native session honors baseUrl and normalizes provider/model. The concrete
    # wire model remains unprefixed. Support simple model names here only.
    if '/' in model:
        raise ValueError('This candidate supports only unprefixed model IDs')
    from urllib.parse import urlsplit
    url=urlsplit(base)
    if url.scheme!='https' and not (url.scheme=='http' and url.hostname in ('127.0.0.1','localhost')):
        raise ValueError('Model base URL must be HTTPS or a local test endpoint')
    if url.username or url.password or url.query or url.fragment:
        raise ValueError('Model base URL must not contain credentials, query or fragment')
    home=Path(tempfile.mkdtemp(prefix='abb-openharness-session-'))
    config=home/'.oh';config.mkdir(mode=0o700)
    # No secret in generated config or argv. Use upstream OpenAI-compatible
    # provider with explicit baseUrl; it remains the original native provider.
    (config/'config.yaml').write_text('provider: openai\nmodel: '+json.dumps('openai/'+model)+'\nbaseUrl: '+json.dumps(base)+'\n')
    child=dict(environ);child['HOME']=str(home);child['OPENAI_API_KEY']=key
    for name,suffix in [('XDG_CONFIG_HOME','.config'),('XDG_CACHE_HOME','.cache'),('XDG_DATA_HOME','.local/share'),('XDG_STATE_HOME','.local/state')]:
        target=home/suffix;target.mkdir(parents=True,exist_ok=True);child[name]=str(target)
    child['ABB_OPENHARNESS_CALL_EVIDENCE']=str(home/'model-tool-calls.jsonl')
    command=['node','--import',str(Path(__file__).with_name('request_evidence.mjs')),'/opt/agent/agent/dist/main.js','session','--model','openai/'+model]
    return command,child

if __name__=='__main__':
    import asyncio
    from session_acp import serve
    asyncio.run(serve())
