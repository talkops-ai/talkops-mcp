"""Pydantic models for logs collection profiles.

Represents the filelog receiver and log-related processor configuration,
corresponding to the ``otel://logs-profile/{namespace}/{collector}`` resource.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class FilelogReceiverConfig(BaseModel):
    """Configuration details of a filelog receiver instance."""

    include_paths: List[str] = Field(
        default_factory=list,
        description="Glob paths included for log collection",
    )
    exclude_paths: List[str] = Field(
        default_factory=list,
        description="Glob paths excluded from log collection",
    )
    include_file_name: bool = Field(
        default=True,
        description="Whether filename is added as an attribute",
    )
    include_file_path: bool = Field(
        default=False,
        description="Whether full path is added as an attribute",
    )
    multiline_config: Optional[Dict[str, str]] = Field(
        default=None,
        description="Multiline parsing configuration (line_start_pattern, etc.)",
    )
    operators: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Stanza operators for log parsing (regex, json, etc.)",
    )
    storage: Optional[str] = Field(
        default=None,
        description="Storage extension name for checkpoint persistence",
    )


class LogsCollectionProfile(BaseModel):
    """Logs collection profile extracted from collector configuration.

    Corresponds to the ``otel://logs-profile/{namespace}/{collector}`` resource.
    """

    collector_name: str = Field(description="Parent collector CRD name")
    collector_namespace: str = Field(description="Parent collector namespace")
    enabled: bool = Field(
        default=False,
        description="Whether any logs pipeline is configured",
    )

    filelog_receivers: List[FilelogReceiverConfig] = Field(
        default_factory=list,
        description="All filelog receiver configurations found",
    )

    # Safety assessment
    has_storage_checkpoint: bool = Field(
        default=False,
        description="Whether filelog uses persistent storage to avoid data loss on restart",
    )
    has_exclude_self: bool = Field(
        default=False,
        description="Whether collector's own logs are excluded to prevent feedback loops",
    )
    has_resource_detection: bool = Field(
        default=False,
        description="Whether resource detection processor enriches log records",
    )

    # Log processors in pipeline
    log_processors: List[str] = Field(
        default_factory=list,
        description="Processor names in the logs pipeline(s)",
    )
    log_exporters: List[str] = Field(
        default_factory=list,
        description="Exporter names in the logs pipeline(s)",
    )

    warnings: List[str] = Field(
        default_factory=list,
        description="Safety warnings (e.g., 'no storage checkpoint', 'self-collection risk')",
    )
