from __future__ import annotations

import base64
import json
from datetime import datetime
from textwrap import wrap

from app.models.memory import MemoryState
from app.session_manager import SessionRecord


def build_json_export(state: MemoryState, session: SessionRecord | None) -> dict:
    return {
        "meeting": {
            "meeting_id": state.meeting_id,
            "title": session.metadata.title if session else state.meeting_id,
            "mode": session.metadata.mode if session else "live",
            "started_at": session.created_at.isoformat() if session else None,
            "generated_at": datetime.utcnow().isoformat() + "Z",
        },
        "summary": {
            "running_summary": state.running_summary,
            "current_topic_focus": state.current_topic_focus,
            "unresolved_issues": state.unresolved_issues,
            "locked": state.summary_human_locked,
        },
        "action_items": [item.model_dump(mode="json") for item in state.action_items if not item.deleted],
        "decisions": [item.model_dump(mode="json") for item in state.decisions if not item.deleted],
        "risks": [item.model_dump(mode="json") for item in state.risks if not item.deleted],
        "review_flags": state.review_flags,
        "transcript": [utterance.model_dump(mode="json") for utterance in state.display_transcript_buffer],
    }


def build_pdf_export(report: dict) -> bytes:
    title = report["meeting"]["title"] or "LiveNote Meeting Report"
    lines: list[str] = [
        title,
        "",
        "Summary",
        report["summary"]["running_summary"] or "No summary available.",
        "",
        "Current Topic",
        report["summary"]["current_topic_focus"] or "No current topic extracted.",
        "",
        "Action Items",
    ]

    action_items = report.get("action_items", [])
    if action_items:
        for item in action_items:
            lines.append(f"- {item['owner']}: {item['task']} ({item['deadline']})")
    else:
        lines.append("- None")

    lines.extend(["", "Decisions"])
    decisions = report.get("decisions", [])
    if decisions:
        for decision in decisions:
            lines.append(f"- {decision['decision']}")
    else:
        lines.append("- None")

    lines.extend(["", "Risks"])
    risks = report.get("risks", [])
    if risks:
        for risk in risks:
            lines.append(f"- {risk['risk']}")
    else:
        lines.append("- None")

    wrapped_lines: list[str] = []
    for line in lines:
        wrapped_lines.extend(wrap(line, width=92) or [""])

    return _simple_pdf_from_lines(wrapped_lines)


def encode_export_payload(report: dict) -> dict:
    json_bytes = json.dumps(report, indent=2).encode("utf-8")
    pdf_bytes = build_pdf_export(report)
    return {
        "report": report,
        "json_base64": base64.b64encode(json_bytes).decode("utf-8"),
        "pdf_base64": base64.b64encode(pdf_bytes).decode("utf-8"),
    }


def _escape_pdf_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _simple_pdf_from_lines(lines: list[str]) -> bytes:
    page_height = 792
    top = 760
    line_height = 14
    max_lines = 48
    pages = [lines[index:index + max_lines] for index in range(0, len(lines), max_lines)] or [[]]

    objects: list[bytes] = []

    def add_object(payload: str | bytes) -> int:
        data = payload.encode("latin-1") if isinstance(payload, str) else payload
        objects.append(data)
        return len(objects)

    font_id = add_object("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    page_ids: list[int] = []
    content_ids: list[int] = []

    pages_id = len(objects) + 1
    for page_lines in pages:
        content_stream = ["BT", "/F1 11 Tf"]
        y = top
        for line in page_lines:
            content_stream.append(f"1 0 0 1 54 {y} Tm ({_escape_pdf_text(line)}) Tj")
            y -= line_height
        content_stream.append("ET")
        stream_data = "\n".join(content_stream).encode("latin-1")
        content_id = add_object(
            b"<< /Length " + str(len(stream_data)).encode("ascii") + b" >>\nstream\n" + stream_data + b"\nendstream"
        )
        content_ids.append(content_id)
        page_id = add_object(
            f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 612 {page_height}] /Contents {content_id} 0 R /Resources << /Font << /F1 {font_id} 0 R >> >> >>"
        )
        page_ids.append(page_id)

    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects.insert(pages_id - 1, f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("latin-1"))
    catalog_id = add_object(f"<< /Type /Catalog /Pages {pages_id} 0 R >>")

    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode("ascii"))
        output.extend(obj)
        output.extend(b"\nendobj\n")

    xref_start = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\nstartxref\n{xref_start}\n%%EOF".encode(
            "ascii"
        )
    )
    return bytes(output)
