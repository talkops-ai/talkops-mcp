"""Audit log models."""
from datetime import datetime
from typing import List
from pydantic import BaseModel, Field


class AuditLogEntry(BaseModel):
    timestamp: datetime
    backend_id: str
    operation: str
    principal: str
    summary: str
