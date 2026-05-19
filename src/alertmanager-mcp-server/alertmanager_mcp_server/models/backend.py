"""Alertmanager backend models."""
from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class BackendDescriptor(BaseModel):
    id: str
    display_name: Optional[str] = None
    base_url: str
    labels: Dict[str, str] = Field(default_factory=dict)
    health: Literal["unknown", "healthy", "degraded", "unhealthy"] = "unknown"
    version: Optional[str] = None
    is_default: bool = False


class BackendsSummary(BaseModel):
    backends: List[BackendDescriptor]
