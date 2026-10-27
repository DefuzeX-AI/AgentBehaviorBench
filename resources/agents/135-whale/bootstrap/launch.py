"""Map runtime-selected DeepSeek settings to the unmodified native ACP server."""
import os


def environment(source):
    env = dict(source)
    if env.get("ABB_AGENT_MODEL_PROVIDER") != "deepseek":
        raise ValueError("Whale requires the DeepSeek provider")
    if env.get("ABB_AGENT_MODEL") != "deepseek-v4-pro":
        raise ValueError("Select --model deepseek-v4-pro: the pinned native model and current catalog must agree")
    if not env.get("ABB_AGENT_MODEL_API_KEY") or not env.get("ABB_AGENT_MODEL_BASE_URL"):
        raise ValueError("Whale requires runtime-selected model credentials and endpoint")
    env.update(DEEPSEEK_API_KEY=env["ABB_AGENT_MODEL_API_KEY"],
               DEEPSEEK_BASE_URL=env["ABB_AGENT_MODEL_BASE_URL"],
               WHALE_MODEL=env["ABB_AGENT_MODEL"], WHALE_API="auto",
               WHALE_HOME="/home/agent/.whale", WHALE_WORKSPACE="/home/agent/workspace")
    return env


if __name__ == "__main__":
    os.execve("/usr/local/bin/whale-acp", ["whale-acp"], environment(os.environ))
