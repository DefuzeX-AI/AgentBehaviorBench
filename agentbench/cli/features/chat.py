"""Chat with one enabled Agent in a single session, then print its record paths."""
import math
import os
import time
from pathlib import Path

from .base import CommandFeature
from .run import DEFAULT_REGISTRY_PATH
from ..environment import load_project_environment
from agentbench.cli.options import configure_env_file, configure_model


def configure_parser(parser):
    from agentbench.cli.viewer.server import DEFAULT_HOST, DEFAULT_PORT
    from .view import viewer_port
    parser.add_argument("agent", metavar="AGENT", help="Enabled Agent ID or `observe --list` number")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--output", type=Path, default=Path("results/chat"),
                        help="Chat artifact root; each chat creates a run-ID subdirectory.")
    configure_env_file(parser)
    configure_model(parser, help="Target model name; defaults to the selected provider model")
    parser.add_argument("--timeout", type=float, help="Positive per-turn timeout in seconds")
    parser.add_argument("--view", action="store_true",
                        help="Chat in a local web page with the live trajectory instead of the terminal.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="With --view: viewer host.")
    parser.add_argument("--port", type=viewer_port, default=DEFAULT_PORT,
                        help="With --view: viewer port; a busy port falls back to a free one.")
    parser.add_argument("--no-open", action="store_true", help="With --view: print the page URL without opening a browser.")


def execute(args):
    from agentbench.observe.catalog import enabled_agents, resolve_agent, select_agent
    try:
        if args.timeout is not None and (not math.isfinite(args.timeout) or args.timeout <= 0):
            raise ValueError("--timeout must be finite and positive")
        if args.view:
            from agentbench.cli.viewer.server import require_viewer_assets
            require_viewer_assets()
        agent = resolve_agent(select_agent(enabled_agents(args.registry), args.agent), args.registry)
        load_project_environment(args.env_file)
        environ = dict(os.environ)
        if args.model:
            environ["ABB_MODEL"] = args.model
    except Exception as exc:
        print(f"Chat failed: {exc}")
        return 1
    if args.view:
        return chat_in_page(agent, args, environ)
    from agentbench.observe.chat import run_chat
    run = run_chat(agent, output=args.output, environ=environ, timeout=args.timeout)
    return 0 if run is not None and run["status"] == "succeeded" else 1


def chat_in_page(agent, args, environ, *, open_page=None):
    """Start the Agent, then open the page; Ctrl+C here also ends the chat."""
    import webbrowser
    from agentbench.cli.viewer.chat import start_chat_viewer
    from agentbench.observe.chat import report
    from agentbench.observe.chat_view import ChatController
    controller = ChatController(agent, output=args.output, environ=environ, timeout=args.timeout)
    print(f"Starting {agent.agent_id}; the first image build can take several minutes.", flush=True)
    server = None
    try:
        try:
            directory = controller.start()
        except Exception as exc:
            print(f"Chat failed: {type(exc).__name__}: {exc}")
            controller.end(wait=True)
            return 1
        server, url = start_chat_viewer(controller, host=args.host, port=args.port)
        print(f"Run: {directory.name}\nView: {url}\nChat in the page; End chat there or press Ctrl+C here.", flush=True)
        if not getattr(args, "no_open", False):
            (open_page or webbrowser.open)(url)
        while not controller.ended.wait(0.5):
            pass
        report(controller.run, controller.directory)
        print("The page stays open for reviewing and marking the trajectory; press Ctrl+C to stop it.", flush=True)
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        if not controller.ended.is_set():
            print("\nEnding the chat and saving records...", flush=True)
            controller.end(wait=True)
            report(controller.run, controller.directory)
        print("Viewer stopped.")
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
    run = controller.run or {}
    return 0 if run.get("status") == "succeeded" else 1


FEATURE = CommandFeature(name="chat", help="Chat with one enabled Agent and save its records",
                         description=__doc__, configure=configure_parser, execute=execute)
