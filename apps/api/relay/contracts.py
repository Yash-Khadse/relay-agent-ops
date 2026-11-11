from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WorkflowConfig(StrictModel):
    max_revisions: int = Field(2, ge=0, le=3)
    approval_hours: int = Field(24, ge=1, le=168)
    crew_enabled: bool = False


class ExecutionInput(StrictModel):
    template_id: Literal["research", "support", "content"]
    topic: str = Field(min_length=3, max_length=160)
    brief: str = Field(min_length=10, max_length=8000)
    source_ids: list[str] = Field(default_factory=list, max_length=8)
    config: WorkflowConfig = Field(default_factory=WorkflowConfig)


class DecisionInput(StrictModel):
    decision: Literal["approve", "reject", "revise"]
    comment: str = Field(default="", max_length=2000)


class SourceInput(StrictModel):
    title: str = Field(min_length=2, max_length=120)
    content: str = Field(min_length=10, max_length=24000)


class LoginInput(StrictModel):
    code: str = Field(min_length=32, max_length=128)


class Evidence(StrictModel):
    source_id: str
    quote: str = Field(min_length=1, max_length=1500)
    finding: str = Field(min_length=1, max_length=2000)


class ResearchResult(StrictModel):
    summary: str = Field(max_length=8000)
    evidence: list[Evidence] = Field(max_length=24)
    limitations: list[str] = Field(max_length=12)


class AnalysisResult(StrictModel):
    findings: list[str] = Field(min_length=1, max_length=12)
    tradeoffs: list[str] = Field(max_length=12)
    category: str = Field(default="general", max_length=80)
    priority: Literal["low", "normal", "high", "urgent"] = "normal"


class DraftResult(StrictModel):
    title: str = Field(min_length=1, max_length=160)
    markdown: str = Field(min_length=20, max_length=30000)
    source_ids: list[str] = Field(max_length=24)


class ReviewResult(StrictModel):
    passed: bool
    issues: list[str] = Field(max_length=15)
    summary: str = Field(max_length=3000)


class Handoff(StrictModel):
    workflow_id: str
    current_node: str
    source_agent: str
    target_agent: str
    task: str
    context: dict[str, Any]
    output_schema: str
    timeout_seconds: int
    permissions: list[str]
    correlation_id: str
