"""Silence models aligned with Alertmanager API v2."""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field
from alertmanager_mcp_server.models.alert import AlertMatcher, GettableAlert


class SilenceStatus(BaseModel):
    state: str = Field(..., description="active, pending, or expired")


class PostableSilence(BaseModel):
    matchers: List[AlertMatcher]
    startsAt: datetime
    endsAt: datetime
    createdBy: str
    comment: str


class GettableSilence(PostableSilence):
    id: str
    status: SilenceStatus
    updatedAt: Optional[datetime] = None


class SilenceEffectPreview(BaseModel):
    affected_alert_count: int = 0
    affected_alerts_preview: List[GettableAlert] = Field(default_factory=list)
    warning_flag: bool = False
