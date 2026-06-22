"""Log transform and PII masking tool.

Generates OTTL (OpenTelemetry Transformation Language) statements
for the ``transform`` processor to parse JSON logs and mask PII
(Personally Identifiable Information) before export.
"""

from typing import Any, Dict, List, Optional

from mcp.types import ToolAnnotations
from fastmcp import Context
from pydantic import Field

from opentelemetry_mcp_server.exceptions import OtelOperationError
from opentelemetry_mcp_server.tools.base import BaseTool


# ──────────────────────────────────────────────
# Curated PII regex pattern registry
# ──────────────────────────────────────────────

# Each entry: (pattern_name, description, regex, replacement)
_PII_PATTERNS: Dict[str, Dict[str, str]] = {
    "ssn": {
        "description": "US Social Security Number (XXX-XX-XXXX)",
        "regex": r"\\d{3}-\\d{2}-\\d{4}",
        "replacement": "***-**-****",
    },
    "credit_card": {
        "description": "Credit card number (16 digits with optional separators)",
        "regex": r"\\d{4}[\\s-]?\\d{4}[\\s-]?\\d{4}[\\s-]?\\d{4}",
        "replacement": "****-****-****-****",
    },
    "email": {
        "description": "Email address",
        "regex": r"[a-zA-Z0-9._%+\\-]+@[a-zA-Z0-9.\\-]+\\.[a-zA-Z]{2,}",
        "replacement": "[REDACTED_EMAIL]",
    },
    "ipv4": {
        "description": "IPv4 address",
        "regex": r"\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}",
        "replacement": "[REDACTED_IP]",
    },
    "phone_us": {
        "description": "US phone number (+1-XXX-XXX-XXXX or similar)",
        "regex": r"\\+?1?[\\s.-]?\\(?\\d{3}\\)?[\\s.-]?\\d{3}[\\s.-]?\\d{4}",
        "replacement": "[REDACTED_PHONE]",
    },
    "jwt": {
        "description": "JSON Web Token (eyJ... pattern)",
        "regex": r"eyJ[A-Za-z0-9_-]+\\.eyJ[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+",
        "replacement": "[REDACTED_JWT]",
    },
    "bearer_token": {
        "description": "Bearer auth token in headers",
        "regex": r"Bearer\\s+[A-Za-z0-9._~+/=-]+",
        "replacement": "Bearer [REDACTED]",
    },
}


def generate_log_transform_config(
    mask_patterns: Optional[List[str]] = None,
    parse_json: bool = True,
    extract_fields: Optional[List[str]] = None,
    custom_mask_rules: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """Generate a transform processor config for log processing.

    Creates OTTL ``log_statements`` for JSON parsing and PII masking.
    Uses ``error_mode: ignore`` so non-JSON lines don't crash the pipeline.

    Args:
        mask_patterns: Names from the PII pattern registry
            (e.g., ``["ssn", "credit_card", "email"]``).
        parse_json: If True, adds ``ParseJSON(body)`` statements.
        extract_fields: Field names to promote from parsed JSON body
            to log attributes (e.g., ``["user_id", "request_id"]``).
        custom_mask_rules: Custom masking rules as
            ``[{"field": str, "regex": str, "replacement": str}]``.

    Returns:
        Complete transform processor config dict.
    """
    statements: List[str] = []

    # Phase 1: JSON parsing
    if parse_json:
        # Parse body to cache, guarded by JSON check
        statements.append(
            'merge_maps(cache, ParseJSON(body), "upsert") '
            'where IsMatch(body, "^\\\\{")'
        )

        # Extract specific fields to attributes
        if extract_fields:
            for field_name in extract_fields:
                safe_attr = field_name.replace(".", "_")
                statements.append(
                    f'set(attributes["{safe_attr}"], cache["{field_name}"]) '
                    f'where cache["{field_name}"] != nil'
                )

        # Set structured body back
        statements.append(
            'set(body, cache) where cache != nil'
        )

    # Phase 2: PII masking from registry
    if mask_patterns:
        for pattern_name in mask_patterns:
            pattern = _PII_PATTERNS.get(pattern_name)
            if not pattern:
                continue

            # Apply to body (as string)
            statements.append(
                f'replace_pattern(body, "{pattern["regex"]}", '
                f'"{pattern["replacement"]}") '
                f'where IsString(body)'
            )

    # Phase 3: Custom masking rules
    if custom_mask_rules:
        for rule in custom_mask_rules:
            target = rule.get("field", "body")
            regex = rule.get("regex", "")
            replacement = rule.get("replacement", "[REDACTED]")
            if not regex:
                continue

            if target == "body":
                statements.append(
                    f'replace_pattern(body, "{regex}", "{replacement}") '
                    'where IsString(body)'
                )
            else:
                statements.append(
                    f'replace_pattern(attributes["{target}"], '
                    f'"{regex}", "{replacement}") '
                    f'where attributes["{target}"] != nil'
                )

    if not statements:
        return {}

    config = {
        "processors": {
            "transform/log_processing": {
                "error_mode": "ignore",
                "log_statements": [
                    {
                        "context": "log",
                        "statements": statements,
                    }
                ],
            }
        }
    }

    return config


class LogTransformTools(BaseTool):
    """Log transform and PII masking tools."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        kubernetes_service = self.kubernetes_service
        collector_config_service = self.collector_config_service

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Generate Log Transform",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def otel_generate_log_transform(
            namespace: str = Field(
                ..., min_length=1, description="Collector namespace"
            ),
            collector_name: str = Field(
                ..., min_length=1, description="Collector CRD name"
            ),
            parse_json: bool = Field(
                default=True,
                description=(
                    "Parse JSON log bodies into structured maps "
                    "using OTTL ParseJSON()"
                ),
            ),
            mask_patterns: Optional[List[str]] = Field(
                default=None,
                description=(
                    "PII patterns to mask. Available: "
                    "ssn, credit_card, email, ipv4, phone_us, jwt, bearer_token"
                ),
            ),
            extract_fields: Optional[List[str]] = Field(
                default=None,
                description=(
                    "Fields to extract from JSON body into log attributes "
                    "(e.g., ['user_id', 'request_id', 'trace_id'])"
                ),
            ),
            target_pipeline: str = Field(
                default="logs",
                description="Pipeline to add the transform processor to",
            ),
            dry_run: bool = Field(
                default=True,
                description=(
                    "If True, returns the OTTL config snippet for review. "
                    "Set False to apply it to the collector."
                ),
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Generate OTTL transform statements for log parsing and PII masking.

            Use this to add structured JSON log parsing and/or PII
            redaction (SSN, credit card, email, etc.) to a collector's
            logs pipeline. Uses the OTel transform processor with OTTL.

            Returns:
            - dry_run=True: {"config_snippet": str, "patterns_applied": [...],
               "statements_count": int, ...}
            - dry_run=False: {"action": "applied", "changes": [...], ...}

            When NOT to use: For dropping specific metric attributes, use
            otel_gen_drop_attribute_rules. For sampling (trace reduction),
            use otel_toggle_sampling_strategy.

            Prerequisites: Collector must use the otel-contrib distribution
            (the transform processor is not in the core distribution).

            Common errors:
            - Unknown pattern: Use mask_patterns from the available list.
            - Transform processor not found: Ensure otel-contrib collector.
            """
            try:
                # Validate mask patterns
                if mask_patterns:
                    unknown = [
                        p for p in mask_patterns if p not in _PII_PATTERNS
                    ]
                    if unknown:
                        from opentelemetry_mcp_server.exceptions import (
                            OtelValidationError,
                        )
                        raise OtelValidationError(
                            f"Unknown PII patterns: {unknown}. "
                            f"Available: {list(_PII_PATTERNS.keys())}"
                        )

                config = generate_log_transform_config(
                    mask_patterns=mask_patterns,
                    parse_json=parse_json,
                    extract_fields=extract_fields,
                )

                if not config:
                    return {
                        "collector": f"{namespace}/{collector_name}",
                        "dry_run": dry_run,
                        "action": "no_change",
                        "message": (
                            "No transform rules generated. Specify "
                            "parse_json=True and/or mask_patterns."
                        ),
                    }

                from opentelemetry_mcp_server.utils.yaml_helpers import (
                    config_to_yaml,
                )

                config_snippet = config_to_yaml(config)
                patterns_applied = []
                if mask_patterns:
                    for p in mask_patterns:
                        if p in _PII_PATTERNS:
                            patterns_applied.append({
                                "name": p,
                                "description": _PII_PATTERNS[p]["description"],
                                "replacement": _PII_PATTERNS[p]["replacement"],
                            })

                statements = (
                    config["processors"]["transform/log_processing"]
                    ["log_statements"][0]["statements"]
                )

                if not dry_run:
                    from opentelemetry_mcp_server.utils.config_merger import (
                        merge_processor,
                    )

                    raw = await kubernetes_service.get_otel_collector(
                        namespace, collector_name
                    )
                    current_cfg = collector_config_service.parse_collector_config(
                        raw
                    )

                    merged_cfg, changes = merge_processor(
                        current_cfg,
                        "transform/log_processing",
                        config["processors"]["transform/log_processing"],
                        target_pipeline,
                        before="batch",
                    )

                    spec = dict(raw.get("spec", {}))
                    spec["config"] = merged_cfg

                    await kubernetes_service.create_or_patch_collector(
                        namespace=namespace,
                        name=collector_name,
                        spec=spec,
                        dry_run=False,
                    )

                    return {
                        "collector": f"{namespace}/{collector_name}",
                        "dry_run": False,
                        "action": "applied",
                        "changes": changes,
                        "patterns_applied": patterns_applied,
                        "statements_count": len(statements),
                        "message": (
                            "Log transform processor applied. "
                            "Monitor for parsing errors using "
                            "otel_verify_pipeline_health."
                        ),
                    }

                return {
                    "collector": f"{namespace}/{collector_name}",
                    "dry_run": True,
                    "action": "dry_run",
                    "config_snippet": config_snippet,
                    "patterns_applied": patterns_applied,
                    "statements_count": len(statements),
                    "parse_json_enabled": parse_json,
                    "extract_fields": extract_fields or [],
                    "message": (
                        "Review the OTTL config above. "
                        "Set dry_run=False to apply it to the collector."
                    ),
                }
            except OtelOperationError:
                raise
            except Exception as e:
                raise OtelOperationError(
                    f"Failed to generate log transform: {e}"
                )

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="List PII Patterns",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            )
        )
        async def otel_list_pii_patterns(
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """List available PII masking patterns for log transforms.

            Use this to discover which built-in PII patterns are available
            for otel_generate_log_transform's mask_patterns parameter.
            Read-only — returns the pattern registry.

            Returns:
            - {"patterns": [{"name": str, "description": str, "regex": str,
               "replacement": str}]}
            """
            patterns = []
            for name, info in _PII_PATTERNS.items():
                patterns.append({
                    "name": name,
                    "description": info["description"],
                    "regex": info["regex"],
                    "replacement": info["replacement"],
                })
            return {"patterns": patterns, "count": len(patterns)}
