# PraisonAI native ACP integration

The launcher calls the upstream public `praisonai.acp.serve` entrypoint. It changes
only model connection settings using `ABB_AGENT_MODEL_*`. Native agent prompts,
read-only tool gates and session behavior remain in upstream source. All nine
Python packages are installed from the imported monorepo snapshot, without GPU
training extras; the native ACP coding path uses a remote model.

Docker Linux containers support Windows, macOS and Linux hosts. Run:
`python -m agentbench evaluate praisonai --sdk native --case-file resources/agents/148-praisonai/smoke-case.json --cases 1 --max-steps 1 --no-view -y`
