"""Execute optional build and certification stages for a downloaded Agent."""

from agentbench.cli.environment import execution_environment_snapshot, load_project_environment
from agentbench.cli.sdk import sdk_arguments
from agentbench.sdk.contracts import SDKOnboarding
from agentbench.sdk.plugins import resolve_sdk

from .build_agent_env.common.registry import register_agent
from .build_agent_env.service import build_agent_environment
from .build_agent_env.common.errors import BuildError
from .build_agent_env.common.validation import validate_unit
from .build_agent_env.build_toml.options import options_from_cli


def configure_download(source, args, *, output_fn=print) -> int:
    """Run requested stages only; -c never implicitly generates configuration."""

    load_project_environment(args.env_file)
    loaded = execution_environment_snapshot()
    options = sdk_arguments(args)

    if "sdk_selection" not in options:
        options["sdk_selection"] = resolve_sdk(args.sdk)
    selection = options["sdk_selection"]
    sdk = selection.value

    if not isinstance(sdk, SDKOnboarding):
        raise BuildError("Selected SDK has no onboarding validation capability")

    
    if args.build:
        output_fn("Collecting source evidence and requesting an OpenRouter configuration...")
        result = build_agent_environment(
            source, sdk=sdk, registry_path=args.registry, environ=loaded.environ,
            settings_path=args.build_settings, model=args.build_model, answers_path=args.answers,
            output_fn=output_fn, manifest_options=options_from_cli(args))
        output_fn(f"Build status: {result.status}; records: {result.attempt}")
        for message in result.messages:
            output_fn(f"  {message}")
        if result.status != "generated":
            if result.status == "needs_input":
                output_fn("Answer these questions in a text file and repeat -b --answers PATH.")
            elif result.status == "conflict":
                output_fn("Review the reported existing file; completed files were preserved.")
            return 2
        output_fn(f"Registered {result.agent_id}; static checks passed, certification pending.")

        
    if args.certify:
        agent_id = validate_unit(source.directory, sdk)
        register_agent(source.directory, args.registry, source.repository)
        from agentbench.cli.features.certify import certify

        return certify(agent_id, registry_path=args.registry, environ=loaded.environ,
                       concurrency=loaded.concurrency, assume_yes=args.yes,
                       model=args.model, output_path=args.output, **options,
                       **({"viewer_starter": None} if args.no_view else {}))
    return 0
