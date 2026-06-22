"""Common Tempo data models shared across module types."""

from pydantic import BaseModel


class BaseTempoModel(BaseModel):
    """Base model for all Tempo-related models."""

    model_config = {"populate_by_name": True}
