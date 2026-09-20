"""Select a framework-derived mode; shared transport/evidence lives outside modes."""
from .common import _error_envelope  # Compatibility for existing error-contract callers.


def ModelInterceptorAddon(config):
    if config.mode == 'observe':
        from ..observe.handler import ObserveInterceptor
        return ObserveInterceptor(config)
    if config.mode == 'replace':
        from ..replace.handler import ReplaceInterceptor
        return ReplaceInterceptor(config)
    raise ValueError('Unknown internal interception mode')
