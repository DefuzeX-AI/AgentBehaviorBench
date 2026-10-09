from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ReviewIssue is emitted by review agents for logical/formality corrections.
class ReviewIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # New primary contract for draft logic review -> targeted patch flow.
    issue_type: str = Field(
        default="UNSUPPORTED_CLAIM_FEATURE",
        min_length=1,
        description="Issue category. For unsupported-claim flow this should be 'UNSUPPORTED_CLAIM_FEATURE'.",
    )
    claim_reference: str = Field(
        default="未明确标注",
        min_length=1,
        description="Claim index and missing feature reference, e.g. '权1中的弹性卡扣'.",
    )
    patch_instruction: str = Field(
        default="请在具体实施方式中补充与该权利要求特征一致的支撑段落。",
        min_length=1,
        description="Actionable patch text plus insertion section/location for downstream editor.",
    )

    # Backward-compatible legacy fields used by old reviewers/consumers.
    severity: Literal["low", "medium", "high"] = Field(
        default="medium",
        description="Legacy severity level.",
    )
    location: str = Field(
        default="specification",
        min_length=1,
        description="Legacy location marker.",
    )
    description: str = Field(
        default="检测到说明书对该权利要求特征支撑不足。",
        min_length=1,
        description="Legacy human-readable issue description.",
    )
    suggestion: str = Field(
        default="请在说明书对应实施方式中补充与该特征一致的明确支撑描述。",
        min_length=1,
        description="Legacy correction suggestion.",
    )


class ReviewReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issues: list[ReviewIssue] = Field(
        default_factory=list,
        description="Structured review issue list produced by logic review agent.",
    )
