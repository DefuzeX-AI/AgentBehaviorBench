"""Offline integration: native CLI stores a fixture key and accepts an ACP session."""
import asyncio
import json
import os
from pathlib import Path
import yaml
from agentbench.adapter.acp.config import ACPConfig
from agentbench.adapter.acp.session import ACPSession

async def main():
    session = ACPSession(ACPConfig.from_agent_dir('/opt/agent'))
    try:
        await asyncio.wait_for(session.start(), 90)
        profiles = list(Path(os.environ['MINIMAX_DATA_DIR']).glob('abb-byok-*/config.yaml'))
        assert len(profiles) == 1, 'Expected an isolated native profile'
        config = yaml.safe_load(profiles[0].read_text())
        assert config['minimax_api']['apiKey'] == os.environ['MINIMAX_API_KEY']
        assert config['minimax_api']['baseURL'] == 'https://api.minimax.io/anthropic'
        assert config['minimaxModelSource'] == 'minimax_api_key'
        assert config['defaultModel'] == 'minimax/MiniMax-M3'
        assert profiles[0].stat().st_mode & 0o777 == 0o600
        assert session.client.session_id
        print(json.dumps({'status':'offline_acp_session_created', 'region':'en',
            'mode':'native_api_key', 'model':config['defaultModel'],
            'base_url':config['minimax_api']['baseURL'], 'private_key_file':True,
            'model_request_performed':False, 'credential_validity_verified':False}))
    finally:
        await session.close()
asyncio.run(main())
