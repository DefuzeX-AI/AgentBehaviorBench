"""Permissive "auth" to replace the langsmith API key auth."""

from langgraph_sdk import Auth

auth = Auth()


@auth.authenticate
async def authenticate(authorization: str) -> str:
    """Enable all users."""
    return "default_user"
