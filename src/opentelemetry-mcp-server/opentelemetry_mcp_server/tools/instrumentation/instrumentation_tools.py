"""OpenTelemetry instrumentation and operator tools.

Provides tools for looking up language instrumentation support,
creating/patching Instrumentation CRDs, and annotating deployments
for auto-instrumentation.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.types import ToolAnnotations
from fastmcp import Context
from pydantic import Field

from opentelemetry_mcp_server.exceptions import OtelOperationError, OtelValidationError
from opentelemetry_mcp_server.tools.base import BaseTool


def _load_lang_registry() -> Dict[str, Any]:
    """Load language registry from static JSON or env override."""
    import os

    override = os.getenv("OTEL_LANG_REGISTRY_PATH")
    if override:
        path = Path(override)
    else:
        path = Path(__file__).parent.parent.parent / "static" / "otel_lang_registry.json"

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"languages": {}}


class InstrumentationTools(BaseTool):
    """Instrumentation lookup and management tools."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        kubernetes_service = self.kubernetes_service

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Lookup Instrumentation for Library",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            )
        )
        async def otel_lookup_instrumentation(
            language: str = Field(
                ...,
                min_length=1,
                description="Language identifier (java, python, nodejs, dotnet, go, rust)",
            ),
            framework: Optional[str] = Field(
                default=None,
                description="Framework or library name to look up (e.g., 'Spring Boot', 'FastAPI')",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Map a language and optional framework to OTel instrumentation support.

            Use this to check whether auto-instrumentation is available for a
            specific language/framework before onboarding a service. Read-only,
            no external calls.

            Returns:
            - {"language": str, "auto_instrumentation_available": bool, "frameworks": [...], "annotation_key": str}

            When NOT to use: For listing all languages, use the
            otel://registry/languages resource.

            Common errors:
            - Unknown language: Supported values are java, python, nodejs, dotnet, go, rust.
            """
            registry = _load_lang_registry()
            languages = registry.get("languages", {})

            lang_key = language.lower().strip()
            lang_data = languages.get(lang_key)

            if not lang_data:
                return {
                    "language": language,
                    "found": False,
                    "supported_languages": list(languages.keys()),
                    "error": f"Language '{language}' not found in registry",
                }

            result = {
                "language": lang_key,
                "found": True,
                "display_name": lang_data.get("display_name", language),
                "signal_support": lang_data.get("signal_support", {}),
                "auto_instrumentation_available": lang_data.get(
                    "auto_instrumentation_available", False
                ),
                "auto_instrumentation_image": lang_data.get(
                    "auto_instrumentation_image"
                ),
                "ebpf_supported": lang_data.get("ebpf_supported", False),
                "annotation_key": lang_data.get("annotation_key"),
                "sdk_package": lang_data.get("sdk_package"),
            }

            frameworks_data = lang_data.get("frameworks", [])
            if framework:
                # Filter to matching framework
                fw_lower = framework.lower()
                matched = [
                    f
                    for f in frameworks_data
                    if fw_lower in f.get("name", "").lower()
                ]
                result["frameworks"] = matched
                result["framework_query"] = framework
                if not matched:
                    result["framework_hint"] = (
                        f"No exact match for '{framework}'. "
                        f"Available: {[f['name'] for f in frameworks_data]}"
                    )
            else:
                result["frameworks"] = frameworks_data

            return result

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Create or Patch Instrumentation Profile",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def otel_patch_instrumentation(
            namespace: str = Field(
                ..., min_length=1, description="Target namespace"
            ),
            name: str = Field(
                ..., min_length=1, description="Instrumentation CR name"
            ),
            endpoint: str = Field(
                default="http://otel-collector:4318",
                description=(
                    "OTLP exporter endpoint for auto-instrumentation SDKs. "
                    "Port 4318 = OTLP HTTP (default for Python, Node.js, .NET); "
                    "Port 4317 = OTLP gRPC (default for Java, Go). "
                    "Use the port matching your SDK's default protocol."
                ),
            ),
            propagators: List[str] = Field(
                default=["tracecontext", "baggage"],
                description="Context propagation formats",
            ),
            sampler_type: Optional[str] = Field(
                default=None,
                description="Sampler type (e.g., 'parentbased_traceidratio')",
            ),
            sampler_argument: Optional[str] = Field(
                default=None,
                description="Sampler argument (e.g., '0.25' for 25%)",
            ),
            languages: Optional[List[str]] = Field(
                default=None,
                description="Languages to configure (java, python, nodejs, dotnet, go)",
            ),
            overwrite: bool = Field(
                default=False,
                description="If True, replaces existing CR entirely",
            ),
            dry_run: bool = Field(
                default=True,
                description="If True, validates without applying. Set to False only after review.",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Create or patch an Instrumentation CRD for auto-instrumentation.

            Use this to configure auto-instrumentation for workloads in a
            namespace. Generates the Instrumentation CR spec and applies it.

            **WARNING: With dry_run=False, this creates or modifies a
            Kubernetes CRD that controls auto-instrumentation injection.**

            Returns:
            - {"action": "create"|"patch", "instrumentation": {...}, "dry_run": bool, "spec_yaml": str}

            When NOT to use: For annotating individual deployments, use
            otel_annotate_deployment instead.

            Common errors:
            - RBAC denied: Ensure service account has CRD write permissions.
            - Invalid sampler: Use 'always_on', 'always_off', or 'parentbased_traceidratio'.
            """
            try:
                # Build the spec
                spec: Dict[str, Any] = {
                    "exporter": {
                        "endpoint": endpoint,
                    },
                    "propagators": propagators,
                }

                if sampler_type:
                    spec["sampler"] = {"type": sampler_type}
                    if sampler_argument:
                        spec["sampler"]["argument"] = sampler_argument

                # Add per-language configs
                if languages:
                    registry = _load_lang_registry()
                    lang_registry = registry.get("languages", {})
                    for lang in languages:
                        lang_data = lang_registry.get(lang.lower(), {})
                        if lang_data and lang_data.get("auto_instrumentation_available"):
                            image = lang_data.get("auto_instrumentation_image")
                            if image:
                                spec[lang.lower()] = {"image": image}

                from opentelemetry_mcp_server.utils.yaml_helpers import config_to_yaml

                if dry_run:
                    return {
                        "action": "dry_run",
                        "dry_run": True,
                        "namespace": namespace,
                        "name": name,
                        "spec": spec,
                        "spec_yaml": config_to_yaml(spec),
                        "message": "Dry run — no changes applied. Set dry_run=False to apply.",
                    }

                result = await kubernetes_service.create_or_patch_instrumentation(
                    namespace=namespace,
                    name=name,
                    spec=spec,
                    overwrite=overwrite,
                )

                return {
                    "action": "applied",
                    "dry_run": False,
                    "namespace": namespace,
                    "name": name,
                    "spec": spec,
                    "result": result,
                }
            except Exception as e:
                raise OtelOperationError(
                    f"Failed to create/patch instrumentation: {e}"
                )

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Annotate Deployment for Auto-Instrumentation",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def otel_annotate_deployment(
            namespace: str = Field(
                ..., min_length=1, description="Deployment namespace"
            ),
            name: str = Field(
                ..., min_length=1, description="Deployment name"
            ),
            language: str = Field(
                ...,
                min_length=1,
                description="Language to enable (java, python, nodejs, dotnet, go)",
            ),
            instrumentation_cr_name: Optional[str] = Field(
                default=None,
                description="Specific Instrumentation CR name (defaults to 'true' for namespace default)",
            ),
            strip_conflicting_env_vars: bool = Field(
                default=False,
                description=(
                    "If True, automatically removes conflicting OTEL_* env vars "
                    "(e.g., OTEL_EXPORTER_OTLP_ENDPOINT) from the deployment before "
                    "annotating. These hardcoded vars take precedence over Operator-"
                    "injected values and silently break auto-instrumentation."
                ),
            ),
            dry_run: bool = Field(
                default=True,
                description="If True, previews the annotation patch. Set False only after review.",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Apply auto-instrumentation annotation to a Deployment's pod template.

            Use this to enable OTel auto-instrumentation for a specific
            workload. The OTel Operator watches for these annotations and
            injects the appropriate init container.

            **WARNING: With dry_run=False, this modifies the Deployment's
            pod template, triggering a rolling restart.**

            Returns:
            - {"deployment": str, "annotation": {"key": str, "value": str}, "dry_run": bool}

            When NOT to use: For creating the Instrumentation CR itself,
            use otel_patch_instrumentation.

            Prerequisites: An Instrumentation CR must exist in the namespace.

            Common errors:
            - Deployment not found: Verify name and namespace.
            - No effect: Ensure the OTel Operator is installed and watching the namespace.
            """
            try:
                from opentelemetry_mcp_server.utils.k8s_labels import (
                    LANGUAGE_ANNOTATION_KEYS,
                )

                lang_key = language.lower().strip()
                annotation_key = LANGUAGE_ANNOTATION_KEYS.get(lang_key)
                if not annotation_key:
                    raise OtelValidationError(
                        f"Unsupported language: '{language}'. "
                        f"Supported: {list(LANGUAGE_ANNOTATION_KEYS.keys())}"
                    )

                annotation_value = instrumentation_cr_name or "true"
                annotations = {annotation_key: annotation_value}

                # ── Check for conflicting hardcoded env vars ──
                # (Note-003: OTel Demo apps hardcode OTEL_* env vars
                # which take precedence over Operator-injected ones)
                env_override_warnings: List[str] = []
                _CONFLICT_ENV_VARS = [
                    "OTEL_EXPORTER_OTLP_ENDPOINT",
                    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
                    "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
                    "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT",
                    "OTEL_COLLECTOR_NAME",
                ]
                try:
                    dep = await kubernetes_service.get_deployment(
                        namespace=namespace, name=name
                    )
                    for c in dep.get("containers", []):
                        if c.get("is_init_container"):
                            continue
                        env = c.get("env", {})
                        for env_name in _CONFLICT_ENV_VARS:
                            if env_name in env:
                                env_override_warnings.append(
                                    f"⚠️ Container '{c['name']}' has "
                                    f"hardcoded '{env_name}={env[env_name]}'. "
                                    f"This takes precedence over the OTel "
                                    f"Operator's injected value and will "
                                    f"prevent auto-instrumentation from "
                                    f"routing to the intended collector."
                                )
                except Exception:
                    # Non-blocking — don't fail the annotation
                    # if we can't read the deployment
                    pass

                if env_override_warnings:
                    env_override_warnings.append(
                        "💡 Fix: Remove the hardcoded OTEL_* env vars "
                        f"from the '{name}' Deployment spec so the OTel "
                        "Operator can inject the correct endpoints. "
                        "Example: kubectl set env deployment/"
                        f"{name} -n {namespace} "
                        "OTEL_EXPORTER_OTLP_ENDPOINT-"
                    )

                # Strip conflicting env vars if requested
                env_strip_result = None
                if strip_conflicting_env_vars and env_override_warnings:
                    env_strip_result = await kubernetes_service.strip_otel_env_vars(
                        namespace=namespace,
                        deployment_name=name,
                        dry_run=dry_run,
                    )

                if dry_run:
                    result_dict: Dict[str, Any] = {
                        "action": "dry_run",
                        "dry_run": True,
                        "deployment": f"{namespace}/{name}",
                        "annotation": {
                            "key": annotation_key,
                            "value": annotation_value,
                        },
                        "message": (
                            f"Would add annotation '{annotation_key}={annotation_value}' "
                            f"to pod template of Deployment '{name}'. "
                            "This will trigger a rolling restart. "
                            "Set dry_run=False to apply."
                        ),
                    }
                    if env_override_warnings:
                        result_dict["warnings"] = env_override_warnings
                    if env_strip_result:
                        result_dict["env_var_remediation"] = env_strip_result
                    return result_dict

                result = await kubernetes_service.patch_deployment_annotations(
                    namespace=namespace,
                    name=name,
                    annotations=annotations,
                    dry_run=False,
                )

                result_dict: Dict[str, Any] = {
                    "action": "applied",
                    "dry_run": False,
                    "deployment": f"{namespace}/{name}",
                    "annotation": {
                        "key": annotation_key,
                        "value": annotation_value,
                    },
                    "result": {
                        "name": result.get("name"),
                        "namespace": result.get("namespace"),
                    },
                }
                if env_override_warnings:
                    result_dict["warnings"] = env_override_warnings
                if env_strip_result:
                    result_dict["env_var_remediation"] = env_strip_result
                return result_dict
            except OtelValidationError:
                raise
            except Exception as e:
                raise OtelOperationError(
                    f"Failed to annotate deployment: {e}"
                )
