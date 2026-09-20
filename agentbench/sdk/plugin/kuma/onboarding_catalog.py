"""Live Strategy Group discovery and snapshot-based profile selection checks."""

from .configuration import api_key


def fetch(*, environ, timeout, evaluation=None):
    """Return the full official catalog and the worker's intrinsic capabilities.

    Inputs are the explicit BBA environment snapshot and HTTP timeout in seconds.
    Uses the same public API as ``kuma strategies list``: one authenticated GET,
    with a fresh catalog rather than a saved fallback. No Case/Judge/model runs.
    Credentials never appear in the returned JSON or in public error messages.
    """
    try:
        from kuma import KumaClient, DEFAULT_BASE_URL
        from kuma.evidence.runtime_contract import derive_casegen_evidence_capabilities
    except ImportError:
        raise ValueError("KUMA catalog discovery requires the plugin's PyPI requirements") from None
    credential, _ = api_key(environ)
    try:
        catalog = KumaClient(api_key=credential,
                             base_url=environ.get("KUMA_BASE_URL") or DEFAULT_BASE_URL,
                             timeout=timeout).strategy_group_catalog()
    except Exception:
        raise ValueError("Could not refresh the KUMA Strategy Group catalog; check the SDK credential, "
                         "service URL and connection, then retry -b. No saved catalog was substituted.") from None
    # Runtime and onboarding share the same explicit evidence policy.
    # These are SDK evidence capabilities, not a claim that every tool is traced.
    from agentbench.sdk.common.workspace import workspace_policy
    policy = workspace_policy({'evaluation': evaluation or {}})
    capabilities = derive_casegen_evidence_capabilities(
        track_files=policy.track_files, trace_evidence_configured=True)
    return {"strategy_group_catalog": catalog.to_dict(),
            "available_evidence_capabilities": list(capabilities)}


def validate_selection(directory, *, context):
    """Check the generated profile against the exact catalog sent to the model.

    Uses official KUMA parsers/resolution for ID, version, availability and
    required Evidence. A generated profile must explicitly select one group;
    existing runtime profiles outside onboarding retain SDK default behavior.
    """
    from kuma.repository.agent_profiles import parse_agent_profile
    from kuma.repository.strategy_groups import (
        available_evidence_capabilities, resolve_strategy_group, validate_strategy_group_catalog,
    )
    catalog = validate_strategy_group_catalog(context.get("strategy_group_catalog"))
    profile = parse_agent_profile(directory / "requirement.md")
    if profile.strategy_group is None:
        raise ValueError("requirement.md must declare strategy_group with the exact id and string version "
                         "from sdk_context.strategy_group_catalog")
    capabilities = available_evidence_capabilities(
        profile.tool_capabilities, tuple(context["available_evidence_capabilities"]))
    try:
        resolve_strategy_group(catalog, explicit=profile.strategy_group, scan=False,
                               available_capabilities=capabilities)
    except ValueError:
        raise
    except Exception as exc:
        code = getattr(exc, "code", "strategy_group_invalid")
        raise ValueError(f"KUMA strategy_group selection failed ({code}); select an available exact "
                         "id/version from sdk_context whose required_capabilities are supported") from None
