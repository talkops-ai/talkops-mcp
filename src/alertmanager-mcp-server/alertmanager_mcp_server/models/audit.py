"""Audit log models."""

from datetime import datetime
from typing import Any, Dict, Literal
from pydantic import BaseModel, Field

AuditOutcome = Literal[
    "succeeded",
    "denied",
    "aborted",
    "confirmation_required",
    "failed",
]


class AuditLogEntry(BaseModel):
    timestamp: datetime
    backend_id: str
    operation: str
    principal: str
    summary: str
    outcome: AuditOutcome = "succeeded"
    details: Dict[str, Any] = Field(default_factory=dict)
