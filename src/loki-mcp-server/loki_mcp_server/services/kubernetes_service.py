"""Kubernetes Loki Operator CRD (`loki.grafana.com`) inspection and Server-Side Apply service."""

from __future__ import annotations

import asyncio
import copy
import json
import os
import shutil
from typing import Any, Dict, List, Optional

import yaml

from loki_mcp_server.config import KubernetesConfig, LokiOperatorConfig
from loki_mcp_server.exceptions import LokiQueryError, LokiValidationError
from loki_mcp_server.utils.elicitation import compute_unified_diff
from loki_mcp_server.utils.redaction import sanitize_k8s_manifest

SUPPORTED_LOKI_CRD_KINDS = {
    "lokistack": ("LokiStack", "lokistacks", "v1"),
    "lokistacks": ("LokiStack", "lokistacks", "v1"),
    "rulerconfig": ("RulerConfig", "rulerconfigs", "v1beta1"),
    "rulerconfigs": ("RulerConfig", "rulerconfigs", "v1beta1"),
    "alertingrule": ("AlertingRule", "alertingrules", "v1beta1"),
    "alertingrules": ("AlertingRule", "alertingrules", "v1beta1"),
    "recordingrule": ("RecordingRule", "recordingrules", "v1beta1"),
    "recordingrules": ("RecordingRule", "recordingrules", "v1beta1"),
}

_DIFF_STRIP_META_KEYS = frozenset(
    {"uid", "resourceVersion", "generation", "creationTimestamp", "managedFields"}
)


def _clean_for_diff(obj: Dict[str, Any]) -> Dict[str, Any]:
    """Strip volatile Kubernetes server metadata so unified diffs highlight real spec/label changes."""
    cleaned = copy.deepcopy(sanitize_k8s_manifest(obj))
    meta = cleaned.get("metadata")
    if isinstance(meta, dict):
        for k in _DIFF_STRIP_META_KEYS:
            meta.pop(k, None)
    cleaned.pop("status", None)
    return cleaned


class KubernetesService:
    """Service for inspecting and managing Kubernetes Loki Operator Custom Resources."""

    def __init__(
        self,
        k8s_config: KubernetesConfig,
        operator_config: Optional[LokiOperatorConfig] = None,
        field_manager: str = "talkops-loki-mcp",
        force_live_k8s: bool = False,
    ) -> None:
        self.k8s_config = k8s_config
        self.operator_config = operator_config or LokiOperatorConfig()
        self.field_manager = field_manager
        self._force_live_k8s = force_live_k8s
        self._store: Dict[str, Dict[str, Any]] = {}

    def _use_live_k8s(self) -> bool:
        """Return True when live Kubernetes cluster operations should run via kubectl."""
        if not self.k8s_config.enabled:
            return False
        if self._force_live_k8s:
            return True
        if os.getenv("PYTEST_CURRENT_TEST"):
            return False
        return shutil.which("kubectl") is not None

    def _kubectl_cmd(self, *args: str) -> List[str]:
        cmd = ["kubectl"]
        if self.k8s_config.kubeconfig:
            cmd.extend(["--kubeconfig", self.k8s_config.kubeconfig])
        if self.k8s_config.context_name:
            cmd.extend(["--context", self.k8s_config.context_name])
        cmd.extend(args)
        return cmd

    async def _run_kubectl(
        self,
        *args: str,
        stdin_text: Optional[str] = None,
        timeout: float = 20.0,
    ) -> tuple[int, str, str]:
        cmd = self._kubectl_cmd(*args)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE if stdin_text is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        in_bytes = stdin_text.encode("utf-8") if stdin_text is not None else None
        out_b, err_b = await asyncio.wait_for(proc.communicate(in_bytes), timeout=timeout)
        return (
            proc.returncode or 0,
            out_b.decode("utf-8", errors="replace"),
            err_b.decode("utf-8", errors="replace"),
        )

    def resolve_crd_kind(self, kind: str) -> tuple[str, str, str]:
        """Resolve a user-supplied CRD kind into (CanonicalKind, plural, api_version)."""
        key = (kind or "").strip().lower()
        if key not in SUPPORTED_LOKI_CRD_KINDS:
            raise LokiValidationError(
                f"Unsupported Loki Operator CRD kind '{kind}'. "
                "Supported kinds: LokiStack, RulerConfig, AlertingRule, RecordingRule."
            )
        return SUPPORTED_LOKI_CRD_KINDS[key]

    def validate_operator_manifest(
        self,
        manifest_yaml: str,
        default_namespace: str = "default",
    ) -> Dict[str, Any]:
        """Parse and validate a Loki Operator CR YAML manifest."""
        if not manifest_yaml or not manifest_yaml.strip():
            raise LokiValidationError("manifest_yaml must not be empty.")
        try:
            doc = yaml.safe_load(manifest_yaml)
        except Exception as exc:
            raise LokiValidationError(f"Invalid YAML syntax in manifest: {exc}") from exc

        if not isinstance(doc, dict):
            raise LokiValidationError("Manifest must be a YAML mapping object.")

        kind_raw = str(doc.get("kind", "")).strip()
        if not kind_raw:
            raise LokiValidationError("Manifest is missing required 'kind' field.")

        canonical_kind, _, expected_ver = self.resolve_crd_kind(kind_raw)
        doc["kind"] = canonical_kind

        api_version = str(doc.get("apiVersion", "")).strip()
        expected_prefix = f"{self.operator_config.crd_group}/"
        if not api_version:
            doc["apiVersion"] = f"{self.operator_config.crd_group}/{expected_ver}"
        elif not api_version.startswith(expected_prefix):
            raise LokiValidationError(
                f"Invalid apiVersion '{api_version}' for {canonical_kind}. "
                f"Expected '{self.operator_config.crd_group}/{expected_ver}'."
            )

        meta = doc.get("metadata")
        if not isinstance(meta, dict) or not meta.get("name"):
            raise LokiValidationError(
                "Manifest metadata.name is required for Loki Operator resources."
            )
        meta.setdefault("namespace", default_namespace)

        spec = doc.get("spec")
        if not isinstance(spec, dict) or not spec:
            raise LokiValidationError(
                f"{canonical_kind} manifest must contain a non-empty 'spec' object."
            )

        if canonical_kind == "LokiStack":
            size = spec.get("size")
            if not size:
                raise LokiValidationError(
                    "LokiStack spec.size is required (e.g., '1x.extra-small', '1x.small', '1x.medium')."
                )
            storage = spec.get("storage")
            if not isinstance(storage, dict) or "secret" not in storage:
                raise LokiValidationError(
                    "LokiStack spec.storage.secret is required to configure object storage credentials."
                )

        return doc

    async def list_loki_operator_crs(
        self,
        namespace: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List Loki Operator custom resources in a namespace (or all namespaces)."""
        if self._use_live_k8s():
            items: List[Dict[str, Any]] = []
            seen_keys: set[str] = set()
            plurals = ("lokistacks", "rulerconfigs", "alertingrules", "recordingrules")
            ns_args = (
                ["-A"]
                if (not namespace or namespace == "_all")
                else ["-n", namespace]
            )
            for plural in plurals:
                resource = f"{plural}.{self.operator_config.crd_group}"
                rc, stdout, _ = await self._run_kubectl(
                    "get", resource, *ns_args, "-o", "json", "--ignore-not-found"
                )
                if rc != 0 or not stdout.strip():
                    continue
                try:
                    payload = json.loads(stdout)
                except json.JSONDecodeError:
                    continue
                raw_items = (
                    payload.get("items", [])
                    if isinstance(payload, dict) and "items" in payload
                    else ([payload] if isinstance(payload, dict) and payload.get("kind") else [])
                )
                for cr in raw_items:
                    if not isinstance(cr, dict):
                        continue
                    meta = cr.get("metadata") or {}
                    k_id = f"{cr.get('kind', plural)}/{meta.get('namespace', 'default')}/{meta.get('name', '')}"
                    if k_id not in seen_keys:
                        seen_keys.add(k_id)
                        items.append(sanitize_k8s_manifest(cr))
            items.sort(
                key=lambda c: (
                    str(c.get("kind", "")),
                    str(c.get("metadata", {}).get("namespace", "")),
                    str(c.get("metadata", {}).get("name", "")),
                )
            )
            return items

        items = []
        for _, cr in sorted(self._store.items()):
            ns = cr.get("metadata", {}).get("namespace", "default")
            if namespace and namespace != "_all" and ns != namespace:
                continue
            items.append(sanitize_k8s_manifest(cr))
        return items

    async def get_loki_operator_cr(
        self,
        kind: str,
        namespace: str,
        name: str,
    ) -> Dict[str, Any]:
        """Get a sanitized Loki Operator CR manifest by kind, namespace, and name."""
        canonical_kind, plural, _ = self.resolve_crd_kind(kind)
        if self._use_live_k8s():
            resource = f"{plural}.{self.operator_config.crd_group}"
            rc, stdout, _ = await self._run_kubectl(
                "get", resource, name, "-n", namespace, "-o", "json"
            )
            if rc == 0 and stdout.strip():
                try:
                    parsed = json.loads(stdout)
                    if isinstance(parsed, dict) and parsed.get("metadata", {}).get("name"):
                        return sanitize_k8s_manifest(parsed)
                except json.JSONDecodeError:
                    pass
            return {
                "apiVersion": f"{self.operator_config.crd_group}/v1",
                "kind": canonical_kind,
                "metadata": {"name": name, "namespace": namespace},
                "status": {"phase": "NotFound", "kubernetes_enabled": self.k8s_config.enabled},
            }

        key = f"{canonical_kind}/{namespace}/{name}"
        if key in self._store:
            return sanitize_k8s_manifest(self._store[key])
        return {
            "apiVersion": f"{self.operator_config.crd_group}/v1",
            "kind": canonical_kind,
            "metadata": {"name": name, "namespace": namespace},
            "status": {"phase": "NotFound", "kubernetes_enabled": self.k8s_config.enabled},
        }

    async def apply_loki_operator_cr(
        self,
        manifest_yaml: str,
        namespace: str = "default",
        dry_run: bool = True,
        force_conflicts: bool = False,
    ) -> Dict[str, Any]:
        """Validate, compute unified diff, and dry-run or Server-Side Apply a Loki Operator CR."""
        doc = self.validate_operator_manifest(
            manifest_yaml=manifest_yaml,
            default_namespace=namespace,
        )
        canonical_kind = doc["kind"]
        meta = doc["metadata"]
        name = meta["name"]
        ns = meta.get("namespace", namespace)
        meta["namespace"] = ns
        key = f"{canonical_kind}/{ns}/{name}"

        if self._use_live_k8s():
            existing_cr = await self.get_loki_operator_cr(canonical_kind, ns, name)
            has_existing = (
                isinstance(existing_cr, dict)
                and existing_cr.get("status", {}).get("phase") != "NotFound"
            )
            before_yaml = (
                yaml.safe_dump(_clean_for_diff(existing_cr), sort_keys=True)
                if has_existing
                else ""
            )

            apply_args = [
                "apply",
                "--server-side",
                f"--field-manager={self.field_manager}",
                "-n",
                ns,
                "-f",
                "-",
                "-o",
                "json",
            ]
            if force_conflicts:
                apply_args.append("--force-conflicts")
            if dry_run:
                apply_args.append("--dry-run=server")

            rc, stdout, stderr = await self._run_kubectl(
                *apply_args,
                stdin_text=yaml.safe_dump(doc, sort_keys=False),
            )
            if rc != 0:
                raise LokiQueryError(
                    f"Kubernetes Server-Side Apply failed for {canonical_kind} '{ns}/{name}': "
                    f"{stderr.strip() or stdout.strip()}"
                )

            try:
                applied_obj = json.loads(stdout) if stdout.strip() else doc
            except json.JSONDecodeError:
                applied_obj = doc

            sanitized_result = sanitize_k8s_manifest(applied_obj)
            after_yaml = yaml.safe_dump(_clean_for_diff(applied_obj), sort_keys=True)
            diff = compute_unified_diff(
                before_yaml,
                after_yaml,
                fromfile=f"live/{canonical_kind}/{ns}/{name}",
                tofile=f"desired/{canonical_kind}/{ns}/{name}",
            )
            return {
                "status": "dry_run_preview" if dry_run else "applied",
                "dry_run": dry_run,
                "kind": canonical_kind,
                "namespace": ns,
                "name": name,
                "field_manager": self.field_manager,
                "force_conflicts": force_conflicts,
                "diff": diff,
                "manifest": sanitized_result,
            }

        existing = self._store.get(key)
        before_yaml = (
            yaml.safe_dump(sanitize_k8s_manifest(existing), sort_keys=True)
            if existing
            else ""
        )
        sanitized_desired = sanitize_k8s_manifest(doc)
        after_yaml = yaml.safe_dump(sanitized_desired, sort_keys=True)
        diff = compute_unified_diff(
            before_yaml,
            after_yaml,
            fromfile=f"live/{canonical_kind}/{ns}/{name}",
            tofile=f"desired/{canonical_kind}/{ns}/{name}",
        )

        if not dry_run:
            self._store[key] = sanitized_desired

        return {
            "status": "dry_run_preview" if dry_run else "applied",
            "dry_run": dry_run,
            "kind": canonical_kind,
            "namespace": ns,
            "name": name,
            "field_manager": self.field_manager,
            "force_conflicts": force_conflicts,
            "diff": diff,
            "manifest": sanitized_desired,
        }
