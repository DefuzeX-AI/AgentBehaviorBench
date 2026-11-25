# Yuxi native chatbot integration

The Docker launcher starts isolated loopback PostgreSQL and Redis. The binding
uses native schema/preset initialization, initial identity creation, model provider
configuration, project/session creation, runtime context preparation and
`ChatbotAgent.get_graph`. Native default prompt, skills, plugins, authorization and
tools are retained. No permission flags are patched. Only the model connection is
configured for ABB interception. External sandbox/Cube and knowledge services
are not provisioned; native dependency failures remain failures.

Docker Linux containers can be used on Windows, macOS and Linux:
`python -m agentbench evaluate yuxi --sdk native --case-file resources/agents/150-yuxi/smoke-case.json --cases 1 --max-steps 1 --no-view -y`
