"""Backend diagnostics and Loki Ruler alerting/recording rule tools.

Tools:
- loki_get_diagnostics (`diagnostics` toolset, read-only)
- loki_upsert_rule_group (`rules` toolset, write-gated, dry_run=True default + elicitation)
- loki_delete_rule_group (`rules` toolset, write/destructive-gated, dry_run=True default + elicitation)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field
import yaml

from loki_mcp_server.exceptions import LokiValidationError
from loki_mcp_server.tools.base import BaseTool
from loki_mcp_server.utils.elicitation import (
    compute_unified_diff,
    confirm_mutation_or_elicit,
)
from loki_mcp_server.utils.error_handling import tool_error_boundary
from loki_mcp_server.utils.logql_helpers import (
    detect_high_cardinality_in_selector,
    validate_stream_selector,
)


def _validate_rule_group_yaml(
    rules_yaml: str,
    expected_group_name: str,
) -> tuple[Dict[str, Any], List[str]]:
    """Validate Loki Ruler rule group YAML structure and LogQL hygiene."""
    if not rules_yaml or not rules_yaml.strip():
        raise LokiValidationError("rules_yaml must not be empty.")
    try:
        doc = yaml.safe_load(rules_yaml)
    except Exception as exc:
        raise LokiValidationError(f"Invalid YAML in rules_yaml: {exc}") from exc

    if not isinstance(doc, dict):
        raise LokiValidationError("rules_yaml must be a YAML mapping representing a rule group.")

    # Unwrap if user passed {"groups": [{...}]}
    if "groups" in doc and isinstance(doc["groups"], list) and len(doc["groups"]) == 1:
        doc = doc["groups"][0]

    name = str(doc.get("name") or expected_group_name).strip()
    if not name:
        raise LokiValidationError("Rule group must specify a 'name'.")
    doc["name"] = name

    rules = doc.get("rules")
    if not isinstance(rules, list) or not rules:
        raise LokiValidationError("Rule group must contain a non-empty 'rules' list.")

    warnings: List[str] = []
    for idx, rule in enumerate(rules):
        if not isinstance(rule, dict):
            raise LokiValidationError(f"Rule #{idx + 1} must be a mapping.")
        has_alert = bool(rule.get("alert"))
        has_record = bool(rule.get("record"))
        if has_alert == has_record:
            raise LokiValidationError(
                f"Rule #{idx + 1} must define exactly one of 'alert' or 'record'."
            )
        expr = str(rule.get("expr", "")).strip()
        if not expr:
            raise LokiValidationError(f"Rule #{idx + 1} is missing required 'expr' LogQL expression.")

        validate_stream_selector(expr)
        hc = detect_high_cardinality_in_selector(expr)
        if hc:
            warnings.append(
                f"Rule '{rule.get('alert') or rule.get('record')}' contains high-cardinality "
                f"label(s) {hc} inside '{{}}'. Move to structured metadata or line filters."
            )
        if "unwrap" in expr and "__error__" not in expr:
            warnings.append(
                f"Rule '{rule.get('alert') or rule.get('record')}' uses '| unwrap' without "
                "'| __error__=\"\"'. Add '| __error__=\"\"' to avoid sample conversion errors."
            )
        if has_alert and not rule.get("for"):
            warnings.append(
                f"Alert '{rule['alert']}' omits 'for:' duration; consider 'for: 5m' to prevent flapping."
            )

    return doc, warnings


class RulesAndDiagnosticsTools(BaseTool):
    """Diagnostics (`diagnostics`) and Loki Ruler (`rules`) tools."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        loki = self.loki_service
        config = self.config

        # ──────────────────────────────────────────
        # Tool 14: loki_get_diagnostics (Read-Only)
        # ──────────────────────────────────────────
        if config.should_register("diagnostics", is_write=False):

            @mcp_instance.tool(
                annotations=ToolAnnotations(
                    title="Get Loki Backend & Ingestion Diagnostics",
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=True,
                ),
                output_schema=None,
            )
            @tool_error_boundary
            async def loki_get_diagnostics(
                include_metrics: bool = Field(
                    default=True,
                    description="Scrape /metrics for loki_discarded_samples_total and ingester chunk counts",
                ),
                selector: Optional[str] = Field(
                    default=None,
                    description="Optional stream selector to check recent 1h index stats for (e.g., '{app=\"checkout\"}')",
                ),
                org_id: Optional[str] = Field(
                    default=None,
                    description="Optional tenant ID (X-Scope-OrgID)",
                ),
                ctx: Context = None,  # type: ignore[assignment]
            ) -> Dict[str, Any]:
                """Diagnose Loki backend readiness, build version, and discarded log sample reasons.

                Inspects `/ready`, `/loki/api/v1/status/buildinfo`, and `/metrics`
                (`loki_discarded_samples_total` by `reason`) to identify rate limiting,
                stream cardinality limits, or out-of-order/too-old log drops. Read-only.
                """
                if ctx:
                    await ctx.info("Running Loki backend and ingestion diagnostics...")

                health = await loki.health_check()
                build_info = await loki.get_build_info()
                runtime_cfg = await loki.get_runtime_config()
                metrics_diag: Dict[str, Any] = {}
                if include_metrics:
                    metrics_diag = await loki.get_discarded_samples_diagnostics()

                selector_stats: Optional[Dict[str, Any]] = None
                if selector:
                    clean_sel = validate_stream_selector(selector)
                    try:
                        selector_stats = await loki.get_index_stats(
                            query=clean_sel, org_id=org_id
                        )
                    except Exception:
                        selector_stats = None

                findings: List[Dict[str, str]] = []
                discarded = metrics_diag.get("discarded_samples_by_reason", {})
                for reason, count in discarded.items():
                    if count > 0:
                        findings.append(
                            {
                                "code": f"LOKI_DISCARDED_{reason.upper()}",
                                "reason": reason,
                                "count": str(int(count)),
                                "remediation": (
                                    "Increase ingestion_rate_mb / ingestion_burst_size_mb or per_stream_rate_limit in limits_config, or split monolithic streams by service_name"
                                    if "rate_limit" in reason
                                    else "Reduce label cardinality or move dynamic fields (pod, trace_id, ip) to structured_metadata"
                                    if "label" in reason or "stream" in reason
                                    else "Enable limits_config.max_line_size_truncate: true or truncate oversized lines in collector"
                                    if "line_too_long" in reason
                                    else "Check NTP clock skew, rewrite archival replay timestamps in collector, or tune limits_config.reject_old_samples_max_age (default 168h)"
                                    if "age" in reason or "old" in reason or "order" in reason
                                    else "Inspect Alloy/OTel Collector timestamp parsing or limits_config thresholds"
                                ),
                            }
                        )

                comp_cfg = runtime_cfg.get("compactor") if isinstance(runtime_cfg, dict) else None
                if isinstance(comp_cfg, dict) and not comp_cfg.get("compactor_delete_ready"):
                    findings.append(
                        {
                            "code": "LOKI_COMPACTOR_DELETE_DISABLED",
                            "reason": "compactor_delete_not_configured",
                            "count": "1",
                            "remediation": (
                                "Set compactor.retention_enabled: true and compactor.delete_request_store "
                                "(filesystem/s3/gcs/azure) to enable /loki/api/v1/delete requests."
                            ),
                        }
                    )

                return {
                    "health": health,
                    "build_info": build_info,
                    "runtime_config": runtime_cfg,
                    "ingestion_metrics": metrics_diag,
                    "selector_index_stats": selector_stats,
                    "diagnostic_findings": findings,
                }

        # ──────────────────────────────────────────
        # Tool 15 & 16: Loki Ruler Tools (Write-Gated)
        # ──────────────────────────────────────────
        if config.should_register("rules", is_write=True):

            @mcp_instance.tool(
                annotations=ToolAnnotations(
                    title="Upsert Loki Ruler Rule Group",
                    readOnlyHint=False,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=True,
                ),
                output_schema=None,
            )
            @tool_error_boundary
            async def loki_upsert_rule_group(
                namespace: str = Field(
                    ...,
                    min_length=1,
                    description="Loki Ruler namespace for the rule group (e.g., 'production')",
                ),
                group_name: str = Field(
                    ...,
                    min_length=1,
                    description="Rule group name (e.g., 'checkout-log-alerts')",
                ),
                rules_yaml: str = Field(
                    ...,
                    min_length=1,
                    description="YAML definition of the Loki alerting/recording rule group",
                ),
                dry_run: bool = Field(
                    default=True,
                    description="Preview validation and unified YAML diff without mutating Loki Ruler (default: True)",
                ),
                confirm: bool = Field(
                    default=False,
                    description="Confirm mutation when dry_run=False (or approve via interactive MCP elicitation)",
                ),
                org_id: Optional[str] = Field(
                    default=None,
                    description="Optional tenant ID (X-Scope-OrgID)",
                ),
                ctx: Context = None,  # type: ignore[assignment]
            ) -> Dict[str, Any]:
                """Validate, preview (`dry_run=True`), or upsert a Loki Ruler alerting/recording rule group.

                Validates LogQL expressions, checks for high-cardinality selectors and
                missing `| __error__=""` guards, computes a unified diff against the
                existing rule group, and applies via `POST /loki/api/v1/rules/{namespace}`
                only after `dry_run=False` and operator confirmation.
                """
                normalized_group, warnings = _validate_rule_group_yaml(
                    rules_yaml=rules_yaml,
                    expected_group_name=group_name,
                )
                canonical_yaml = yaml.safe_dump(normalized_group, sort_keys=False)

                existing_rules = await loki.get_rules(
                    namespace=namespace, group_name=group_name, org_id=org_id
                )
                before_yaml = (
                    yaml.safe_dump(existing_rules, sort_keys=False)
                    if existing_rules
                    else ""
                )
                diff = compute_unified_diff(
                    before_yaml,
                    canonical_yaml,
                    fromfile=f"live/rules/{namespace}/{group_name}",
                    tofile=f"desired/rules/{namespace}/{group_name}",
                )

                if dry_run:
                    return {
                        "status": "dry_run_preview",
                        "dry_run": True,
                        "namespace": namespace,
                        "group_name": normalized_group["name"],
                        "rule_count": len(normalized_group.get("rules", [])),
                        "warnings": warnings,
                        "diff": diff,
                        "next_step": (
                            "Review the diff and warnings. To apply, call loki_upsert_rule_group "
                            "with dry_run=False and confirm=True."
                        ),
                    }

                approved, reason = await confirm_mutation_or_elicit(
                    ctx,
                    confirm=confirm,
                    prompt_message=(
                        f"Apply Loki Ruler rule group '{normalized_group['name']}' "
                        f"in namespace '{namespace}' ({len(normalized_group.get('rules', []))} rules)?"
                    ),
                )
                if not approved:
                    return {
                        "status": "confirmation_required",
                        "dry_run": False,
                        "approved": False,
                        "reason": reason,
                        "namespace": namespace,
                        "group_name": normalized_group["name"],
                        "diff": diff,
                    }

                res = await loki.upsert_rule_group(
                    namespace=namespace,
                    rules_yaml=canonical_yaml,
                    org_id=org_id,
                )
                return {
                    **res,
                    "dry_run": False,
                    "group_name": normalized_group["name"],
                    "rule_count": len(normalized_group.get("rules", [])),
                    "warnings": warnings,
                    "diff": diff,
                }

            @mcp_instance.tool(
                annotations=ToolAnnotations(
                    title="Delete Loki Ruler Rule Group",
                    readOnlyHint=False,
                    destructiveHint=True,
                    idempotentHint=True,
                    openWorldHint=True,
                ),
                output_schema=None,
            )
            @tool_error_boundary
            async def loki_delete_rule_group(
                namespace: str = Field(
                    ...,
                    min_length=1,
                    description="Loki Ruler namespace containing the rule group",
                ),
                group_name: str = Field(
                    ...,
                    min_length=1,
                    description="Name of the rule group to delete",
                ),
                dry_run: bool = Field(
                    default=True,
                    description="Preview deletion without mutating Loki Ruler (default: True)",
                ),
                confirm: bool = Field(
                    default=False,
                    description="Confirm destructive deletion when dry_run=False",
                ),
                org_id: Optional[str] = Field(
                    default=None,
                    description="Optional tenant ID (X-Scope-OrgID)",
                ),
                ctx: Context = None,  # type: ignore[assignment]
            ) -> Dict[str, Any]:
                """Preview (`dry_run=True`) or delete a Loki Ruler rule group after confirmation."""
                existing = await loki.get_rules(
                    namespace=namespace, group_name=group_name, org_id=org_id
                )
                if dry_run:
                    return {
                        "status": "dry_run_preview",
                        "dry_run": True,
                        "action": "delete_rule_group",
                        "namespace": namespace,
                        "group_name": group_name,
                        "existing_group": existing,
                        "next_step": (
                            "Call loki_delete_rule_group with dry_run=False and confirm=True "
                            "to permanently delete this rule group."
                        ),
                    }

                approved, reason = await confirm_mutation_or_elicit(
                    ctx,
                    confirm=confirm,
                    prompt_message=(
                        f"Permanently delete Loki Ruler rule group '{group_name}' "
                        f"in namespace '{namespace}'?"
                    ),
                )
                if not approved:
                    return {
                        "status": "confirmation_required",
                        "dry_run": False,
                        "approved": False,
                        "reason": reason,
                        "namespace": namespace,
                        "group_name": group_name,
                    }

                res = await loki.delete_rule_group(
                    namespace=namespace,
                    group_name=group_name,
                    org_id=org_id,
                )
                return {
                    **res,
                    "dry_run": False,
                }
