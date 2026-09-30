"""Enrich runtime facts with observations made inside the worker environment."""
from dataclasses import replace
import os
import platform
import shutil

from agentbench.runtime.contracts.environment import ExecutionEnvironment


def observe_environment(value=None, *, workspace=None):
    environment = ExecutionEnvironment.from_dict(value) if value else ExecutionEnvironment()
    # Only inspect a bounded public executable list. Do not run Agent code, dump
    # environment variables, or mistake a program on PATH for an Agent tool.
    programs = ('python', 'python3', 'node', 'npm', 'git', 'rg', 'sh', 'bash', 'curl')
    process = {'system': platform.system(), 'python_version': platform.python_version(),
               'uid': os.getuid() if hasattr(os, 'getuid') else None,
               'gid': os.getgid() if hasattr(os, 'getgid') else None,
               'programs_on_path': [name for name in programs if shutil.which(name)]}
    return replace(environment, process=process, workspace=workspace)
