"""Launch the shipped SGR File Agent preset through the upstream ACP server."""
import os
from pathlib import Path
import shutil
import sys
import yaml

root = Path("/opt/agent/agent/examples/sgr_file_agent")
deployment = Path.home()/"sgr_file_agent"
shutil.copytree(root, deployment, dirs_exist_ok=True)
config = yaml.safe_load((deployment/"config.yaml.example").read_text())
config["llm"].update(api_key=os.environ["ABB_AGENT_MODEL_API_KEY"],
    base_url=os.environ["ABB_AGENT_MODEL_BASE_URL"], model=os.environ["ABB_AGENT_MODEL"])
if os.environ.get("ABB_AGENT_MODEL_PROVIDER") == "deepseek":
    # The native loop requires tool_choice=required, supported in non-thinking mode.
    config["llm"].setdefault("extra_body", {})["thinking"] = {"type": "disabled"}
# SGRFileAgent already registers these classes. The example's separately loaded
# aliases otherwise create distinct classes with duplicate API tool names.
native_file_tools = {
    "get_system_paths_tool", "list_directory_tool", "read_file_tool",
    "search_in_files_tool", "find_files_fast_tool",
}
agent_config = config["agents"]["sgr_file_agent"]
agent_config["tools"] = [name for name in agent_config["tools"] if name not in native_file_tools]
config["agents"]["sgr_file_agent"]["working_directory"] = "/workspace"
path = deployment/"config.yaml"
path.write_text(yaml.safe_dump(config))
path.chmod(0o600)
os.chdir(deployment)
os.execv(sys.executable, [sys.executable, "-m", "sgr_agent_core.acp", "--config", str(path)])
