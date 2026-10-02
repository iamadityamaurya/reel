"""Persist generated ideas to a Supabase table via the PostgREST API.

Every row stores an ``index`` (1-based position within the generated batch), the
idea text, and a ``video_generated`` flag that defaults to ``false``.
"""

import logging
from typing import Any, Dict, List, Optional

import httpx

import config
from utils import retry_call

logger = logging.getLogger(__name__)


class SupabaseTableMissingError(Exception):
    """Raised when the configured ideas table does not exist yet."""


class SupabaseIdeaStore:
    def __init__(
        self,
        url: Optional[str] = None,
        service_key: Optional[str] = None,
        table: Optional[str] = None,
    ):
        self.url = (url or config.SUPABASE_URL).rstrip("/")
        self.service_key = service_key or config.SUPABASE_SERVICE_KEY
        self.table = table or config.SUPABASE_IDEAS_TABLE

    # ------------------------------------------------------------------ helpers
    @property
    def is_configured(self) -> bool:
        return bool(self.url and self.service_key)

    def _headers(self, prefer: Optional[str] = None) -> Dict[str, str]:
        headers = {
            "apikey": self.service_key,
            "Authorization": f"Bearer {self.service_key}",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        return headers

    def _missing_table_message(self) -> str:
        ref = self.url.replace("https://", "").split(".")[0] if self.url else "<project-ref>"
        return (
            f"Supabase table '{self.table}' does not exist. Run supabase/schema.sql "
            f"once in the SQL editor: "
            f"https://supabase.com/dashboard/project/{ref}/sql/new"
        )

    # ------------------------------------------------------------------- checks
    def table_exists(self) -> bool:
        if not self.is_configured:
            return False
        try:
            response = httpx.get(
                f"{self.url}/rest/v1/{self.table}",
                headers=self._headers(),
                params={"select": "id", "limit": "0"},
                timeout=30.0,
            )
        except httpx.HTTPError as e:
            logger.warning("Could not reach Supabase to check the table: %s", e)
            return False

        if response.status_code == 200:
            return True
        if response.status_code == 404 or "PGRST205" in response.text:
            return False
        logger.warning(
            "Unexpected Supabase response while checking table: %s %s",
            response.status_code,
            response.text[:200],
        )
        return False

    # -------------------------------------------------------------------- write
    def save_ideas(
        self,
        ideas: List[Dict[str, Any]],
        topic: str = "",
        tone: str = "",
        video_generated: bool = False,
    ) -> List[Dict[str, Any]]:
        """Insert ``ideas`` and return the created rows (with their Supabase ids)."""
        if not ideas:
            return []
        if not self.is_configured:
            logger.warning("Supabase is not configured; skipping idea persistence.")
            return []

        rows = []
        for position, idea in enumerate(ideas, start=1):
            rows.append({
                # `index` is the 1-based position of the idea in this batch.
                "index": idea.get("id") or position,
                "title": str(idea.get("title", "")).strip(),
                "hook": str(idea.get("hook", "") or "").strip() or None,
                "summary": str(idea.get("summary", "") or "").strip() or None,
                "topic": (topic or None),
                "tone": (tone or None),
                "video_generated": bool(video_generated),
            })

        def _insert() -> List[Dict[str, Any]]:
            response = httpx.post(
                f"{self.url}/rest/v1/{self.table}",
                headers=self._headers(prefer="return=representation"),
                json=rows,
                timeout=60.0,
            )
            if response.status_code in (200, 201):
                return response.json()
            if response.status_code == 404 or "PGRST205" in response.text:
                raise SupabaseTableMissingError(self._missing_table_message())
            raise RuntimeError(
                f"Supabase insert failed ({response.status_code}): {response.text[:300]}"
            )

        # SupabaseTableMissingError is not in `exceptions`, so it is raised at once
        # instead of being retried.
        return retry_call(
            _insert,
            attempts=3,
            base_delay=2.0,
            exceptions=(httpx.HTTPError, RuntimeError),
            description="Supabase idea insert",
        )

    def mark_video_generated(self, row_id: str, generated: bool = True) -> bool:
        """Update the ``video_generated`` flag for a single row."""
        if not self.is_configured:
            return False

        def _patch() -> bool:
            response = httpx.patch(
                f"{self.url}/rest/v1/{self.table}",
                headers=self._headers(),
                params={"id": f"eq.{row_id}"},
                json={"video_generated": generated},
                timeout=30.0,
            )
            if response.status_code not in (200, 204):
                logger.warning(
                    "Failed to update video_generated (%s): %s",
                    response.status_code,
                    response.text[:200],
                )
                return False
            return True

        try:
            return retry_call(
                _patch,
                attempts=3,
                base_delay=2.0,
                exceptions=(httpx.HTTPError, RuntimeError),
                description="Supabase update video_generated",
            )
        except Exception as e:
            logger.warning("Could not update video_generated after retries: %s", e)
            return False

    # --------------------------------------------------------------------- read
    def list_ideas(
        self,
        limit: int = 100,
        video_generated: Optional[bool] = None,
        order: str = "created_at.desc",
    ) -> List[Dict[str, Any]]:
        if not self.is_configured:
            return []
        params = {
            "select": "*",
            "order": order,
            "limit": str(limit),
        }
        if video_generated is not None:
            params["video_generated"] = f"eq.{str(video_generated).lower()}"

        def _get() -> List[Dict[str, Any]]:
            response = httpx.get(
                f"{self.url}/rest/v1/{self.table}",
                headers=self._headers(),
                params=params,
                timeout=30.0,
            )
            if response.status_code == 404 or "PGRST205" in response.text:
                raise SupabaseTableMissingError(self._missing_table_message())
            response.raise_for_status()
            return response.json()

        return retry_call(
            _get,
            attempts=3,
            base_delay=2.0,
            exceptions=(httpx.HTTPError, RuntimeError),
            description="Supabase list ideas",
        )

    def next_unprocessed_idea(self) -> Optional[Dict[str, Any]]:
        """
        Return the next idea with ``video_generated = false``, starting from
        ``index`` 1 and moving upward. Returns ``None`` when all are done.
        """
        rows = self.list_ideas(
            limit=50,
            video_generated=False,
            order="index.asc,created_at.asc",
        )
        for row in rows:
            if not row.get("video_generated"):
                return row
        return None