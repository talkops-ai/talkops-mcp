"""Kargo credentials models."""

from typing import Optional
from pydantic import BaseModel, ConfigDict


class CreateRepoCredentialsRequest(BaseModel):
    """Internal request payload for Kargo REST repo-credentials API."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    name: str
    repoUrl: str
    type: str
    username: Optional[str] = None
    password: Optional[str] = None
    description: Optional[str] = None
    repoUrlIsRegex: Optional[bool] = False
