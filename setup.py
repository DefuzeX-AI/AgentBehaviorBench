"""Bundle the canonical binding guide without maintaining a second source copy."""
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py


class BuildPy(build_py):
    def run(self):
        super().run()
        source = Path(__file__).parent / "docs" / "LangGraph Bindings.md"
        target = Path(self.build_lib) / (
            "agentbench/onboarding/build_agent_env/frameworks/langgraph/assets/handbook.md"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        self.copy_file(str(source), str(target))


setup(cmdclass={"build_py": BuildPy})
