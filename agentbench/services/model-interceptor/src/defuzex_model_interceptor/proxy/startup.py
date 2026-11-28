"""Optional target-owned checks must finish before the proxy reports readiness."""
from ..registry import load_targets


def preflight_targets(config):
    if config.mode != 'replace':
        return
    plugins = load_targets()
    targets = config.targets.values() if config.targets else (config.target,)
    for target in targets:
        hook = getattr(plugins[target.target_plugin], 'preflight', None)
        if hook is not None:
            secrets = (target.secret,) if target.secret else tuple(c.secret for c in config.credentials)
            hook(target, secrets)
