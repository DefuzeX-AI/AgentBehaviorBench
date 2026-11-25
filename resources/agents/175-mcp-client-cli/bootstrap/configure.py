"""Provision the native example prompt and built-in-tool configuration."""
from pathlib import Path
import json

root = Path(__file__).resolve().parents[1]
example = json.loads((root / "agent/mcp-server-config-example.json").read_text())
config = {
    "systemPrompt": example["systemPrompt"],
    "llm": {k: v for k, v in example["llm"].items() if k != "api_key"},
    # External MCP servers are user-configured examples, not bundled tools.
    # Native load_tools still appends save_memory when this mapping is empty.
    "mcpServers": {},
}
config["llm"]["base_url"] = "https://api.openai.com/v1"
(root / "mcp-server-config.json").write_text(json.dumps(config, indent=2) + "\n")
