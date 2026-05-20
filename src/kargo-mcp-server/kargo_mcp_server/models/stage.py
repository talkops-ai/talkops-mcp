"""Kargo Stage models."""


from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from kargo_mcp_server.models.common import ObjectMeta


class RequestedFreightOrigin(BaseModel):
    """Origin of requested freight.

    In Kargo, the origin must always be a Warehouse. Stage-to-stage
    dependencies are expressed via ``FreightSources.stages`` instead.
    """

    kind: str = "Warehouse"  # Must always be "Warehouse"
    name: str


class FreightSources(BaseModel):
    """Specifies where requested Freight may be obtained from.

    At least one of ``direct`` or ``stages`` must be specified:
    - ``direct=True``: Freight can be obtained directly from the origin Warehouse.
    - ``stages``: List of upstream Stage names that can supply the Freight.
    """

    direct: bool = False
    stages: List[str] = Field(default_factory=list)
    availability_strategy: Optional[str] = Field(default=None, alias="availabilityStrategy")
    required_soak_time: Optional[str] = Field(default=None, alias="requiredSoakTime")

    model_config = {"populate_by_name": True}


class RequestedFreight(BaseModel):
    """Freight request entry within a Stage spec.

    Each entry binds to a specific Warehouse (origin) and describes
    how the Stage can obtain Freight from that Warehouse — either
    directly or through upstream Stages.
    """

    origin: RequestedFreightOrigin
    sources: FreightSources = Field(default_factory=FreightSources)

    model_config = {"populate_by_name": True}


class StageSpec(BaseModel):
    """Stage specification."""

    variables: Dict[str, Any] = Field(default_factory=dict)
    requestedFreight: List[RequestedFreight] = Field(default_factory=list)
    promotionTemplate: Optional[Dict[str, Any]] = None

    model_config = {"populate_by_name": True}


class StageStatus(BaseModel):
    """Stage status."""

    current_freight_id: Optional[str] = Field(default=None, alias="currentFreightId")
    last_promotion_id: Optional[str] = Field(default=None, alias="lastPromotionId")
    conditions: List[Dict[str, Any]] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class Stage(BaseModel):
    """Full Kargo Stage resource."""

    apiVersion: str = "kargo.akuity.io/v1alpha1"
    kind: str = "Stage"
    metadata: ObjectMeta
    spec: StageSpec = Field(default_factory=StageSpec)
    status: Optional[StageStatus] = None


class StageSummary(BaseModel):
    """Compact stage summary with DAG topology."""

    name: str
    upstream_stages: List[str] = Field(default_factory=list)
    downstream_stages: List[str] = Field(default_factory=list)
    current_freight_id: Optional[str] = None
    auto_promotion_enabled: bool = True
