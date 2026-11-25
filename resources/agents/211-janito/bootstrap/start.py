"""Configure native provider/auth stores, then exec upstream Janito ACP."""
import os
from janito.auth_config import set_api_key
from janito.config_store import set_config_value
provider="custom"
set_config_value("provider",provider)
set_config_value("custom.model",os.environ["ABB_AGENT_MODEL"])
set_config_value("custom.endpoint",os.environ["ABB_AGENT_MODEL_BASE_URL"])
set_config_value("custom.models."+os.environ["ABB_AGENT_MODEL"]+".api-type","Completions")
if not set_api_key(provider,os.environ["ABB_AGENT_MODEL_API_KEY"]):
    raise RuntimeError("Native Janito credential store could not be initialized")
os.execvp("janito",["janito","--acp"])
