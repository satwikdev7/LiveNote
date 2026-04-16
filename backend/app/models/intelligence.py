from pydantic import BaseModel, Field


class EvidenceSpan(BaseModel):
    utterance_id: str | None = None
    start_time: float
    end_time: float
    text: str = Field(default="")


class ActionItem(BaseModel):
    id: str
    task: str
    owner: str
    deadline: str = Field(default="unspecified")
    normalized_deadline: str | None = None
    priority: str = Field(default="medium")
    status: str = Field(default="pending")
    needs_review: bool = Field(default=False)
    evidence: str = Field(default="")
    evidence_spans: list[EvidenceSpan] = Field(default_factory=list)
    chunk_origin: int = Field(default=0)
    human_locked: bool = Field(default=False)
    deleted: bool = Field(default=False)


class Decision(BaseModel):
    id: str
    decision: str
    evidence: str = Field(default="")
    evidence_spans: list[EvidenceSpan] = Field(default_factory=list)
    chunk_origin: int = Field(default=0)
    human_locked: bool = Field(default=False)
    deleted: bool = Field(default=False)


class Risk(BaseModel):
    id: str
    risk: str
    evidence: str = Field(default="")
    evidence_spans: list[EvidenceSpan] = Field(default_factory=list)
    chunk_origin: int = Field(default=0)
    human_locked: bool = Field(default=False)
    deleted: bool = Field(default=False)
