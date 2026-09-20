"""Validate ACP plans without importing the CLI or starting authentication."""
from ...common.responses import validate_response


def validate_plan(plan, schema, session):
    validate_response(plan, schema, session)


def binding_steps(plan):
    return []
