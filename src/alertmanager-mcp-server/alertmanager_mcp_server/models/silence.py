"""Silence models aligned with Alertmanager API v2."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from alertmanager_mcp_server.domain.timeparse import format_rfc3339_utc
from alertmanager_mcp_server.models.alert import AlertMatcher, GettableAlert


class SilenceStatus(BaseModel):
    state: str = Field(..., description="active, pending, or expired")


class PostableSilence(BaseModel):
    id: Optional[str] = Field(
        default=None,
        description="Optional existing silence ID for native in-place updates",
    )
    matchers: List[AlertMatcher]
    startsAt: datetime
    endsAt: datetime
    createdBy: str
    comment: str

    def to_api_payload(self) -> Dict[str, Any]:
        """Serialize to Alertmanager v2 `PostableSilence` JSON with RFC3339 UTC timestamps."""
        start_dt = (
            self.startsAt.replace(tzinfo=timezone.utc)
            if self.startsAt.tzinfo is None
            else self.startsAt.astimezone(timezone.utc)
        )
        end_dt = (
            self.endsAt.replace(tzinfo=timezone.utc)
            if self.endsAt.tzinfo is None
            else self.endsAt.astimezone(timezone.utc)
        )
        payload: Dict[str, Any] = {
            "matchers": [m.model_dump() for m in self.matchers],
            "startsAt": format_rfc3339_utc(start_dt),
            "endsAt": format_rfc3339_utc(end_dt),
            "createdBy": self.createdBy,
            "comment": self.comment,
        }
        if self.id is not None:
            payload["id"] = self.id
        return payload


class GettableSilence(PostableSilence):
    id: str  # type: ignore[assignment]
    status: SilenceStatus
    updatedAt: Optional[datetime] = None


class SilenceEffectPreview(BaseModel):
    affected_alert_count: int = 0
    affected_alerts_preview: List[GettableAlert] = Field(default_factory=list)
    warning_flag: bool = False
