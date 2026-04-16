from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from app.chunk_processor import chunk_processor
from app.config import settings
from app.module2.intelligence_extractor import intelligence_extractor
from app.schemas import (
    ChunkUploadMessage,
    HumanAddActionMessage,
    HumanAddDecisionMessage,
    HumanAddRiskMessage,
    HumanDeleteItemMessage,
    HumanRestoreItemMessage,
    HumanUpdateItemMessage,
    HumanUpdateSummaryMessage,
    MeetingEndMessage,
    MeetingStartMessage,
    StateSyncRequestMessage,
)
from app.session_manager import session_manager
from app.state_manager import state_manager
from app.websocket_manager import websocket_manager

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _run_diarization_backfill(context) -> None:
    message = await chunk_processor.process_diarization_backfill(context)
    if message:
        await websocket_manager.send_json(message)


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.app_env,
    }


@app.websocket("/ws/meeting")
async def meeting_websocket(websocket: WebSocket) -> None:
    await websocket_manager.connect(websocket)

    try:
        while True:
            raw_message = await websocket.receive_json()
            message_type = raw_message.get("type")

            if message_type == "meeting_start":
                parsed = MeetingStartMessage.model_validate(raw_message)
                session, _memory = session_manager.create_session(parsed.payload.metadata)
                await websocket_manager.send_json(
                    {
                        "type": "session_created",
                        "payload": {
                            "meeting_id": session.meeting_id,
                            "created_at": session.created_at.isoformat(),
                            "metadata": session.metadata.model_dump(mode="json"),
                        },
                    }
                )
                continue

            if message_type == "chunk_upload":
                parsed = ChunkUploadMessage.model_validate(raw_message)
                await websocket_manager.send_json(
                    {
                        "type": "processing_started",
                        "payload": {
                            "meeting_id": parsed.payload.meeting_id,
                            "sequence_number": parsed.payload.sequence_number,
                        },
                    }
                )
                try:
                    result = await chunk_processor.process_chunk(parsed.payload)
                    await websocket_manager.send_json(
                        {
                            "type": "transcript_update",
                            "payload": result.transcript_payload,
                        }
                    )
                    await websocket_manager.send_json(
                        {
                            "type": "processing_complete",
                            "payload": result.processing_payload,
                        }
                    )
                    if result.diarization_context:
                        asyncio.create_task(_run_diarization_backfill(result.diarization_context))
                    if (
                        settings.live_intelligence_enabled
                        and result.transcript_payload["rolling_memory"]["llm_window_ready"]
                    ):
                        intelligence_messages = await intelligence_extractor.process_ready_window(
                            parsed.payload.meeting_id,
                            parsed.payload.sequence_number,
                        )
                        for message in intelligence_messages:
                            await websocket_manager.send_json(message)
                except Exception as exc:
                    await websocket_manager.send_error(
                        code="chunk_processing_error",
                        detail=str(exc),
                    )
                continue

            if message_type == "meeting_end":
                parsed = MeetingEndMessage.model_validate(raw_message)
                final_messages = await intelligence_extractor.finalize_meeting(parsed.payload.meeting_id)
                for message in final_messages:
                    await websocket_manager.send_json(message)
                session = session_manager.end_session(parsed.payload.meeting_id)
                await websocket_manager.send_json(
                    {
                        "type": "session_ended",
                        "payload": {
                            "meeting_id": session.meeting_id,
                            "ended_at": datetime.now(timezone.utc).isoformat(),
                        },
                    }
                )
                continue

            if message_type == "state_sync_request":
                StateSyncRequestMessage.model_validate(raw_message)
                active_session = session_manager.get_session()
                extra_payload = (
                    intelligence_extractor.build_state_sync_payload(active_session.meeting_id)
                    if active_session and state_manager.get(active_session.meeting_id)
                    else {
                        "transcript": [],
                        "rolling_memory": None,
                        "intelligence": None,
                        "final_report": None,
                    }
                )
                await websocket_manager.send_json(
                    {
                        "type": "state_sync",
                        "payload": {
                            "session": session_manager.snapshot(),
                            **extra_payload,
                        },
                    }
                )
                continue

            if message_type == "human_update_summary":
                parsed = HumanUpdateSummaryMessage.model_validate(raw_message)
                visible = state_manager.update_summary(parsed.payload.meeting_id, parsed.payload.summary)
                await websocket_manager.send_json(
                    {
                        "type": "intelligence_update",
                        "payload": {
                            "meeting_id": parsed.payload.meeting_id,
                            "chunk_id": session_manager.get_session(parsed.payload.meeting_id).last_chunk_sequence
                            if session_manager.get_session(parsed.payload.meeting_id)
                            else 0,
                            **visible,
                            "llm_metadata": {
                                "provider": "human",
                                "model": "manual-edit",
                                "queued_windows": len(state_manager.get(parsed.payload.meeting_id).queued_llm_window)
                                if state_manager.get(parsed.payload.meeting_id)
                                else 0,
                            },
                        },
                    }
                )
                continue

            if message_type == "human_add_action":
                parsed = HumanAddActionMessage.model_validate(raw_message)
                visible = state_manager.add_action_item(
                    parsed.payload.meeting_id,
                    parsed.payload.task,
                    parsed.payload.owner,
                    parsed.payload.deadline,
                    parsed.payload.priority,
                    parsed.payload.evidence,
                )
                await websocket_manager.send_json(
                    {
                        "type": "intelligence_update",
                        "payload": {
                            "meeting_id": parsed.payload.meeting_id,
                            "chunk_id": session_manager.get_session(parsed.payload.meeting_id).last_chunk_sequence
                            if session_manager.get_session(parsed.payload.meeting_id)
                            else 0,
                            **visible,
                            "llm_metadata": {
                                "provider": "human",
                                "model": "manual-add",
                                "queued_windows": len(state_manager.get(parsed.payload.meeting_id).queued_llm_window)
                                if state_manager.get(parsed.payload.meeting_id)
                                else 0,
                            },
                        },
                    }
                )
                continue

            if message_type == "human_add_decision":
                parsed = HumanAddDecisionMessage.model_validate(raw_message)
                visible = state_manager.add_decision(
                    parsed.payload.meeting_id,
                    parsed.payload.decision,
                    parsed.payload.evidence,
                )
                s = session_manager.get_session(parsed.payload.meeting_id)
                await websocket_manager.send_json(
                    {
                        "type": "intelligence_update",
                        "payload": {
                            "meeting_id": parsed.payload.meeting_id,
                            "chunk_id": s.last_chunk_sequence if s else 0,
                            **visible,
                            "llm_metadata": {
                                "provider": "human",
                                "model": "manual-add",
                                "queued_windows": len(state_manager.get(parsed.payload.meeting_id).queued_llm_window)
                                if state_manager.get(parsed.payload.meeting_id)
                                else 0,
                            },
                        },
                    }
                )
                continue

            if message_type == "human_add_risk":
                parsed = HumanAddRiskMessage.model_validate(raw_message)
                visible = state_manager.add_risk(
                    parsed.payload.meeting_id,
                    parsed.payload.risk,
                    parsed.payload.evidence,
                )
                s = session_manager.get_session(parsed.payload.meeting_id)
                await websocket_manager.send_json(
                    {
                        "type": "intelligence_update",
                        "payload": {
                            "meeting_id": parsed.payload.meeting_id,
                            "chunk_id": s.last_chunk_sequence if s else 0,
                            **visible,
                            "llm_metadata": {
                                "provider": "human",
                                "model": "manual-add",
                                "queued_windows": len(state_manager.get(parsed.payload.meeting_id).queued_llm_window)
                                if state_manager.get(parsed.payload.meeting_id)
                                else 0,
                            },
                        },
                    }
                )
                continue

            if message_type in {"human_update_item", "human_update_action"}:
                parsed = HumanUpdateItemMessage.model_validate(raw_message)
                visible = state_manager.update_item(
                    parsed.payload.meeting_id,
                    parsed.payload.item_type,
                    parsed.payload.item_id,
                    parsed.payload.updates,
                )
                await websocket_manager.send_json(
                    {
                        "type": "intelligence_update",
                        "payload": {
                            "meeting_id": parsed.payload.meeting_id,
                            "chunk_id": session_manager.get_session(parsed.payload.meeting_id).last_chunk_sequence
                            if session_manager.get_session(parsed.payload.meeting_id)
                            else 0,
                            **visible,
                            "llm_metadata": {
                                "provider": "human",
                                "model": "manual-edit",
                                "queued_windows": len(state_manager.get(parsed.payload.meeting_id).queued_llm_window)
                                if state_manager.get(parsed.payload.meeting_id)
                                else 0,
                            },
                        },
                    }
                )
                continue

            if message_type == "human_delete_item":
                parsed = HumanDeleteItemMessage.model_validate(raw_message)
                visible = state_manager.mark_item_deleted(
                    parsed.payload.meeting_id,
                    parsed.payload.item_type,
                    parsed.payload.item_id,
                    True,
                )
                await websocket_manager.send_json(
                    {
                        "type": "intelligence_update",
                        "payload": {
                            "meeting_id": parsed.payload.meeting_id,
                            "chunk_id": session_manager.get_session(parsed.payload.meeting_id).last_chunk_sequence
                            if session_manager.get_session(parsed.payload.meeting_id)
                            else 0,
                            **visible,
                            "llm_metadata": {
                                "provider": "human",
                                "model": "manual-delete",
                                "queued_windows": len(state_manager.get(parsed.payload.meeting_id).queued_llm_window)
                                if state_manager.get(parsed.payload.meeting_id)
                                else 0,
                            },
                        },
                    }
                )
                continue

            if message_type == "human_restore_item":
                parsed = HumanRestoreItemMessage.model_validate(raw_message)
                visible = state_manager.mark_item_deleted(
                    parsed.payload.meeting_id,
                    parsed.payload.item_type,
                    parsed.payload.item_id,
                    False,
                )
                await websocket_manager.send_json(
                    {
                        "type": "intelligence_update",
                        "payload": {
                            "meeting_id": parsed.payload.meeting_id,
                            "chunk_id": session_manager.get_session(parsed.payload.meeting_id).last_chunk_sequence
                            if session_manager.get_session(parsed.payload.meeting_id)
                            else 0,
                            **visible,
                            "llm_metadata": {
                                "provider": "human",
                                "model": "manual-restore",
                                "queued_windows": len(state_manager.get(parsed.payload.meeting_id).queued_llm_window)
                                if state_manager.get(parsed.payload.meeting_id)
                                else 0,
                            },
                        },
                    }
                )
                continue

            await websocket_manager.send_error(
                code="unsupported_message",
                detail=f"Unsupported message type: {message_type}",
            )

    except WebSocketDisconnect:
        websocket_manager.disconnect(websocket)
    except ValidationError as exc:
        await websocket_manager.send_error(code="validation_error", detail=str(exc))
        websocket_manager.disconnect(websocket)
    except ValueError as exc:
        await websocket_manager.send_error(code="session_error", detail=str(exc))
        websocket_manager.disconnect(websocket)
    except Exception as exc:
        await websocket_manager.send_error(code="unexpected_error", detail=str(exc))
        websocket_manager.disconnect(websocket)
