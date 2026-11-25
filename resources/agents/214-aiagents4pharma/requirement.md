---
agent_description: "AIAgents4Pharma native supervisor"
input_type: text
---

# AIAgents4Pharma native supervisor

The entrypoint is the upstream `talk2aiagents4pharma.agents.main_agent.get_app` supervisor with its full Talk2BioModels and Talk2KnowledgeGraphs agents. Original prompts, handoffs and tool definitions are retained. The deployment uses the native CPU-compatible graph extraction path and installs the complete Python project.

Inputs are text messages. The greeting runs without uploaded files or supplied knowledge-graph data. Pharmaceutical analysis may require real SBML files, model identifiers, Milvus collections, embedding services and external search credentials. No research dataset, biological result or backend service is fabricated for this smoke test. Missing prerequisites surface through the original tool behavior. This greeting does not validate research results or database-backed analysis.

The Docker deployment uses Linux images for Docker hosts on Windows, macOS and Linux. The model is configured through the declared model-interception route.
