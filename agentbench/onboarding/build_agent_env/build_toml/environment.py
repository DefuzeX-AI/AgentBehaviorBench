"""Assign environment names to their owner before rendering the manifest."""

import re

CREDENTIAL_NAME = re.compile(r"(?:API_KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)", re.I)


def runtime_environment(env_keys, secret_env_keys, interception, *, network_mode='replace'):
    """Return disjoint runtime lists according to adapter credential ownership.

    Replacement excludes interceptor-owned model secrets; observation retains
    native model secrets in the Agent runtime. Explicit tool
    secrets and credential-shaped ordinary names use the runtime secret resolver.
    Only variable names are handled; no environment values are read or invented.
    Inputs remain unchanged so the original model response can be audited.
    """
    declared_models = {item["agent_env"] for item in interception["credentials"]} if interception else set()
    if network_mode == 'observe':
        secret_env_keys = [*secret_env_keys, *sorted(declared_models)]
    model_names = declared_models if network_mode == 'replace' else set()
    secrets = dict.fromkeys(name for name in secret_env_keys if name not in model_names)
    for name in env_keys:
        if name not in model_names and CREDENTIAL_NAME.search(name):
            secrets[name] = None
    ordinary = dict.fromkeys(name for name in env_keys if name not in model_names and name not in secrets)
    return {key: list(names) for key, names in
            (("env_keys", ordinary), ("secret_env_keys", secrets)) if names}
