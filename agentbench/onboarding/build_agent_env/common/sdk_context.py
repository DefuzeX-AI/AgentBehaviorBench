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
    context = dict(session.sdk.onboarding_context(
        environ=session.environ, timeout=session.settings.timeout_seconds))
    if contains_secret(json.dumps(context), session.environ):
        raise BuildError("SDK onboarding context contains credentials; it was not saved or sent to the model")
    save_json(session.attempt / "sdk-context.json", context)
    session.output_fn("SDK: current catalog loaded")
    return context
