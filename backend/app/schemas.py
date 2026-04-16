from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


FrontendMessageType = Literal[
    "meeting_start",
    "chunk_upload",
    "meeting_end",
    "human_add_action",
    "human_add_decision",
    "human_add_risk",
    "human_update_action",
    "human_update_item",
    "human_delete_item",
    "human_restore_item",
    "human_update_summary",
    "state_sync_request",
]

BackendMessageType = Literal[
    "session_created",
    "transcript_update",
    "speaker_backfill",
    "intelligence_update",
    "processing_started",
    "processing_complete",
    "trust_violation",
    "consolidation_complete",
    "session_ended",
    "state_sync",
    "ack",
    "error",
]


class MeetingMetadata(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    mode: Literal["live", "demo"]
    startedAt: datetime | None = None


class MeetingStartPayload(BaseModel):
    metadata: MeetingMetadata


class MeetingStartMessage(BaseModel):
    type: Literal["meeting_start"]
    payload: MeetingStartPayload


class ChunkUploadPayload(BaseModel):
    meeting_id: str
    sequence_number: int = Field(ge=1)
    mime_type: str
    audio_base64: str = Field(min_length=1)
    captured_at: datetime
    duration_ms: int = Field(gt=0)


class ChunkUploadMessage(BaseModel):
    type: Literal["chunk_upload"]
    payload: ChunkUploadPayload


class MeetingEndPayload(BaseModel):
    meeting_id: str


class MeetingEndMessage(BaseModel):
    type: Literal["meeting_end"]
    payload: MeetingEndPayload


class StateSyncRequestMessage(BaseModel):
    type: Literal["state_sync_request"]
    payload: dict = Field(default_factory=dict)


class HumanUpdateSummaryPayload(BaseModel):
    meeting_id: str
    summary: str


class HumanUpdateSummaryMessage(BaseModel):
    type: Literal["human_update_summary"]
    payload: HumanUpdateSummaryPayload


class HumanAddActionPayload(BaseModel):
    meeting_id: str
    task: str
    owner: str
    deadline: str = "unspecified"
    priority: str = "medium"
    evidence: str = ""


class HumanAddActionMessage(BaseModel):
    type: Literal["human_add_action"]
    payload: HumanAddActionPayload


class HumanAddDecisionPayload(BaseModel):
    meeting_id: str
    decision: str
    evidence: str = ""


class HumanAddDecisionMessage(BaseModel):
    type: Literal["human_add_decision"]
    payload: HumanAddDecisionPayload


class HumanAddRiskPayload(BaseModel):
    meeting_id: str
    risk: str
    evidence: str = ""


class HumanAddRiskMessage(BaseModel):
    type: Literal["human_add_risk"]
    payload: HumanAddRiskPayload


class HumanUpdateItemPayload(BaseModel):
    meeting_id: str
    item_type: Literal["action_item", "decision", "risk"]
    item_id: str
    updates: dict = Field(default_factory=dict)


class HumanUpdateItemMessage(BaseModel):
    type: Literal["human_update_item", "human_update_action"]
    payload: HumanUpdateItemPayload


class HumanDeleteRestorePayload(BaseModel):
    meeting_id: str
    item_type: Literal["action_item", "decision", "risk"]
    item_id: str


class HumanDeleteItemMessage(BaseModel):
    type: Literal["human_delete_item"]
    payload: HumanDeleteRestorePayload


class HumanRestoreItemMessage(BaseModel):
    type: Literal["human_restore_item"]
    payload: HumanDeleteRestorePayload


IncomingMessage = (
    MeetingStartMessage
    | ChunkUploadMessage
    | MeetingEndMessage
    | StateSyncRequestMessage
    | HumanUpdateSummaryMessage
    | HumanAddActionMessage
    | HumanAddDecisionMessage
    | HumanAddRiskMessage
    | HumanUpdateItemMessage
    | HumanDeleteItemMessage
    | HumanRestoreItemMessage
)


class OutgoingMessage(BaseModel):
    type: BackendMessageType
    payload: dict
