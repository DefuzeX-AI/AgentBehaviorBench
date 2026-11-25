"""Bind the complete native VibeSurf workflow to a real Chromium session."""
import asyncio
import os
from pathlib import Path
import sys

# Native numerical libraries must fit beside Chromium in the one-CPU runtime.
for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"


class NativeBinding:
    async def ainvoke(self, value, config=None, **kwargs):
        from vibe_surf.agents.vibe_surf_agent import VibeSurfAgent
        from vibe_surf.browser.agen_browser_profile import AgentBrowserProfile
        from vibe_surf.browser.agent_browser_session import AgentBrowserSession
        from vibe_surf.browser.browser_manager import BrowserManager
        from vibe_surf.llm.openai_compatible import ChatOpenAICompatible
        from vibe_surf.tools.vibesurf_tools import VibeSurfTools

        text = value['message'] if isinstance(value, dict) else value
        profile = AgentBrowserProfile(executable_path='/usr/bin/chromium',
            user_data_dir=str(Path.home()/'chromium'), headless=True, keep_alive=True)
        browser = AgentBrowserSession(browser_profile=profile)
        manager = BrowserManager(main_browser_session=browser)
        tools = VibeSurfTools()
        try:
            await browser.start()
            llm = ChatOpenAICompatible(model=os.environ['DEEPSEEK_MODEL'], base_url='https://api.openai.com/v1',
                                      api_key=os.environ['OPENAI_API_KEY'])
            agent = VibeSurfAgent(llm=llm, browser_manager=manager, tools=tools,
                                  workspace_dir='/workspace')
            reply = await agent.run(text)
            errors = [e for e in agent.activity_logs if e.get('agent_status') == 'error']
            if errors or not reply or reply.startswith('# Task Execution Failed'):
                raise RuntimeError(f'Native VibeSurf workflow failed: {reply}; {errors}')
            return {'messages': [{'role': 'assistant', 'content': reply}],
                    'native_activity_logs': agent.activity_logs}
        finally:
            await tools.unregister_mcp_clients()
            await manager.close()
            await browser.kill()

    def invoke(self, value, config=None, **kwargs):
        return asyncio.run(self.ainvoke(value, config=config, **kwargs))


def create_graph():
    sys.path.insert(0, '/opt/agent/agent')
    return NativeBinding()
