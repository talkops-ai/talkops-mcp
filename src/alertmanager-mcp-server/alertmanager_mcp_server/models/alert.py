"""Alert and alert group models aligned with Alertmanager API v2."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AlertMatcher(BaseModel):
    name: str = Field(..., description="Label name")
    value: str = Field(..., description="Label value or regex pattern")
    isRegex: bool = Field(default=False, description="Whether value is a regex")
    isEqual: bool = Field(default=True, description="False for negative matching")


class AlertStatus(BaseModel):
    state: str = Field(default="active", description="active, suppressed, unprocessed")
    silencedBy: List[str] = Field(default_factory=list)
    inhibitedBy: List[str] = Field(default_factory=list)


class GettableAlert(BaseModel):
    fingerprint: str
    labels: Dict[str, str] = Field(default_factory=dict)
    annotations: Dict[str, str] = Field(default_factory=dict)
    startsAt: datetime
    endsAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None
    generatorURL: Optional[str] = None
    receivers: List[Any] = Field(default_factory=list)
    status: Dict[str, Any] = Field(default_factory=dict)

    @property
    def receiver_names(self) -> List[str]:
        """Return normalized receiver name strings attached to this alert."""
        names: List[str] = []
        for r in self.receivers:
            if isinstance(r, dict) and r.get("name"):
                names.append(str(r["name"]))
            elif isinstance(r, str) and r:
                names.append(r)
        return names


class AlertGroup(BaseModel):
    labels: Dict[str, str] = Field(default_factory=dict)
    receiver: Optional[Dict[str, Any]] = None
    alerts: List[GettableAlert] = Field(default_factory=list)

    @property
    def receiver_name(self) -> Optional[str]:
        if isinstance(self.receiver, dict) and self.receiver.get("name"):
            return str(self.receiver["name"])
        return None
