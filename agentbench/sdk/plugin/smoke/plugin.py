from pathlib import Path

from agentbench.sdk.integration.plugin import ContainerSDKPlugin

plugin = ContainerSDKPlugin(
    create_run=__package__ + ".backend:create_run",
    requirements=Path(__file__).with_name("requirements.txt"),
)
