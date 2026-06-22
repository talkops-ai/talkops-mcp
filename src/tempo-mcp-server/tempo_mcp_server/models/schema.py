"""Schema discovery models.

Scope enum enhanced per research: includes event, link, instrumentation
in addition to resource, span, intrinsic.
"""

from typing import Any, Dict, List, Optional

from tempo_mcp_server.models.common import BaseTempoModel


# Valid scopes for tag discovery (validated against Tempo docs)
VALID_SCOPES = ("all", "resource", "span", "intrinsic", "event", "link", "instrumentation")


class AttributeNameEntry(BaseTempoModel):
    """A single discovered attribute/tag name."""

    name: str
    scope: Optional[str] = None       # resource, span, intrinsic, etc.
    category: Optional[str] = None    # "k8s", "http", "otel", "custom", etc.
    description: Optional[str] = None


class AttributeNamesOutput(BaseTempoModel):
    """Output of tempo_get_attribute_names tool."""

    scopes: List[Dict[str, List[AttributeNameEntry]]] = []
    total: int = 0
    metrics: Optional[Dict[str, Any]] = None


class AttributeValuesOutput(BaseTempoModel):
    """Output of tempo_get_attribute_values tool."""

    attribute_name: str
    tag_values: List[str] = []
    truncated: bool = False
    total: int = 0
    metrics: Optional[Dict[str, Any]] = None


class K8sSemanticMapping(BaseTempoModel):
    """Mapping between a canonical K8s concept and Tempo attribute(s)."""

    semantic_key: str                              # e.g. "namespace", "pod", "deployment"
    candidate_attributes: List[str] = []           # e.g. ["k8s.namespace.name", "namespace"]
    preferred_attribute: Optional[str] = None      # The canonical OTel attribute
    notes: Optional[str] = None


class K8sAttributeMap(BaseTempoModel):
    """Output of tempo_get_k8s_attribute_map tool."""

    backend_id: Optional[str] = None
    tenant: Optional[str] = None
    mappings: List[K8sSemanticMapping] = []
