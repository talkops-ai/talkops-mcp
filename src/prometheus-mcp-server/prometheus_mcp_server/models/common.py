"""Common Prometheus data models shared across module types."""

from pydantic import BaseModel


class BasePrometheusModel(BaseModel):
    """Base model for all Prometheus-related models."""

    model_config = {"populate_by_name": True}
