"""Deploy the native personal edition with only its OpenAI endpoint configured."""
import os

from core.byok_endpoints import get_byok_manager

manager = get_byok_manager()
manager.providers["openai"].base_url = os.environ["ABB_AGENT_MODEL_BASE_URL"]
manager.providers["openai"].model = os.environ["ABB_AGENT_MODEL"]
manager._save_configuration()

import uvicorn

uvicorn.run("main_api_app:app", host="127.0.0.1", port=8000)
