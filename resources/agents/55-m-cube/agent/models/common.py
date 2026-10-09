from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# SessionStatus is shared by API responses and workflow state reporting.
class SessionStatus(str, Enum):
    queued = "queued"
    running = "running"
    waiting_human = "waiting_human"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


# ErrorInfo is the normalized error payload returned by all endpoints.
class ErrorInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., min_length=1, description="Stable machine-readable error code.")
    message: str = Field(..., min_length=1, description="Human-readable error message.")
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional structured details for debugging and UI hints.",
    )
    retryable: bool = Field(
        False,
        description="Whether client can safely retry the request.",
    )


# ApiEnvelope is the uniform HTTP response wrapper for success and failure cases.
class ApiEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(..., min_length=1, description="Server-side request identifier.")
    session_id: str = Field(..., min_length=1, description="Workflow session identifier.")
    status: SessionStatus = Field(..., description="Current status of the session.")
    data: dict[str, Any] | None = Field(
        default=None,
        description="Structured payload for successful responses.",
    )
    error: ErrorInfo | None = Field(
        default=None,
        description="Structured error payload when status is failed/cancelled.",
    )
