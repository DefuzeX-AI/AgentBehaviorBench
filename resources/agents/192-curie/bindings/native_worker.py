"""Start the original outer native graph binding with terminal transport."""
from bridge import run_native
from native_workflow import create_graph

if __name__ == "__main__":
    run_native(create_graph)
