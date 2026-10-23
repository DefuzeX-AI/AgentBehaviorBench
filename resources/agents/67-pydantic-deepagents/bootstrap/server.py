"""Native DeepAgentACP with the documented runtime-selected model factory."""
import asyncio
import os
from acp import run_agent
from apps.acp.server import AgentSessionContext, DeepAgentACP
from pydantic_deep import LocalWorkspace, create_deep_agent

def build_agent(ctx: AgentSessionContext):
    return create_deep_agent(model=ctx.model or os.environ["PYDANTIC_DEEP_MODEL"],
                             workspace=LocalWorkspace(ctx.cwd), context_discovery=True)

def main():
    model = os.environ["PYDANTIC_DEEP_MODEL"]
    server = DeepAgentACP(agent=build_agent, models=[{"value": model, "name": model}])
    asyncio.run(run_agent(server))

if __name__ == "__main__":
    main()
