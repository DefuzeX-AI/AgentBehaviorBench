"""Load optional live SDK metadata before requesting configuration generation."""

import json

from agentbench.sdk.contracts import SDKOnboardingContext
from ..openrouter_provider.privacy import contains_secret
from .errors import BuildError
from .writer import save_json


def load_sdk_context(session):
    if not isinstance(session.sdk, SDKOnboardingContext):
        return {}
    session.output_fn("SDK: refreshing onboarding catalog")
    configured = getattr(session.sdk, 'configured_onboarding_context', None)
    evaluation = getattr(session.manifest_options, 'evaluation', None)
    context = dict(configured(environ=session.environ, timeout=session.settings.timeout_seconds,
                              evaluation=evaluation) if configured and evaluation is not None else
                   session.sdk.onboarding_context(environ=session.environ, timeout=session.settings.timeout_seconds))
    if contains_secret(json.dumps(context), session.environ):
        raise BuildError("SDK onboarding context contains credentials; it was not saved or sent to the model")
    save_json(session.attempt / "sdk-context.json", context)
    session.output_fn("SDK: current catalog loaded")
    return context
