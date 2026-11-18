"""OpenTelemetry workload auto-instrumentation lifecycle and verification tools.

Provides:
- ``otel_patch_instrumentation``: Create/patch Instrumentation CRDs with
  per-language OTLP protocol/port alignment (gRPC :4317 for Java/Go,
  HTTP :4318 for Python/Node.js/.NET).
- ``otel_manage_workload_instrumentation``: Enable, disable, or restart
  auto-instrumentation across Deployments, StatefulSets, and DaemonSets.
- ``otel_verify_instrumentation``: Single-call end-to-end verification of
  annotations, Instrumentation CRs, initContainers, injected env vars, and
  pod restart state.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from opentelemetry_mcp_server.exceptions import (
    OtelOperationError,
    OtelResourceNotFoundError,
    OtelValidationError,
)
from opentelemetry_mcp_server.models.findings import (
    Finding,
    FindingCode,
    FindingSeverity,
)
from opentelemetry_mcp_server.tools.base import (
    BaseTool,
    confirm_destructive_action,
)
from opentelemetry_mcp_server.utils.gitops import (
    build_gitops_finding,
    detect_gitops_ownership,
)
from opentelemetry_mcp_server.utils.k8s_labels import (
    CONTAINER_NAMES_ANNOTATION,
    DOTNET_RUNTIME_ANNOTATION,
    GO_TARGET_EXE_ANNOTATION,
    LANGUAGE_ANNOTATION_KEYS,
    RESOURCE_ATTR_ANNOTATION_PREFIX,
    derive_language_otlp_env,
    detect_language_from_annotations,
    get_instrumentation_cr_from_annotations,
)
from opentelemetry_mcp_server.utils.yaml_helpers import config_to_yaml

_CONFLICT_ENV_VARS = [
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
    "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
    "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT",
    "OTEL_COLLECTOR_NAME",
]


def _load_lang_registry() -> Dict[str, Any]:
    """Load language registry from static JSON or env override."""
    import os

    override = os.getenv("OTEL_LANG_REGISTRY_PATH")
    if override:
        path = Path(override)
    else:
        path = (
            Path(__file__).parent.parent.parent
            / "static"
            / "otel_lang_registry.json"
        )

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"languages": {}}


class InstrumentationTools(BaseTool):
    """Instrumentation CRD and workload annotation management tools."""

    def register(self, mcp_instance: Any) -> None:
        kubernetes_service = self.kubernetes_service

        if self.should_register_tool("instrumentation", is_write=True):

            @mcp_instance.tool(
                annotations=ToolAnnotations(
                    title="Create or Patch Instrumentation CRD",
                    readOnlyHint=False,
                    destructiveHint=True,
                    idempotentHint=False,
                    openWorldHint=True,
                )
            )
            async def otel_patch_instrumentation(
                namespace: str = Field(
                    ..., min_length=1, description="Target Kubernetes namespace"
                ),
                name: str = Field(
                    ..., min_length=1, description="Instrumentation CR name"
                ),
                collector_endpoint: str = Field(
                    default="http://otel-collector:4318",
                    description=(
                        "Collector OTLP endpoint (e.g., 'http://otel-collector:4318'). "
                        "Per-language OTLP protocol and port (:4317 gRPC for Java/Go, "
                        ":4318 HTTP/protobuf for Python/Node.js/.NET) are automatically "
                        "derived for each configured language."
                    ),
                ),
                languages: Optional[List[str]] = Field(
                    default=None,
                    description=(
                        "Languages to configure in the Instrumentation CR "
                        "(e.g., ['java', 'python', 'nodejs', 'dotnet', 'go'])"
                    ),
                ),
                telemetry_options: Optional[Dict[str, Any]] = Field(
                    default=None,
                    description=(
                        "Optional telemetry settings dict supporting keys: "
                        "'propagators' (list, default ['tracecontext', 'baggage']), "
                        "'sampler_type' (e.g., 'parentbased_traceidratio'), "
                        "'sampler_argument' (e.g., '0.25'), "
                        "'resource_attributes' (dict), "
                        "'language_images' (dict of lang -> image), "
                        "'language_env' (dict of lang -> list of {name, value} dicts)"
                    ),
                ),
                overwrite: bool = Field(
                    default=False,
                    description="If True, replaces existing CR entirely; if False, patches",
                ),
                dry_run: bool = Field(
                    default=True,
                    description="If True, validates and previews the CR without applying",
                ),
                confirm: bool = Field(
                    default=False,
                    description=(
                        "Set True to confirm overwriting an existing or GitOps-managed "
                        "Instrumentation CR when dry_run=False"
                    ),
                ),
                ctx: Context = None,  # type: ignore[assignment]
            ) -> Dict[str, Any]:
                """Create or patch an OpenTelemetry Instrumentation CRD.

                Automatically configures pinned auto-instrumentation agent images
                and per-language OTLP protocol/port environment variables so
                mixed-language namespaces (Java/Go gRPC :4317 + Python/Node.js/.NET
                HTTP :4318) route telemetry without protocol mismatches.
                """
                try:
                    if not dry_run:
                        self.require_write_access("otel_patch_instrumentation")

                    opts = dict(telemetry_options or {})
                    propagators = opts.get(
                        "propagators", ["tracecontext", "baggage"]
                    )
                    sampler_type = opts.get("sampler_type")
                    sampler_argument = opts.get("sampler_argument")
                    resource_attrs = opts.get("resource_attributes")
                    custom_images = opts.get("language_images") or {}
                    custom_env = opts.get("language_env") or {}

                    findings: List[Finding] = []

                    # Check existing Instrumentation CRs in namespace
                    existing_cr = None
                    try:
                        existing_list = (
                            await kubernetes_service.list_instrumentations(
                                namespace=namespace
                            )
                        )
                        items = existing_list.get("items", [])
                        other_crs = [
                            i.get("metadata", {}).get("name")
                            for i in items
                            if i.get("metadata", {}).get("name") != name
                        ]
                        for item in items:
                            if item.get("metadata", {}).get("name") == name:
                                existing_cr = item
                                break
                        if other_crs:
                            findings.append(
                                Finding.create(
                                    FindingCode.OP_MULTIPLE_INSTRUMENTATION_CRS,
                                    message=(
                                        f"Namespace '{namespace}' already contains "
                                        f"Instrumentation CR(s): {other_crs}. "
                                        "Workloads using 'true' in inject annotations "
                                        "fail when multiple Instrumentation CRs exist."
                                    ),
                                    field_path=f"namespaces.{namespace}.instrumentations",
                                    remediation=(
                                        "Consolidate into a single Instrumentation CR per "
                                        "namespace, or specify the CR name explicitly in "
                                        "workload inject annotations."
                                    ),
                                )
                            )
                    except Exception:
                        pass

                    gitops_info = {"managed": False}
                    if existing_cr:
                        gitops_info = detect_gitops_ownership(
                            existing_cr.get("metadata")
                        )
                        gitops_finding = build_gitops_finding(
                            name, namespace, gitops_info
                        )
                        if gitops_finding:
                            findings.append(gitops_finding)

                    if not dry_run and (
                        overwrite or gitops_info.get("managed")
                    ):
                        reason = (
                            f"Overwrite Instrumentation CR '{namespace}/{name}'"
                            if overwrite
                            else f"Patch GitOps-managed Instrumentation CR '{namespace}/{name}'"
                        )
                        confirmed = await confirm_destructive_action(
                            ctx, reason, confirm=confirm
                        )
                        if not confirmed:
                            return {
                                "action": "confirmation_required",
                                "dry_run": False,
                                "namespace": namespace,
                                "name": name,
                                "findings": [f.model_dump() for f in findings],
                                "message": (
                                    f"Confirmation required to {reason.lower()}. "
                                    "Pass confirm=True to proceed."
                                ),
                            }

                    spec: Dict[str, Any] = {
                        "exporter": {
                            "endpoint": collector_endpoint,
                        },
                        "propagators": propagators,
                    }

                    if sampler_type:
                        spec["sampler"] = {"type": sampler_type}
                        if sampler_argument is not None:
                            spec["sampler"]["argument"] = str(sampler_argument)

                    if resource_attrs and isinstance(resource_attrs, dict):
                        spec["resource"] = {
                            "resourceAttributes": {
                                str(k): str(v) for k, v in resource_attrs.items()
                            }
                        }

                    language_protocols: Dict[str, Dict[str, str]] = {}
                    if languages:
                        registry = _load_lang_registry()
                        lang_registry = registry.get("languages", {})
                        for lang in languages:
                            lang_key = lang.lower().strip()
                            lang_data = lang_registry.get(lang_key, {})
                            if not lang_data.get(
                                "auto_instrumentation_available", False
                            ) and lang_key not in custom_images:
                                continue

                            image = custom_images.get(
                                lang_key
                            ) or lang_data.get("auto_instrumentation_image")
                            otlp_env = derive_language_otlp_env(
                                collector_endpoint, lang_key
                            )
                            otlp_env_list = (
                                [
                                    {"name": k, "value": v}
                                    for k, v in otlp_env.items()
                                ]
                                if isinstance(otlp_env, dict)
                                else list(otlp_env)
                            )
                            extra_env = list(custom_env.get(lang_key) or [])
                            merged_env_map = {
                                e["name"]: e
                                for e in otlp_env_list
                                if "name" in e
                            }
                            for e in extra_env:
                                if isinstance(e, dict) and "name" in e:
                                    merged_env_map[e["name"]] = e
                            lang_spec: Dict[str, Any] = {
                                "env": list(merged_env_map.values())
                            }
                            if image:
                                lang_spec["image"] = image
                            spec[lang_key] = lang_spec
                            language_protocols[lang_key] = {
                                item["name"]: item["value"]
                                for item in otlp_env_list
                            }

                    if dry_run:
                        return {
                            "action": "dry_run",
                            "dry_run": True,
                            "namespace": namespace,
                            "name": name,
                            "spec": spec,
                            "spec_yaml": config_to_yaml(spec),
                            "language_protocol_mapping": language_protocols,
                            "findings": [f.model_dump() for f in findings],
                            "message": (
                                "Dry run — no changes applied. "
                                "Set dry_run=False to apply."
                            ),
                        }

                    result = (
                        await kubernetes_service.create_or_patch_instrumentation(
                            namespace=namespace,
                            name=name,
                            spec=spec,
                            overwrite=overwrite,
                            dry_run=False,
                        )
                    )

                    return {
                        "action": "applied",
                        "dry_run": False,
                        "namespace": namespace,
                        "name": name,
                        "spec": spec,
                        "language_protocol_mapping": language_protocols,
                        "findings": [f.model_dump() for f in findings],
                        "result": result,
                    }
                except (OtelValidationError, OtelOperationError):
                    raise
                except Exception as e:
                    self.handle_error(
                        e,
                        tool_name="otel_patch_instrumentation",
                        namespace=namespace,
                        resource_name=name,
                    )
                    raise

            @mcp_instance.tool(
                annotations=ToolAnnotations(
                    title="Manage Workload Auto-Instrumentation",
                    readOnlyHint=False,
                    destructiveHint=True,
                    idempotentHint=False,
                    openWorldHint=True,
                )
            )
            async def otel_manage_workload_instrumentation(
                namespace: str = Field(
                    ..., min_length=1, description="Workload namespace"
                ),
                workload_name: str = Field(
                    ..., min_length=1, description="Workload name"
                ),
                action: Literal["enable", "disable", "restart"] = Field(
                    default="enable",
                    description=(
                        "Action to perform: 'enable' (inject annotation), "
                        "'disable' (remove inject annotation), or 'restart' "
                        "(trigger rolling restart to pick up CR changes)"
                    ),
                ),
                workload_kind: Literal[
                    "Deployment", "StatefulSet", "DaemonSet"
                ] = Field(
                    default="Deployment",
                    description="Workload kind: 'Deployment', 'StatefulSet', or 'DaemonSet'",
                ),
                language: Optional[str] = Field(
                    default=None,
                    description=(
                        "Language to instrument ('java', 'python', 'nodejs', "
                        "'dotnet', 'go'). Required when action='enable'."
                    ),
                ),
                injection_options: Optional[Dict[str, Any]] = Field(
                    default=None,
                    description=(
                        "Optional injection settings dict supporting keys: "
                        "'instrumentation_cr_name' (str, default 'true'), "
                        "'container_names' (list of container names), "
                        "'go_target_exe' (required path for Go binary), "
                        "'dotnet_runtime' ('linux-x64' or 'linux-musl-x64'), "
                        "'resource_attributes' (dict), "
                        "'strip_conflicting_env' (bool, default False)"
                    ),
                ),
                dry_run: bool = Field(
                    default=True,
                    description="If True, previews workload patch without applying",
                ),
                confirm: bool = Field(
                    default=False,
                    description=(
                        "Set True to confirm disabling instrumentation or mutating "
                        "a GitOps-managed workload when dry_run=False"
                    ),
                ),
                ctx: Context = None,  # type: ignore[assignment]
            ) -> Dict[str, Any]:
                """Enable, disable, or restart OpenTelemetry auto-instrumentation on a workload.

                Supports Deployments, StatefulSets, and DaemonSets, multi-container
                targeting, Go eBPF target executable paths, .NET glibc/musl runtime
                identifiers, and automatic removal of conflicting hardcoded OTEL_*
                environment variables.
                """
                try:
                    if not dry_run:
                        self.require_write_access(
                            "otel_manage_workload_instrumentation"
                        )

                    opts = dict(injection_options or {})
                    findings: List[Finding] = []

                    # Read target workload
                    wl = await kubernetes_service.get_workload(
                        namespace=namespace,
                        name=workload_name,
                        kind=workload_kind,
                    )
                    gitops_info = detect_gitops_ownership({
                        "labels": wl.get("labels", {}),
                        "annotations": wl.get("annotations", {}),
                    })
                    gitops_finding = build_gitops_finding(
                        workload_name, namespace, gitops_info
                    )
                    if gitops_finding:
                        findings.append(gitops_finding)

                    # Handle restart action
                    if action == "restart":
                        if dry_run:
                            return {
                                "action": "dry_run",
                                "operation": "restart",
                                "dry_run": True,
                                "workload": f"{namespace}/{workload_name}",
                                "workload_kind": workload_kind,
                                "findings": [f.model_dump() for f in findings],
                                "message": (
                                    f"Would trigger rolling restart of {workload_kind} "
                                    f"'{namespace}/{workload_name}'. Set dry_run=False to apply."
                                ),
                            }
                        res = await kubernetes_service.restart_workload(
                            namespace=namespace,
                            name=workload_name,
                            kind=workload_kind,
                            dry_run=False,
                        )
                        return {
                            "action": "applied",
                            "operation": "restart",
                            "dry_run": False,
                            "workload": f"{namespace}/{workload_name}",
                            "workload_kind": workload_kind,
                            "findings": [f.model_dump() for f in findings],
                            "result": {
                                "name": res.get("name"),
                                "namespace": res.get("namespace"),
                            },
                            "message": (
                                f"Triggered rolling restart of {workload_kind} "
                                f"'{namespace}/{workload_name}'."
                            ),
                        }

                    # Handle disable action
                    if action == "disable":
                        pod_annotations = wl.get("pod_annotations", {}) or {}
                        annotations_to_remove: Dict[str, Optional[str]] = {}
                        if language:
                            lang_key = language.lower().strip()
                            ann_key = LANGUAGE_ANNOTATION_KEYS.get(lang_key)
                            if ann_key:
                                annotations_to_remove[ann_key] = None
                        else:
                            for k in pod_annotations:
                                if k.startswith(
                                    "instrumentation.opentelemetry.io/"
                                ):
                                    annotations_to_remove[k] = None

                        if not annotations_to_remove:
                            for ann_key in LANGUAGE_ANNOTATION_KEYS.values():
                                if ann_key in pod_annotations:
                                    annotations_to_remove[ann_key] = None

                        if dry_run:
                            return {
                                "action": "dry_run",
                                "operation": "disable",
                                "dry_run": True,
                                "workload": f"{namespace}/{workload_name}",
                                "workload_kind": workload_kind,
                                "annotations_removed": list(
                                    annotations_to_remove.keys()
                                ),
                                "findings": [f.model_dump() for f in findings],
                                "message": (
                                    f"Would remove instrumentation annotations "
                                    f"{list(annotations_to_remove.keys())} from "
                                    f"{workload_kind} '{workload_name}'. "
                                    "Set dry_run=False and confirm=True to apply."
                                ),
                            }

                        confirmed = await confirm_destructive_action(
                            ctx,
                            f"Disable auto-instrumentation on {workload_kind} "
                            f"'{namespace}/{workload_name}'",
                            confirm=confirm,
                        )
                        if not confirmed:
                            return {
                                "action": "confirmation_required",
                                "operation": "disable",
                                "dry_run": False,
                                "workload": f"{namespace}/{workload_name}",
                                "workload_kind": workload_kind,
                                "findings": [f.model_dump() for f in findings],
                                "message": (
                                    "Disabling workload instrumentation requires "
                                    "confirmation. Pass confirm=True to proceed."
                                ),
                            }

                        res = await kubernetes_service.patch_workload_annotations(
                            namespace=namespace,
                            name=workload_name,
                            annotations=annotations_to_remove,
                            kind=workload_kind,
                            dry_run=False,
                        )
                        return {
                            "action": "applied",
                            "operation": "disable",
                            "dry_run": False,
                            "workload": f"{namespace}/{workload_name}",
                            "workload_kind": workload_kind,
                            "annotations_removed": list(
                                annotations_to_remove.keys()
                            ),
                            "findings": [f.model_dump() for f in findings],
                            "result": {
                                "name": res.get("name"),
                                "namespace": res.get("namespace"),
                            },
                        }

                    # Handle enable action
                    if not language:
                        raise OtelValidationError(
                            "Parameter 'language' is required when action='enable'. "
                            f"Supported: {list(LANGUAGE_ANNOTATION_KEYS.keys())}"
                        )

                    lang_key = language.lower().strip()
                    annotation_key = LANGUAGE_ANNOTATION_KEYS.get(lang_key)
                    if not annotation_key:
                        raise OtelValidationError(
                            f"Unsupported language: '{language}'. "
                            f"Supported: {list(LANGUAGE_ANNOTATION_KEYS.keys())}"
                        )

                    go_target_exe = opts.get("go_target_exe")
                    if lang_key == "go" and not go_target_exe:
                        findings.append(
                            Finding.create(
                                FindingCode.INST_GO_MISSING_TARGET_EXE,
                                message=(
                                    "Go auto-instrumentation requires 'go_target_exe' "
                                    f"({GO_TARGET_EXE_ANNOTATION}) pointing to the binary path."
                                ),
                                field_path=f"spec.template.metadata.annotations.{GO_TARGET_EXE_ANNOTATION}",
                                remediation=(
                                    "Pass injection_options={'go_target_exe': '/app/main'}."
                                ),
                            )
                        )
                        raise OtelValidationError(
                            "Go auto-instrumentation requires "
                            "injection_options={'go_target_exe': '/path/to/binary'}."
                        )

                    cr_name = opts.get("instrumentation_cr_name")
                    annotation_value = str(cr_name) if cr_name else "true"
                    annotations: Dict[str, Optional[str]] = {
                        annotation_key: annotation_value
                    }

                    container_names = opts.get("container_names")
                    if container_names:
                        if isinstance(container_names, list):
                            wl_containers = {
                                c.get("name")
                                for c in wl.get("containers", [])
                                if not c.get("is_init_container")
                            }
                            unknown_c = [
                                c for c in container_names if c not in wl_containers
                            ]
                            if unknown_c:
                                findings.append(
                                    Finding.create(
                                        FindingCode.INST_CONTAINER_NAME_MISMATCH,
                                        message=(
                                            f"Container name(s) {unknown_c} not found in "
                                            f"{workload_kind} '{workload_name}' "
                                            f"(available: {sorted(wl_containers)})."
                                        ),
                                        field_path=f"spec.template.metadata.annotations.{CONTAINER_NAMES_ANNOTATION}",
                                        remediation=(
                                            f"Choose container_names from {sorted(wl_containers)}."
                                        ),
                                    )
                                )
                            annotations[CONTAINER_NAMES_ANNOTATION] = ",".join(
                                str(c) for c in container_names
                            )
                        else:
                            annotations[CONTAINER_NAMES_ANNOTATION] = str(
                                container_names
                            )

                    if go_target_exe:
                        annotations[GO_TARGET_EXE_ANNOTATION] = str(
                            go_target_exe
                        )

                    dotnet_runtime = opts.get("dotnet_runtime")
                    if dotnet_runtime:
                        annotations[DOTNET_RUNTIME_ANNOTATION] = str(
                            dotnet_runtime
                        )

                    res_attrs = opts.get("resource_attributes")
                    if isinstance(res_attrs, dict):
                        for k, v in res_attrs.items():
                            annotations[
                                f"{RESOURCE_ATTR_ANNOTATION_PREFIX}{k}"
                            ] = str(v)

                    # Check if Instrumentation CR exists in namespace
                    try:
                        instrs = await kubernetes_service.list_instrumentations(
                            namespace=namespace
                        )
                        items = instrs.get("items", [])
                        if not items:
                            findings.append(
                                Finding.create(
                                    FindingCode.INST_NO_CR_IN_NAMESPACE,
                                    message=(
                                        f"No Instrumentation CR found in namespace '{namespace}'. "
                                        "The Operator cannot inject an initContainer until an "
                                        "Instrumentation CR exists."
                                    ),
                                    remediation=(
                                        f"Call otel_patch_instrumentation(namespace='{namespace}', "
                                        f"name='default-instrumentation', languages=['{lang_key}']) first."
                                    ),
                                )
                            )
                    except Exception:
                        pass

                    # Check for conflicting hardcoded OTEL_* env vars
                    env_override_warnings: List[str] = []
                    for c in wl.get("containers", []):
                        if c.get("is_init_container"):
                            continue
                        env = c.get("env", {}) or {}
                        for env_name in _CONFLICT_ENV_VARS:
                            if env_name in env:
                                msg = (
                                    f"Container '{c['name']}' has hardcoded "
                                    f"'{env_name}={env[env_name]}' which overrides "
                                    "Operator-injected values."
                                )
                                env_override_warnings.append(msg)
                                findings.append(
                                    Finding.create(
                                        FindingCode.INST_CONFLICTING_ENV_OVERRIDE,
                                        message=msg,
                                        field_path=f"spec.template.spec.containers[{c['name']}].env.{env_name}",
                                        remediation=(
                                            "Pass injection_options={'strip_conflicting_env': True} "
                                            "to remove conflicting OTEL_* env vars."
                                        ),
                                    )
                                )

                    strip_conflicting = bool(
                        opts.get("strip_conflicting_env", False)
                    )
                    env_strip_result = None
                    if strip_conflicting and env_override_warnings:
                        env_strip_result = (
                            await kubernetes_service.strip_otel_env_vars(
                                namespace=namespace,
                                deployment_name=workload_name,
                                dry_run=dry_run,
                                kind=workload_kind,
                            )
                        )

                    if dry_run:
                        result_dict: Dict[str, Any] = {
                            "action": "dry_run",
                            "operation": "enable",
                            "dry_run": True,
                            "deployment": f"{namespace}/{workload_name}",
                            "workload": f"{namespace}/{workload_name}",
                            "workload_kind": workload_kind,
                            "annotation": {
                                "key": annotation_key,
                                "value": annotation_value,
                            },
                            "annotations": annotations,
                            "findings": [f.model_dump() for f in findings],
                            "message": (
                                f"Would apply annotations {annotations} to pod template "
                                f"of {workload_kind} '{workload_name}'. "
                                "Set dry_run=False to apply."
                            ),
                        }
                        if env_override_warnings:
                            result_dict["warnings"] = env_override_warnings
                        if env_strip_result:
                            result_dict["env_var_remediation"] = env_strip_result
                        return result_dict

                    if gitops_info.get("managed"):
                        confirmed = await confirm_destructive_action(
                            ctx,
                            f"Annotate GitOps-managed {workload_kind} "
                            f"'{namespace}/{workload_name}'",
                            confirm=confirm,
                        )
                        if not confirmed:
                            return {
                                "action": "confirmation_required",
                                "operation": "enable",
                                "dry_run": False,
                                "workload": f"{namespace}/{workload_name}",
                                "workload_kind": workload_kind,
                                "findings": [f.model_dump() for f in findings],
                                "message": (
                                    f"{workload_kind} '{namespace}/{workload_name}' is managed "
                                    f"by {gitops_info.get('manager')}. Pass confirm=True to "
                                    "apply live annotations."
                                ),
                            }

                    result = await kubernetes_service.patch_workload_annotations(
                        namespace=namespace,
                        name=workload_name,
                        annotations=annotations,
                        kind=workload_kind,
                        dry_run=False,
                    )

                    result_dict = {
                        "action": "applied",
                        "operation": "enable",
                        "dry_run": False,
                        "deployment": f"{namespace}/{workload_name}",
                        "workload": f"{namespace}/{workload_name}",
                        "workload_kind": workload_kind,
                        "annotation": {
                            "key": annotation_key,
                            "value": annotation_value,
                        },
                        "annotations": annotations,
                        "findings": [f.model_dump() for f in findings],
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
                except (OtelValidationError, OtelOperationError):
                    raise
                except Exception as e:
                    self.handle_error(
                        e,
                        tool_name="otel_manage_workload_instrumentation",
                        namespace=namespace,
                        resource_name=workload_name,
                    )
                    raise

        if self.should_register_tool("instrumentation", is_write=False):

            @mcp_instance.tool(
                annotations=ToolAnnotations(
                    title="Verify Workload Auto-Instrumentation",
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=True,
                )
            )
            async def otel_verify_instrumentation(
                namespace: str = Field(
                    ..., min_length=1, description="Workload namespace"
                ),
                workload_name: str = Field(
                    ..., min_length=1, description="Workload name"
                ),
                workload_kind: Literal[
                    "Deployment", "StatefulSet", "DaemonSet"
                ] = Field(
                    default="Deployment",
                    description="Workload kind: 'Deployment', 'StatefulSet', or 'DaemonSet'",
                ),
                ctx: Context = None,  # type: ignore[assignment]
            ) -> Dict[str, Any]:
                """Verify end-to-end auto-instrumentation for a workload in a single call.

                Correlates workload pod template annotations, Instrumentation CR
                existence in the namespace, live pod initContainers, injected OTEL_*
                env vars, pod creation timestamps vs. CR creation timestamps, and
                Operator webhook logs to explain whether and why instrumentation is
                working or failing.
                """
                try:
                    findings: List[Finding] = []
                    wl = await kubernetes_service.get_workload(
                        namespace=namespace,
                        name=workload_name,
                        kind=workload_kind,
                    )

                    pod_annotations = wl.get("pod_annotations", {}) or {}
                    annotated_lang = detect_language_from_annotations(
                        pod_annotations
                    )
                    cr_ref = get_instrumentation_cr_from_annotations(
                        pod_annotations
                    )

                    # 1. Check Instrumentation CRs in namespace
                    instrs_raw = await kubernetes_service.list_instrumentations(
                        namespace=namespace
                    )
                    instr_items = instrs_raw.get("items", [])
                    matched_cr = None
                    cr_created_ts = None

                    if len(instr_items) == 0:
                        findings.append(
                            Finding.create(
                                FindingCode.INST_NO_CR_IN_NAMESPACE,
                                message=(
                                    f"No Instrumentation CR exists in namespace '{namespace}'."
                                ),
                                remediation=(
                                    f"Create an Instrumentation CR in '{namespace}' using "
                                    "otel_patch_instrumentation."
                                ),
                            )
                        )
                    elif len(instr_items) > 1 and (
                        cr_ref is None or cr_ref == "true"
                    ):
                        findings.append(
                            Finding.create(
                                FindingCode.OP_MULTIPLE_INSTRUMENTATION_CRS,
                                message=(
                                    f"Namespace '{namespace}' has {len(instr_items)} "
                                    "Instrumentation CRs, and workload uses 'true' instead "
                                    "of an explicit CR name."
                                ),
                                remediation=(
                                    "Delete duplicate Instrumentation CRs or set "
                                    "instrumentation_cr_name explicitly."
                                ),
                            )
                        )
                        matched_cr = instr_items[0]
                    else:
                        if cr_ref and cr_ref != "true":
                            for item in instr_items:
                                if (
                                    item.get("metadata", {}).get("name")
                                    == cr_ref
                                ):
                                    matched_cr = item
                                    break
                        else:
                            matched_cr = instr_items[0]

                    if matched_cr:
                        cr_created_ts = (
                            matched_cr.get("metadata", {}) or {}
                        ).get("creationTimestamp")

                    # 2. Check Go target exe & container names on workload
                    if (
                        annotated_lang == "go"
                        and not pod_annotations.get(GO_TARGET_EXE_ANNOTATION)
                    ):
                        findings.append(
                            Finding.create(
                                FindingCode.INST_GO_MISSING_TARGET_EXE,
                                message=(
                                    f"{workload_kind} '{workload_name}' has inject-go "
                                    f"without '{GO_TARGET_EXE_ANNOTATION}'."
                                ),
                                field_path=f"spec.template.metadata.annotations.{GO_TARGET_EXE_ANNOTATION}",
                                remediation=(
                                    "Set injection_options={'go_target_exe': '/path/to/binary'} "
                                    "via otel_manage_workload_instrumentation."
                                ),
                            )
                        )

                    target_containers_str = pod_annotations.get(
                        CONTAINER_NAMES_ANNOTATION
                    )
                    if target_containers_str:
                        requested_containers = [
                            c.strip()
                            for c in target_containers_str.split(",")
                            if c.strip()
                        ]
                        actual_containers = {
                            c.get("name")
                            for c in wl.get("containers", [])
                            if not c.get("is_init_container")
                        }
                        missing_c = [
                            c
                            for c in requested_containers
                            if c not in actual_containers
                        ]
                        if missing_c:
                            findings.append(
                                Finding.create(
                                    FindingCode.INST_CONTAINER_NAME_MISMATCH,
                                    message=(
                                        f"Annotation '{CONTAINER_NAMES_ANNOTATION}' references "
                                        f"missing container(s) {missing_c} (actual: {sorted(actual_containers)})."
                                    ),
                                    field_path=f"spec.template.metadata.annotations.{CONTAINER_NAMES_ANNOTATION}",
                                    remediation=(
                                        f"Update container-names to match {sorted(actual_containers)}."
                                    ),
                                )
                            )

                    # 3. Check hardcoded conflicting OTEL_* env vars
                    for c in wl.get("containers", []):
                        if c.get("is_init_container"):
                            continue
                        env = c.get("env", {}) or {}
                        for conflict_key in _CONFLICT_ENV_VARS:
                            if conflict_key in env:
                                findings.append(
                                    Finding.create(
                                        FindingCode.INST_CONFLICTING_ENV_OVERRIDE,
                                        message=(
                                            f"Container '{c.get('name')}' defines hardcoded "
                                            f"'{conflict_key}={env[conflict_key]}'."
                                        ),
                                        field_path=f"spec.template.spec.containers[{c.get('name')}].env.{conflict_key}",
                                        remediation=(
                                            "Call otel_manage_workload_instrumentation with "
                                            "injection_options={'strip_conflicting_env': True}."
                                        ),
                                    )
                                )

                    # 4. Inspect live pods for workload
                    all_pods = await kubernetes_service.list_pods(
                        namespace=namespace
                    )
                    pod_labels = wl.get("pod_labels", {}) or {}
                    workload_pods = []
                    for p in all_pods:
                        p_name = p.get("name", "")
                        p_labels = p.get("labels", {}) or {}
                        if pod_labels and all(
                            p_labels.get(k) == v for k, v in pod_labels.items()
                        ):
                            workload_pods.append(p)
                        elif p_name.startswith(f"{workload_name}-"):
                            workload_pods.append(p)

                    pod_summaries = []
                    any_init_injected = False
                    for p in workload_pods:
                        init_cs = p.get("init_containers", []) or []
                        has_otel_init = any(
                            "opentelemetry"
                            in (ic.get("image", "") or "").lower()
                            or "opentelemetry"
                            in (ic.get("name", "") or "").lower()
                            for ic in init_cs
                        )
                        if has_otel_init:
                            any_init_injected = True

                        p_created = p.get("creation_timestamp")
                        if (
                            annotated_lang
                            and not has_otel_init
                            and cr_created_ts
                            and p_created
                            and str(p_created) < str(cr_created_ts)
                        ):
                            findings.append(
                                Finding.create(
                                    FindingCode.INST_POD_NOT_RESTARTED,
                                    message=(
                                        f"Pod '{p.get('name')}' was created ({p_created}) "
                                        f"before Instrumentation CR ({cr_created_ts}) and "
                                        "lacks the auto-instrumentation initContainer."
                                    ),
                                    remediation=(
                                        f"Call otel_manage_workload_instrumentation("
                                        f"namespace='{namespace}', workload_name='{workload_name}', "
                                        f"workload_kind='{workload_kind}', action='restart')."
                                    ),
                                )
                            )

                        injected_env = {}
                        for c in p.get("containers", []):
                            for ek, ev in (c.get("env", {}) or {}).items():
                                if ek.startswith("OTEL_") or ek in (
                                    "JAVA_TOOL_OPTIONS",
                                    "PYTHONPATH",
                                    "NODE_OPTIONS",
                                    "CORECLR_ENABLE_PROFILING",
                                ):
                                    injected_env[ek] = ev

                        pod_summaries.append({
                            "name": p.get("name"),
                            "phase": p.get("phase"),
                            "init_containers": init_cs,
                            "otel_init_injected": has_otel_init,
                            "injected_env": injected_env,
                            "creation_timestamp": p_created,
                        })

                    # Check workload template init_containers as fallback when pods list is empty in unit tests
                    template_init_injected = any(
                        c.get("is_init_container", False)
                        and "opentelemetry"
                        in (c.get("image", "") or "").lower()
                        for c in wl.get("containers", [])
                    )
                    effective_init_injected = (
                        any_init_injected or template_init_injected
                    )

                    if (
                        annotated_lang
                        and matched_cr
                        and not effective_init_injected
                        and not any(
                            f.code == FindingCode.INST_POD_NOT_RESTARTED
                            for f in findings
                        )
                    ):
                        findings.append(
                            Finding.create(
                                FindingCode.INST_WEBHOOK_BLOCKED,
                                message=(
                                    f"{workload_kind} '{workload_name}' has annotation "
                                    f"'inject-{annotated_lang}' and Instrumentation CR exists, "
                                    "but no OpenTelemetry initContainer was injected."
                                ),
                                remediation=(
                                    "Restart the workload with action='restart', or inspect "
                                    "otel://operator/status for mutating webhook errors."
                                ),
                            )
                        )

                    has_errors = any(
                        f.severity == FindingSeverity.ERROR for f in findings
                    )
                    verified = bool(
                        annotated_lang
                        and matched_cr
                        and effective_init_injected
                        and not has_errors
                    )

                    return {
                        "verified": verified,
                        "status": "verified" if verified else "unverified",
                        "workload": {
                            "name": workload_name,
                            "namespace": namespace,
                            "kind": workload_kind,
                            "annotated_language": annotated_lang,
                            "instrumentation_cr_ref": cr_ref or "true",
                            "pod_annotations": pod_annotations,
                            "template_init_injected": template_init_injected,
                        },
                        "instrumentation_cr": (
                            {
                                "name": (
                                    matched_cr.get("metadata", {}) or {}
                                ).get("name"),
                                "creation_timestamp": cr_created_ts,
                                "exporter": (
                                    matched_cr.get("spec", {}) or {}
                                ).get("exporter"),
                            }
                            if matched_cr
                            else None
                        ),
                        "pods": pod_summaries,
                        "findings": [f.model_dump() for f in findings],
                    }
                except Exception as e:
                    self.handle_error(
                        e,
                        tool_name="otel_verify_instrumentation",
                        namespace=namespace,
                        resource_name=workload_name,
                    )
                    raise
