"""Common Kargo data models shared across resource types."""


from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ObjectMeta(BaseModel):
    """Kubernetes-style object metadata."""

    name: str
    namespace: Optional[str] = None
    labels: Dict[str, str] = Field(default_factory=dict)
    annotations: Dict[str, str] = Field(default_factory=dict)
    creationTimestamp: Optional[datetime] = None

    model_config = {"populate_by_name": True}
