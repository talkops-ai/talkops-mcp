"""Kargo credentials models."""

from typing import Optional
from pydantic import BaseModel, Field

class CreateRepoCredentialsRequest(BaseModel):
    """Request model for creating repository credentials."""
    name: str
    repoUrl: str
    type: str
    username: Optional[str] = None
    password: Optional[str] = None
    description: Optional[str] = None
    repoUrlIsRegex: Optional[bool] = False
