"""Alert and alert group models aligned with Alertmanager API v2."""
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AlertMatcher(BaseModel):
    name: str = Field(..., description="Label name")
    value: str = Field(..., description="Label value or regex pattern")
    isRegex: bool = Field(False, description="Whether value is a regex")
    isEqual: bool = Field(True, description="False for negative matching")


class AlertStatus(BaseModel):
    state: str = Field("active", description="active, suppressed, unprocessed")
    silencedBy: List[str] = Field(default_factory=list)
    inhibitedBy: List[str] = Field(default_factory=list)


class GettableAlert(BaseModel):
    fingerprint: str
    labels: Dict[str, str] = Field(default_factory=dict)
    annotations: Dict[str, str] = Field(default_factory=dict)
    startsAt: datetime
    endsAt: Optional[datetime] = None
    generatorURL: Optional[str] = None
    status: Dict[str, Any] = Field(default_factory=dict)


class AlertGroup(BaseModel):
    labels: Dict[str, str] = Field(default_factory=dict)
    alerts: List[GettableAlert] = Field(default_factory=list)
