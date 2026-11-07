"""Render the manifest from reviewed native source facts and deployment policy."""
from pathlib import Path
from agentbench.onboarding.source import DownloadedAgent
from agentbench.onboarding.build_agent_env.build_toml.rendering import render_manifest
from agentbench.onboarding.build_agent_env.build_toml.options import ManifestOptions
u=Path(__file__).resolve().parents[1]
facts={'framework':'langgraph','display_name':'NVIDIA Deep Researcher Agent (native NAT workflow)','adapter':{'config':None,'graph_id':None,'binding':'bridge.py:create_graph','input_key':'message','output_key':'response'},'models':[{'protocol':'openai-chat','agent_env':'OPENAI_API_KEY','endpoint':None}],'tool_routes':[{'host_patterns':['api.tavily.com'],'ports':[443],'methods':['POST'],'path_patterns':['/search']}],'env_keys':[],'secret_env_keys':['TAVILY_API_KEY'],'input_fields':[{'name':'message','type':'string','required':True}]}
s=DownloadedAgent(u,'https://github.com/NVIDIA-AI-Blueprints/deep-researcher-agent','951a1a1114e9818073ddbe2a5fdbfa824751f4d3',(),warnings=('internal symlinks materialized manually',))
u.joinpath('agent.toml').write_text(render_manifest(facts,source=s,agent_id='deep-researcher-agent',options=ManifestOptions(timeout_sec=1200)))
# Tavily is optional at native startup. Its absent-key path remains the native
# explicit tool-unavailable error; full research acceptance still requires it.
import tomllib
from agentbench.onboarding.build_agent_env.build_toml.encoding import encode_manifest
manifest=tomllib.loads(u.joinpath('agent.toml').read_text())
manifest['runtime']['optional_secret_env_keys']=manifest['runtime'].pop('secret_env_keys')
manifest['llm_interception']['network_config']='network/rules.toml'
u.joinpath('agent.toml').write_text(encode_manifest(manifest))
