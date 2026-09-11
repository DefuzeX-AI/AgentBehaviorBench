"""Interactive enabled-Agent selection and native input, without a Judge."""
import json
import math
import os
from argparse import ArgumentTypeError
from pathlib import Path

from .base import CommandFeature
from .run import DEFAULT_REGISTRY_PATH
from ..environment import load_project_environment
from agentbench.observe.catalog import enabled_agents, select_agent, resolve_agent, tomllib
from agentbench.observe.service import observe
from agentbench.observe.store import summarize
from agentbench.observe.review import render_review


def configure_parser(parser):
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("selection", nargs="?", metavar="AGENT",
                           help="Enabled Agent number or ID; omit to choose interactively")
    selection.add_argument("--agent", help="Alias for the positional Agent number or ID")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--list", action="store_true", help="Show all enabled Agents and exit")
    parser.add_argument("--input", type=Path, help="Native input JSON file")
    parser.add_argument("--output", type=Path, default=Path("results/observe"))
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--model", type=model_name, metavar="MODEL",
                        help="OpenRouter model name (not an Agent number); defaults to OPENROUTER_MODEL")
    parser.add_argument("--timeout", type=float, help="Positive execution timeout in seconds")
    parser.add_argument("--show", type=Path, help="Review a saved observe run directory offline")


def model_name(value):
    if value.strip().isdecimal():
        raise ArgumentTypeError(
            f"--model 指定模型名称，不是 Agent 编号；选择 {value.strip()} 号 Agent 请使用 observe {value.strip()}"
        )
    return value


def native_input(agent, path, input_fn=input):
    if path:
        return json.loads(path.read_text(encoding="utf-8"))
    with (agent.path / "agent.toml").open("rb") as stream:
        fields = tomllib.load(stream).get("observe", {}).get("input_fields", [])
    if not fields:
        return json.loads(input_fn("Native input (JSON): "))
    value = {}
    for field in fields:
        while True:
            answer = input_fn(field.get("label", field["name"]) + ": ").strip()
            if answer or not field.get("required", False):
                break
            print("此字段必填。")
        if answer:
            value[field["name"]] = answer
    return value


def execute(args):
    try:
        if args.show:
            print(render_review(args.show))
            print(json.dumps(summarize(args.show), ensure_ascii=False, indent=2))
            return 0
        records = enabled_agents(args.registry)
        selected = args.selection or args.agent
        if selected is None or args.list:
            print("Enabled Agents:")
            for number, record in enumerate(records, 1):
                print(f"  {number}. {record['agent_id']} [{record.get('framework', '?')}] "
                      f"status={record.get('status', 'unknown')}")
        if args.list:
            return 0
        if not records:
            raise ValueError("没有 enabled Agent")
        if args.timeout is not None and (not math.isfinite(args.timeout) or args.timeout <= 0):
            raise ValueError("--timeout must be finite and positive")
        choice = selected
        while True:
            choice = choice or input("选择 Agent 编号（q 退出）: ").strip()
            if selected is None and choice.lower() == "q":
                return 0
            try:
                record = select_agent(records, choice)
                break
            except ValueError:
                if selected is not None:
                    raise
                print("无效选择，请重试。")
                choice = None
        agent = resolve_agent(record, args.registry)
        print(f"Selected Agent: {agent.agent_id}")
        value = native_input(agent, args.input)
        load_project_environment(args.env_file)
        environ = dict(os.environ)
        if args.model:
            environ["OPENROUTER_MODEL"] = args.model
        observe(agent, value, output=args.output, environ=environ, timeout=args.timeout)
        return 0
    except (KeyboardInterrupt, EOFError):
        print("Observe 已取消；已有记录保留。")
        return 130
    except Exception as exc:
        print(f"Observe failed: {exc}")
        return 1


FEATURE = CommandFeature(name="observe", help="Run one enabled Agent and save traces",
                         description=__doc__, configure=configure_parser, execute=execute)
