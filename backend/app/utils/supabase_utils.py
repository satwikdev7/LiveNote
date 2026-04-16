from __future__ import annotations

import json
import urllib.error
import urllib.request

from app.config import settings


class SupabasePersistence:
    def is_configured(self) -> bool:
        return bool(settings.supabase_url and settings.supabase_service_role_key)

    def persist_report(self, report: dict, exports: dict) -> dict | None:
        if not self.is_configured():
            return None

        headers = {
            "apikey": settings.supabase_service_role_key or "",
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

        meeting_id = report["meeting"]["meeting_id"]
        meeting_row = {
            "meeting_id": meeting_id,
            "title": report["meeting"]["title"],
            "mode": report["meeting"]["mode"],
            "started_at": report["meeting"]["started_at"],
            "generated_at": report["meeting"]["generated_at"],
            "summary": report["summary"]["running_summary"],
            "report": report,
        }

        self._request_json(
            f"{settings.supabase_url}/rest/v1/meetings?on_conflict=meeting_id",
            method="POST",
            headers={**headers, "Prefer": "resolution=merge-duplicates,return=minimal"},
            data=json.dumps(meeting_row).encode("utf-8"),
        )

        json_path = f"{meeting_id}/report.json"
        pdf_path = f"{meeting_id}/report.pdf"
        self._upload_storage(json_path, base64_data=exports["json_base64"], content_type="application/json")
        self._upload_storage(pdf_path, base64_data=exports["pdf_base64"], content_type="application/pdf")

        return {
            "json_path": json_path,
            "pdf_path": pdf_path,
        }

    def _upload_storage(self, path: str, base64_data: str, content_type: str) -> None:
        url = f"{settings.supabase_url}/storage/v1/object/{settings.supabase_storage_bucket}/{path}"
        headers = {
            "apikey": settings.supabase_service_role_key or "",
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "Content-Type": content_type,
            "x-upsert": "true",
        }
        data = __import__("base64").b64decode(base64_data)
        self._request_json(url, method="POST", headers=headers, data=data, allow_non_json=True)

    def _request_json(
        self,
        url: str,
        method: str,
        headers: dict[str, str],
        data: bytes,
        allow_non_json: bool = False,
    ) -> dict | None:
        request = urllib.request.Request(url=url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                body = response.read()
                if allow_non_json or not body:
                    return None
                return json.loads(body.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Supabase persistence failed: {exc.code} {detail}") from exc


supabase_persistence = SupabasePersistence()
