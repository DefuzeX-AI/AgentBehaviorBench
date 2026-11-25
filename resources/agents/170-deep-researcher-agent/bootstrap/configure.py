"""Change only model-client configuration in the pinned native MCP workflow."""
from pathlib import Path
import copy
import yaml

root = Path(__file__).resolve().parent
original = yaml.safe_load((root / "upstream-workflow.yml").read_text())
configured = copy.deepcopy(original)
for llm in configured["llms"].values():
    llm["_type"] = "openai"
    llm["model_name"] = "gpt-4o"
    llm["base_url"] = "https://api.openai.com/v1"
    llm["api_key"] = "${OPENAI_API_KEY}"
    # This NIM-only tokenizer option is not an OpenAI client parameter.
    llm.pop("chat_template_kwargs", None)
assert {k: v for k, v in original.items() if k != "llms"} == {k: v for k, v in configured.items() if k != "llms"}
(root / "workflow.yml").write_text(yaml.safe_dump(configured, sort_keys=False))
