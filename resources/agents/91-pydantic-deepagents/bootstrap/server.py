"""Configure an ABB ACP transport around the unchanged native Agent factory."""
import asyncio
import os
from acp import run_agent
from pydantic_ai.workspaces import LocalWorkspaceBackend, Workspace
from pydantic_ai_backends import ConfinedWorkspace
from pydantic_deep import DeepAgentDeps, LocalWorkspace, create_deep_agent
from bridge import AgentSessionContext, DeepAgentBridge


def build_agent(ctx: AgentSessionContext):
    return create_deep_agent(model=ctx.model or os.environ['PYDANTIC_DEEP_MODEL'],
                            workspace=LocalWorkspace(ctx.cwd), context_discovery=True)


def workspace(cwd):
    # Same native confined per-run workspace as upstream DeepAgentACP._workspace_for.
    return ConfinedWorkspace(Workspace(LocalWorkspaceBackend(cwd, env=dict(os.environ))))


def main():
    server = DeepAgentBridge(agent_factory=build_agent, deps_factory=DeepAgentDeps,
        workspace_factory=workspace, model=os.environ['PYDANTIC_DEEP_MODEL'])
    asyncio.run(run_agent(server))


if __name__ == '__main__':
    main()
