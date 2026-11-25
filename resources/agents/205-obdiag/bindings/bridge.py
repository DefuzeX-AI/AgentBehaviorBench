"""Use the native diagnostic toolset and interactive-mode approval configuration."""
import asyncio
import os
from pathlib import Path
import shutil
import sys
sys.path.insert(0,"/opt/agent/agent")

def create_graph():
    state=Path.home()/".obdiag"
    state.mkdir(exist_ok=True)
    shutil.copytree("/opt/agent/agent/plugins",state,dirs_exist_ok=True)
    (state/"config").mkdir(exist_ok=True)
    import yaml
    model_settings={"llm":{"model":"openai:gpt-4o-mini","api_key":os.environ["OPENAI_API_KEY"],"base_url":"https://api.openai.com/v1"}}
    config_path=state/"config/agent.yml"
    config_path.write_text(yaml.safe_dump(model_settings));config_path.chmod(0o600)
    workspace=Path.home()/"obdiag-workspace";workspace.mkdir(exist_ok=True);os.chdir(workspace)
    from src.common.stdio import StdIO,IO
    from src.handler.agent.handler import load_agent_config,OBDIAG_CONFIG_PATH,SYSTEM_PROMPT,_ASSISTANT_ID
    from src.handler.agent.models import AgentConfig,AgentDependencies,read_obcluster_config
    from src.handler.agent.toolsets import create_obdiag_tools,create_db_tools,create_config_gen_tools,create_knowledge_tools
    from src.handler.agent.tui.agent import create_cli_agent
    from src.handler.agent.tui.config import create_model,build_stream_config
    from src.handler.agent.tui.sessions import generate_thread_id,get_checkpointer
    stdio=StdIO(IO(0,output_stream=sys.stderr,error_stream=sys.stderr))
    native_config=AgentConfig.from_dict(load_agent_config(stdio=stdio))
    deps=AgentDependencies(cluster_config=read_obcluster_config(OBDIAG_CONFIG_PATH),stdio=stdio,
        config_path=OBDIAG_CONFIG_PATH,oceanbase_knowledge_bearer_token=native_config.oceanbase_knowledge_bearer_token)
    native_tools=create_obdiag_tools(lambda:deps.config_path,stdio)+create_db_tools(lambda:deps)+create_config_gen_tools(stdio)
    if native_config.oceanbase_knowledge_enabled:
        native_tools+=create_knowledge_tools(lambda:native_config.oceanbase_knowledge_bearer_token)
    class NativeDiagnostic:
        async def ainvoke(self,inputs,config=None):
            text=inputs["message"]
            if not isinstance(text,str) or not text.strip():raise ValueError("Nonempty text required")
            try:
                model_result=create_model();model_result.apply_to_settings()
                async with get_checkpointer() as cp:
                    agent,_=create_cli_agent(model=model_result.model,assistant_id=_ASSISTANT_ID,
                        tools=native_tools,system_prompt=SYSTEM_PROMPT,interactive=True,
                        auto_approve=not native_config.tool_approval,
                        extra_interrupt_on={fn.__name__:True for fn in native_tools} if native_config.tool_approval else None,
                        checkpointer=cp)
                    result=await agent.ainvoke({"messages":[{"role":"user","content":text}]},
                        build_stream_config(generate_thread_id(),_ASSISTANT_ID))
                    if result.get("__interrupt__"):raise RuntimeError("Native agent requires human input or tool approval")
                    messages=result.get("messages",[])
                    if not messages or messages[-1].type!="ai" or not messages[-1].content:
                        raise RuntimeError("Native diagnostic agent produced no answer")
                    return result
            finally:deps.close()
        def invoke(self,inputs,config=None):return asyncio.run(self.ainvoke(inputs,config))
    return NativeDiagnostic()
