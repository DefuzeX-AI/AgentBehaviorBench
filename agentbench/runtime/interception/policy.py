"""Host policy for shared ACP model traffic (not an Agent manifest setting)."""

# Change this one value and start a new run to switch shared ACP interception.
# Dedicated model.source="native" integrations retain their native credentials.
ACP_MODEL_MODE = "replace"


def acp_model_mode():
    if ACP_MODEL_MODE not in ("observe", "replace"):
        from .config import InterceptionConfigurationError
        raise InterceptionConfigurationError('ACP_MODEL_MODE must be observe or replace')
    return ACP_MODEL_MODE
