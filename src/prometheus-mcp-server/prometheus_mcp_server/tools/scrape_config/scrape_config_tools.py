"""Scrape Configuration & Endpoint Verification MCP tools (`scrape` toolset)."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from prometheus_mcp_server.exceptions import (
    PrometheusOperationError,
    PrometheusValidationError,
)
from prometheus_mcp_server.tools.base import BaseTool
from prometheus_mcp_server.utils.endpoint_tester import test_metrics_endpoint
from prometheus_mcp_server.utils.param_coercion import JsonDict, JsonStrList

SCRAPE_KINDS = Literal[
    "ServiceMonitor", "PodMonitor", "Probe", "ScrapeConfig", "file_sd"
]


class ScrapeConfigTools(BaseTool):
    """Scrape target verification and Kubernetes / File SD scrape configuration tools (`scrape` toolset)."""

    def register(self, mcp_instance: Any) -> None:
        if self.should_register("scrape", is_write=False):
            self._register_read_tools(mcp_instance)
        if self.should_register("scrape", is_write=True):
            self._register_write_tools(mcp_instance)

    def _register_read_tools(self, mcp_instance: Any) -> None:
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Verify Metrics Endpoint & Prometheus Scrape Health",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def prom_verify_metrics_endpoint(
            backend_id: str = Field(
                ...,
                min_length=1,
                description="Prometheus backend ID (e.g. 'default')",
            ),
            endpoint_url: Optional[str] = Field(
                default=None,
                description="Optional direct HTTP /metrics URL to probe (e.g. 'http://my-svc:8080/metrics')",
            ),
            job_label: Optional[str] = Field(
                default=None,
                description="Optional Prometheus job label to verify `up{job=...} == 1` scrape health",
            ),
            expected_metrics: Optional[JsonStrList] = Field(
                default=None,
                description="Optional list of metric names expected to be present",
            ),
            verify_timeout: int = Field(
                default=15,
                ge=1,
                le=120,
                description="Seconds to poll Prometheus for `up == 1` target health (1-120)",
            ),
            ctx: Optional[Context] = None,
        ) -> Dict[str, Any]:
            """Verify a `/metrics` HTTP endpoint and/or poll Prometheus until `up{job=...} == 1.0`.

            Fixes the false-positive bug where `up == 0` was treated as healthy. Read-only.

            Returns:
            - {"healthy": bool, "endpoint_check": {...}, "scrape_up": bool, "up_instances": [...], "missing_metrics": [...]}
            """
            if not endpoint_url and not job_label:
                raise PrometheusValidationError(
                    "Provide at least one of 'endpoint_url' or 'job_label'."
                )

            endpoint_check: Optional[Dict[str, Any]] = None
            if endpoint_url:
                endpoint_check = await test_metrics_endpoint(endpoint_url)
                if (
                    not endpoint_check.get("ok", False)
                    and endpoint_check.get("status_code", 0) == 0
                    and self.kubernetes_service is not None
                    and hasattr(self.kubernetes_service, "probe_incluster_http")
                ):
                    try:
                        maybe_proxy = self.kubernetes_service.probe_incluster_http(
                            endpoint_url
                        )
                        if hasattr(maybe_proxy, "__await__"):
                            maybe_proxy = await maybe_proxy
                        if isinstance(maybe_proxy, dict):
                            endpoint_check = maybe_proxy
                    except Exception:
                        pass

            scrape_up = False
            up_instances: List[str] = []
            down_instances: List[str] = []

            if job_label:
                deadline = asyncio.get_event_loop().time() + max(1, verify_timeout)
                attempt = 0
                escaped_job = re.escape(job_label)
                while True:
                    attempt += 1
                    if ctx is not None and hasattr(ctx, "report_progress"):
                        try:
                            await ctx.report_progress(attempt, max(1, verify_timeout // 3))
                        except Exception:
                            pass
                    try:
                        res = await self.prometheus_service.instant_query(
                            backend_id, f'up{{job="{job_label}"}}'
                        )
                        if not res.result:
                            res = await self.prometheus_service.instant_query(
                                backend_id, f'up{{job=~".*{escaped_job}.*"}}'
                            )
                        base_job = re.sub(r"-(?:service)?monitor$", "", job_label)
                        if not res.result and base_job and base_job != job_label:
                            res = await self.prometheus_service.instant_query(
                                backend_id, f'up{{job=~".*{re.escape(base_job)}.*"}}'
                            )
                        up_instances.clear()
                        down_instances.clear()
                        for sample in res.result:
                            inst = sample.metric.get("instance", "unknown")
                            val = float(sample.value[1])
                            if val == 1.0:
                                up_instances.append(inst)
                            else:
                                down_instances.append(inst)
                        if up_instances and not down_instances:
                            scrape_up = True
                            break
                    except Exception:
                        pass

                    if asyncio.get_event_loop().time() >= deadline:
                        break
                    await asyncio.sleep(min(2.0, max(0.2, verify_timeout / 5.0)))

            missing_metrics: List[str] = []
            if expected_metrics:
                found_set = set(
                    (endpoint_check or {}).get("metrics_found", [])
                )
                escaped_job = re.escape(job_label) if job_label else ""
                for m in expected_metrics:
                    if m in found_set:
                        continue
                    if job_label:
                        try:
                            q_res = await self.prometheus_service.instant_query(
                                backend_id, f'count({m}{{job="{job_label}"}})'
                            )
                            if not q_res.result:
                                q_res = await self.prometheus_service.instant_query(
                                    backend_id, f'count({m}{{job=~".*{escaped_job}.*"}})'
                                )
                            if q_res.result and float(q_res.result[0].value[1]) > 0:
                                continue
                        except Exception:
                            pass
                    missing_metrics.append(m)

            healthy = True
            if endpoint_check is not None and not endpoint_check.get("ok", False):
                healthy = False
            if job_label and not scrape_up:
                healthy = False
            if missing_metrics:
                healthy = False

            return {
                "backend_id": backend_id,
                "healthy": healthy,
                "endpoint_check": endpoint_check,
                "scrape_up": scrape_up if job_label else None,
                "up_instances": up_instances,
                "down_instances": down_instances,
                "missing_metrics": missing_metrics,
            }

    def _register_write_tools(self, mcp_instance: Any) -> None:
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Apply Prometheus Scrape Configuration (CRD or File SD)",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def prom_apply_scrape_config(
            backend_id: str = Field(
                ...,
                min_length=1,
                description="Prometheus backend ID (e.g. 'default')",
            ),
            kind: SCRAPE_KINDS = Field(
                ...,
                description="Scrape resource kind: ServiceMonitor, PodMonitor, Probe, ScrapeConfig, or file_sd",
            ),
            name: str = Field(
                ...,
                min_length=1,
                description="Resource metadata name (or target group name for file_sd)",
            ),
            spec: JsonDict = Field(
                ...,
                description="CRD spec dictionary (or {'file_path': str, 'targets': [...], 'labels': {...}} for file_sd)",
            ),
            namespace: str = Field(
                default="monitoring",
                description="Kubernetes namespace for the scrape CRD",
            ),
            dry_run: bool = Field(
                default=True,
                description="When True (default), previews the manifest without mutating the cluster or filesystem",
            ),
            confirm: bool = Field(
                default=False,
                description="Set True to confirm live write when dry_run=False",
            ),
            ctx: Optional[Context] = None,
        ) -> Dict[str, Any]:
            """Create or update a `ServiceMonitor`, `PodMonitor`, `Probe`, `ScrapeConfig` CRD, or `file_sd` target group.

            **MUTATES STATE when `dry_run=False`.** Automatically injects required Prometheus Operator selector labels.

            Returns:
            - {"status": str, "dry_run": bool, "kind": str, "name": str, "manifest": {...}}
            """
            self.ensure_write_allowed(backend_id, "prom_apply_scrape_config")

            if kind == "file_sd":
                file_path = str(spec.get("file_path", "")).strip()
                targets = spec.get("targets", [])
                labels = spec.get("labels", {"job": name})
                trigger_reload = bool(spec.get("trigger_reload", True))
                if not file_path or not isinstance(targets, list) or not targets:
                    raise PrometheusValidationError(
                        "For kind='file_sd', spec must include 'file_path' and a non-empty 'targets' list."
                    )
                entry = {"targets": targets, "labels": labels}
                if not dry_run:
                    await self.confirm_or_elicit(
                        ctx,
                        confirm=confirm,
                        prompt_message=f"Write file_sd target group '{name}' ({len(targets)} targets) to '{file_path}'?",
                        backend_id=backend_id,
                        operation="prom_apply_scrape_config",
                        details={"kind": kind, "name": name, "file_path": file_path},
                    )
                    path_obj = Path(file_path)
                    path_obj.parent.mkdir(parents=True, exist_ok=True)
                    existing: List[Dict[str, Any]] = []
                    if path_obj.exists():
                        try:
                            existing = json.loads(path_obj.read_text(encoding="utf-8"))
                        except Exception:
                            existing = []
                    existing = [
                        g for g in existing if g.get("labels", {}).get("job") != labels.get("job")
                    ]
                    existing.append(entry)
                    path_obj.write_text(json.dumps(existing, indent=2), encoding="utf-8")
                    reloaded = (
                        await self.prometheus_service.reload_config(backend_id)
                        if trigger_reload
                        else False
                    )
                else:
                    reloaded = False

                self.record_audit(
                    backend_id=backend_id,
                    operation="prom_apply_scrape_config",
                    summary=f"{'Dry-run' if dry_run else 'Applied'} file_sd '{name}'",
                    outcome="dry_run" if dry_run else "succeeded",
                    details={"kind": "file_sd", "name": name, "file_path": file_path},
                )
                return {
                    "status": "dry_run_preview" if dry_run else "applied",
                    "dry_run": dry_run,
                    "kind": "file_sd",
                    "name": name,
                    "file_path": file_path,
                    "reload_triggered": reloaded,
                    "entry": entry,
                }

            if self.kubernetes_service is None:
                raise PrometheusOperationError(
                    "Kubernetes service is not configured (set K8S_ENABLED=true)."
                )

            api_version = (
                "monitoring.coreos.com/v1alpha1"
                if kind == "ScrapeConfig"
                else "monitoring.coreos.com/v1"
            )
            req_labels = (
                await self.kubernetes_service.get_probe_required_labels()
                if kind == "Probe"
                else await self.kubernetes_service.get_servicemonitor_required_labels()
            )
            meta_labels = {
                "app.kubernetes.io/name": name,
                "app.kubernetes.io/managed-by": "prometheus-mcp-server",
            }
            meta_labels.update(req_labels)
            if isinstance(spec.get("metadata_labels"), dict):
                meta_labels.update(spec["metadata_labels"])

            clean_spec = {k: v for k, v in spec.items() if k != "metadata_labels"}
            discovered_service: Optional[Dict[str, Any]] = None

            if kind == "ServiceMonitor":
                target_service = str(
                    clean_spec.pop("target_service", None)
                    or clean_spec.pop("service_name", None)
                    or ""
                ).strip()
                target_ns = str(clean_spec.pop("target_namespace", None) or namespace).strip()
                shorthand_port = clean_spec.pop("port", None)
                shorthand_path = clean_spec.pop("path", None)
                shorthand_interval = clean_spec.pop("interval", None)
                shorthand_match_labels = clean_spec.pop("match_labels", None)

                need_discovery = bool(target_service) or (
                    "selector" not in clean_spec and "endpoints" not in clean_spec
                )
                if need_discovery and hasattr(
                    self.kubernetes_service, "discover_service_details"
                ):
                    svc_lookup_name = target_service or name
                    try:
                        maybe_svc = self.kubernetes_service.discover_service_details(
                            target_ns, svc_lookup_name
                        )
                        if hasattr(maybe_svc, "__await__"):
                            maybe_svc = await maybe_svc
                        if isinstance(maybe_svc, dict):
                            discovered_service = maybe_svc
                    except Exception:
                        discovered_service = None

                if "selector" not in clean_spec:
                    if isinstance(shorthand_match_labels, dict) and shorthand_match_labels:
                        match_labels = dict(shorthand_match_labels)
                    elif discovered_service:
                        noisy_keys = {
                            "helm.sh/chart",
                            "app.kubernetes.io/version",
                            "app.kubernetes.io/managed-by",
                            "kubectl.kubernetes.io/last-applied-configuration",
                        }
                        raw_svc_labels = discovered_service.get("labels") or {}
                        filtered_labels = {
                            k: v for k, v in raw_svc_labels.items() if k not in noisy_keys
                        }
                        match_labels = (
                            filtered_labels
                            or discovered_service.get("selector")
                            or {"app.kubernetes.io/name": target_service or name}
                        )
                    else:
                        match_labels = {"app.kubernetes.io/name": target_service or name}
                    clean_spec["selector"] = {"matchLabels": match_labels}

                if "endpoints" not in clean_spec:
                    port_name = str(shorthand_port or "").strip()
                    if not port_name and discovered_service:
                        mp = discovered_service.get("metrics_port")
                        if isinstance(mp, dict) and mp.get("name"):
                            port_name = str(mp["name"])
                        elif discovered_service.get("ports"):
                            first_named = next(
                                (
                                    p.get("name")
                                    for p in discovered_service["ports"]
                                    if isinstance(p, dict) and p.get("name")
                                ),
                                None,
                            )
                            if first_named:
                                port_name = str(first_named)
                    if not port_name:
                        port_name = "metrics"

                    clean_spec["endpoints"] = [
                        {
                            "port": port_name,
                            "path": str(shorthand_path or "/metrics"),
                            "interval": str(shorthand_interval or "30s"),
                        }
                    ]

                if target_ns != namespace and "namespaceSelector" not in clean_spec:
                    clean_spec["namespaceSelector"] = {"matchNames": [target_ns]}

            manifest = {
                "apiVersion": api_version,
                "kind": kind,
                "metadata": {
                    "name": name,
                    "namespace": namespace,
                    "labels": meta_labels,
                },
                "spec": clean_spec,
            }

            if not dry_run:
                await self.confirm_or_elicit(
                    ctx,
                    confirm=confirm,
                    prompt_message=f"Apply {kind} '{namespace}/{name}' to Kubernetes?",
                    backend_id=backend_id,
                    operation="prom_apply_scrape_config",
                    details={"kind": kind, "name": name, "namespace": namespace},
                )
                await self.kubernetes_service.apply_custom_resource(namespace, manifest)

            self.record_audit(
                backend_id=backend_id,
                operation="prom_apply_scrape_config",
                summary=f"{'Dry-run' if dry_run else 'Applied'} {kind} '{namespace}/{name}'",
                outcome="dry_run" if dry_run else "succeeded",
                details={"kind": kind, "name": name, "namespace": namespace},
            )
            result_payload: Dict[str, Any] = {
                "status": "dry_run_preview" if dry_run else "applied",
                "dry_run": dry_run,
                "kind": kind,
                "name": name,
                "namespace": namespace,
                "manifest": manifest,
            }
            if discovered_service is not None:
                result_payload["discovered_service"] = discovered_service
            return result_payload

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Delete Prometheus Scrape Configuration",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def prom_delete_scrape_config(
            backend_id: str = Field(
                ...,
                min_length=1,
                description="Prometheus backend ID (e.g. 'default')",
            ),
            kind: SCRAPE_KINDS = Field(
                ...,
                description="Scrape resource kind: ServiceMonitor, PodMonitor, Probe, ScrapeConfig, or file_sd",
            ),
            name: str = Field(
                ...,
                min_length=1,
                description="Resource metadata name (or file path for file_sd)",
            ),
            namespace: str = Field(
                default="monitoring",
                description="Kubernetes namespace of the scrape CRD",
            ),
            dry_run: bool = Field(
                default=True,
                description="When True (default), previews deletion without mutating the cluster",
            ),
            confirm: bool = Field(
                default=False,
                description="Set True to confirm deletion when dry_run=False",
            ),
            ctx: Optional[Context] = None,
        ) -> Dict[str, Any]:
            """Delete a Kubernetes scrape CRD (`ServiceMonitor`, `PodMonitor`, `Probe`, `ScrapeConfig`) or `file_sd` file.

            **DESTRUCTIVE when `dry_run=False`.** Always preview with `dry_run=True` first.

            Returns:
            - {"status": str, "dry_run": bool, "kind": str, "name": str, "namespace": str}
            """
            self.ensure_write_allowed(backend_id, "prom_delete_scrape_config")

            if not dry_run:
                await self.confirm_or_elicit(
                    ctx,
                    confirm=confirm,
                    prompt_message=f"Delete {kind} '{namespace}/{name}'?",
                    backend_id=backend_id,
                    operation="prom_delete_scrape_config",
                    details={"kind": kind, "name": name, "namespace": namespace},
                )

            if kind == "file_sd":
                path_obj = Path(name)
                if not dry_run and path_obj.exists():
                    path_obj.unlink(missing_ok=True)
            else:
                if self.kubernetes_service is None:
                    raise PrometheusOperationError(
                        "Kubernetes service is not configured (set K8S_ENABLED=true)."
                    )
                if not dry_run:
                    group, version, plural = self.kubernetes_service._resolve_crd_coords(
                        kind
                    )
                    await self.kubernetes_service.delete_custom_resource(
                        namespace, group, version, plural, name
                    )

            self.record_audit(
                backend_id=backend_id,
                operation="prom_delete_scrape_config",
                summary=f"{'Dry-run delete' if dry_run else 'Deleted'} {kind} '{namespace}/{name}'",
                outcome="dry_run" if dry_run else "succeeded",
                details={"kind": kind, "name": name, "namespace": namespace},
            )
            return {
                "status": "dry_run_preview" if dry_run else "deleted",
                "dry_run": dry_run,
                "kind": kind,
                "name": name,
                "namespace": namespace,
            }
