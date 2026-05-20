"""Configuration, receiver, and routing models."""
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from alertmanager_mcp_server.models.alert import AlertMatcher


class ReceiverConfig(BaseModel):
    name: str
    type: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class RoutingRoute(BaseModel):
    matchers: List[AlertMatcher] = Field(default_factory=list)
    receiver: Optional[str] = None
    group_by: List[str] = Field(default_factory=list)
    group_wait: Optional[str] = None
    group_interval: Optional[str] = None
    repeat_interval: Optional[str] = None


class RoutingTreeNode(BaseModel):
    """Nested routing tree node preserving the full tree structure."""
    receiver: Optional[str] = None
    matchers: List[AlertMatcher] = Field(default_factory=list)
    group_by: List[str] = Field(default_factory=list)
    group_wait: Optional[str] = None
    group_interval: Optional[str] = None
    repeat_interval: Optional[str] = None
    continue_routing: bool = False
    routes: List["RoutingTreeNode"] = Field(default_factory=list)


class InhibitionRule(BaseModel):
    source_matchers: List[AlertMatcher] = Field(default_factory=list)
    target_matchers: List[AlertMatcher] = Field(default_factory=list)
    equal: List[str] = Field(default_factory=list)


class AlertmanagerConfigSnapshot(BaseModel):
    routes: List[RoutingRoute] = Field(default_factory=list)
    inhibitions: List[InhibitionRule] = Field(default_factory=list)


class RoutingSimulationResult(BaseModel):
    receivers: List[str] = Field(default_factory=list)
    route_path: str = ""
    inhibited_by: List[str] = Field(default_factory=list)


class RoutingExplanation(BaseModel):
    """Rich routing explanation with human-readable reasoning."""
    matched_route: str = ""
    receivers: List[str] = Field(default_factory=list)
    group_labels: List[str] = Field(default_factory=list)
    inhibited_by: List[str] = Field(default_factory=list)
    explanation: str = ""


class SilenceChange(BaseModel):
    """A silence change event for governance audit."""
    silence_id: str
    action: str  # "created", "expired", "updated"
    matchers_summary: str = ""
    created_by: str = ""
    comment: str = ""
    timestamp: datetime
