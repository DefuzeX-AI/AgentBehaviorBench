"""Vite bridge: print the trajectory route of one attempt directory, as the Python viewer serves it."""
import json
from pathlib import Path
import sys

from agentbench.observe.view_api import RunViewAPI

if __name__ == '__main__':
    # The second argument carries the viewer query; the trajectory has no options.
    print(json.dumps(RunViewAPI(Path(sys.argv[1])).trajectory(), ensure_ascii=False))
