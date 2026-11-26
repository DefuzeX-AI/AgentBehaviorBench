"""Select the deployment model and execute the upstream ACP server."""
import os

model = os.environ['ABB_AGENT_MODEL']
os.environ.update(
    CLAUDE_CODE_USE_OPENAI='1',
    OPENAI_API_KEY=os.environ['ABB_AGENT_MODEL_API_KEY'],
    OPENAI_BASE_URL=os.environ['ABB_AGENT_MODEL_BASE_URL'],
    ANTHROPIC_MODEL=model,
    OPENAI_MODEL_OPUS=model,
    OPENAI_MODEL_SONNET=model,
    OPENAI_MODEL_HAIKU=model,
    TAU_ACP_DEBUG='1',
)
os.execvp('node', ['node', '/opt/agent/agent/dist/cli.mjs', 'acp'])
