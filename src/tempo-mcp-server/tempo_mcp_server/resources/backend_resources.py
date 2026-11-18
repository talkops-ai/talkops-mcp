"""Dynamic backend, capabilities, schema, overrides, and trace resources."""

import json
from dataclasses import asdict
from typing import Any, Dict, List

from tempo_mcp_server.exceptions import TempoResourceError
from tempo_mcp_server.resources.base import BaseResource
from tempo_mcp_server.utils.trace_summarizer import summarize_trace


class BackendResources(BaseResource):
    """Dynamic server capabilities, backend status, live schema, overrides, and trace resources."""

    def register(self, mcp_instance: Any) -> None:
        tempo_service = self.tempo_service
        config = self.config

        @mcp_instance.resource(
            "tempo://server/capabilities",
            name="tempo_server_capabilities",
            description="Server capabilities, write gate status, active toolsets, query guardrails, and detected backend features",
            mime_type="application/json",
        )
        async def tempo_server_capabilities() -> str:
            try:
                backend_features: List[Dict[str, Any]] = []
                for b in config.backends:
                    config_facts = await tempo_service.get_safe_status_config(b.id)
                    build_info = None
                    try:
                        build_info = await tempo_service.get_build_info(b.id)
                    except Exception:
                        pass
                    major, gen = tempo_service.detect_tempo_generation(build_info, None, config_facts)
                    backend_features.append({
                        "id": b.id,
                        "base_url": b.base_url,
                        "deployment_mode": b.deployment_mode,
                        "multi_tenant": b.multi_tenant,
                        "default_tenant": b.default_tenant,
                        "tempo_major_version": major,
                        "architecture_generation": gen,
                        "config_facts": config_facts,
                    })

                payload = {
                    "server": config.name,
                    "version": config.version,
                    "transport": config.transport,
                    "allow_write": config.allow_write,
                    "toolsets": config.toolsets,
                    "kubernetes_enabled": config.kubernetes.enabled,
                    "query_policy": asdict(config.query_policy),
                    "backends": backend_features,
                }
                return json.dumps(payload, indent=2)
            except Exception as e:
                raise TempoResourceError(f"Failed to read server capabilities: {e}") from e

        @mcp_instance.resource(
            "tempo://system/backends",
            name="tempo_backends",
            description="All configured Tempo backends with live health status",
            mime_type="application/json",
        )
        async def tempo_system_backends() -> str:
            try:
                backends = await tempo_service.list_backends()
                return json.dumps(backends, indent=2)
            except Exception as e:
                raise TempoResourceError(f"Failed to list backends: {e}") from e

        @mcp_instance.resource(
            "tempo://system/backends/{backend_id}",
            name="tempo_backend_detail",
            description="Detailed live profile for a specific Tempo backend",
            mime_type="application/json",
        )
        async def tempo_system_backend(backend_id: str) -> str:
            try:
                result = await tempo_service.get_backend_capabilities(backend_id)
                return json.dumps(result, indent=2)
            except Exception as e:
                raise TempoResourceError(
                    f"Failed to get backend '{backend_id}': {e}"
                ) from e

        @mcp_instance.resource(
            "tempo://schema/{backend_id}/attributes",
            name="tempo_backend_live_attributes",
            description="Live trace attribute presence and detected OTel Semantic Conventions for a backend",
            mime_type="application/json",
        )
        async def tempo_schema_attributes(backend_id: str) -> str:
            try:
                result = await tempo_service.detect_live_attributes(backend_id=backend_id)
                return json.dumps(result, indent=2)
            except Exception as e:
                raise TempoResourceError(
                    f"Failed to inspect live attributes on '{backend_id}': {e}"
                ) from e

        @mcp_instance.resource(
            "tempo://overrides/{backend_id}/{tenant}",
            name="tempo_tenant_overrides",
            description="Merged user-configurable overrides and current ETag for a Tempo tenant",
            mime_type="application/json",
        )
        async def tempo_tenant_overrides(backend_id: str, tenant: str) -> str:
            try:
                effective_tenant = None if tenant in ("_default", "single-tenant") else tenant
                result = await tempo_service.get_tenant_overrides(
                    backend_id=backend_id,
                    tenant=effective_tenant,
                    scope="merged",
                )
                return json.dumps(result, indent=2)
            except Exception as e:
                raise TempoResourceError(
                    f"Failed to fetch overrides for tenant '{tenant}' on '{backend_id}': {e}"
                ) from e

        @mcp_instance.resource(
            "tempo://traces/{backend_id}/{trace_id}",
            name="tempo_trace_resource",
            description="Compact trace summary and bounded spans for a trace ID",
            mime_type="application/json",
        )
        async def tempo_trace_resource(backend_id: str, trace_id: str) -> str:
            try:
                raw = await tempo_service.get_trace(
                    backend_id=backend_id,
                    trace_id=trace_id,
                    llm_format=False,
                    max_spans=100,
                )
                trace_data = raw.get("trace", {})
                summary = summarize_trace(trace_id, trace_data)
                payload = {
                    "backend_id": backend_id,
                    "trace_id": trace_id,
                    "summary": summary.model_dump(),
                    "trace": trace_data,
                    "truncated": raw.get("truncated", False),
                }
                return json.dumps(payload, indent=2)
            except Exception as e:
                raise TempoResourceError(
                    f"Failed to read trace '{trace_id}' on '{backend_id}': {e}"
                ) from e
