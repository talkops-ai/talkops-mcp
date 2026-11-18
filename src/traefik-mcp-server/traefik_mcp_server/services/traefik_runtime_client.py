"""Traefik v3 Runtime API client (direct HTTP or Kubernetes pods/proxy)."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
import requests


class TraefikRuntimeClient:
    """Fetches running configuration and router/service/middleware status from Traefik's /api/* endpoints."""

    def __init__(
        self,
        traefik_api_url: Optional[str] = None,
        traefik_namespace: str = "traefik",
        k8s_core_v1: Any = None,
        timeout: float = 3.0,
    ):
        self.traefik_api_url = (traefik_api_url or "").rstrip("/") if traefik_api_url else None
        self.traefik_namespace = traefik_namespace
        self.k8s_core_v1 = k8s_core_v1
        self.timeout = timeout
        self._mock_rawdata: Optional[Dict[str, Any]] = None
        self._mock_overview: Optional[Dict[str, Any]] = None
        self._mock_version: Optional[Dict[str, Any]] = None
        self._mock_entrypoints: Optional[List[Dict[str, Any]]] = None

    def set_mock_runtime_data(
        self,
        rawdata: Optional[Dict[str, Any]] = None,
        overview: Optional[Dict[str, Any]] = None,
        version: Optional[Dict[str, Any]] = None,
        entrypoints: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Inject mock runtime responses for unit and integration testing."""
        if rawdata is not None:
            # Normalize if rawdata is passed in protocol-grouped fixture format (e.g. {"http": {"routers": [...]}})
            if "http" in rawdata and isinstance(rawdata["http"], dict) and "routers" not in rawdata:
                normalized: Dict[str, Any] = {}
                for proto, p_prefix in (("http", ""), ("tcp", "tcp"), ("udp", "udp")):
                    p_data = rawdata.get(proto) or {}
                    for section in ("routers", "services", "middlewares"):
                        items = p_data.get(section)
                        if items is None:
                            continue
                        target_k = section if not p_prefix else f"{p_prefix}{section.capitalize()}"
                        if isinstance(items, list):
                            normalized[target_k] = {it["name"]: it for it in items if isinstance(it, dict) and "name" in it}
                        elif isinstance(items, dict):
                            normalized[target_k] = items
                self._mock_rawdata = normalized
                if overview is None and "overview" in rawdata:
                    self._mock_overview = rawdata["overview"]
                if version is None and "version" in rawdata:
                    self._mock_version = rawdata["version"]
                if entrypoints is None and "entrypoints" in rawdata:
                    self._mock_entrypoints = rawdata["entrypoints"]
            else:
                self._mock_rawdata = rawdata
        if overview is not None:
            self._mock_overview = overview
        if version is not None:
            self._mock_version = version
        if entrypoints is not None:
            self._mock_entrypoints = entrypoints

    def _get_json(self, path: str) -> Optional[Any]:
        clean_path = path if path.startswith("/") else f"/{path}"
        if clean_path == "/api/rawdata" and self._mock_rawdata is not None:
            return self._mock_rawdata
        if clean_path == "/api/overview" and self._mock_overview is not None:
            return self._mock_overview
        if clean_path == "/api/version" and self._mock_version is not None:
            return self._mock_version
        if clean_path == "/api/entrypoints" and self._mock_entrypoints is not None:
            return self._mock_entrypoints

        # 1. Direct URL override
        if self.traefik_api_url:
            try:
                resp = requests.get(f"{self.traefik_api_url}{clean_path}", timeout=self.timeout)
                if resp.status_code == 200:
                    return resp.json()
            except Exception:
                return None

        # 2. Via Kubernetes API pods/proxy to Traefik pod
        if self.k8s_core_v1 is not None:
            try:
                pods = self.k8s_core_v1.list_namespaced_pod(
                    namespace=self.traefik_namespace,
                    label_selector="app.kubernetes.io/name=traefik",
                )
                items = getattr(pods, "items", []) or []
                if not items:
                    pods = self.k8s_core_v1.list_namespaced_pod(namespace=self.traefik_namespace)
                    items = [
                        p
                        for p in (getattr(pods, "items", []) or [])
                        if "traefik" in (getattr(getattr(p, "metadata", None), "name", "") or "").lower()
                    ]
                for pod in items:
                    pod_name = getattr(getattr(pod, "metadata", None), "name", None)
                    if not pod_name:
                        continue
                    for port in (9000, 8080):
                        try:
                            raw = self.k8s_core_v1.connect_get_namespaced_pod_proxy_with_path(
                                name=f"{pod_name}:{port}",
                                namespace=self.traefik_namespace,
                                path=clean_path.lstrip("/"),
                            )
                            if isinstance(raw, (dict, list)):
                                return raw
                            if isinstance(raw, str):
                                return json.loads(raw)
                        except Exception:
                            continue
            except Exception:
                return None

        return None

    def is_reachable(self) -> bool:
        return self._get_json("/api/version") is not None or self._get_json("/api/overview") is not None

    def get_version(self) -> Dict[str, Any]:
        data = self._get_json("/api/version")
        if isinstance(data, dict):
            return {
                "version": data.get("Version") or data.get("version") or "3.x",
                "codename": data.get("Codename") or data.get("codename") or "",
                "reachable": True,
            }
        return {"version": "unknown", "codename": "", "reachable": False}

    def get_entrypoints(self) -> List[Dict[str, Any]]:
        data = self._get_json("/api/entrypoints")
        if isinstance(data, list):
            return data
        return []

    def get_rawdata(self) -> Dict[str, Any]:
        data = self._get_json("/api/rawdata")
        if isinstance(data, dict):
            return data
        return {}

    def get_overview(self) -> Dict[str, Any]:
        data = self._get_json("/api/overview")
        if isinstance(data, dict):
            return data
        return {}

    def get_protocol_snapshot(self, protocol: str = "http") -> Dict[str, Any]:
        """Return concise runtime routers, services, and middlewares for a protocol ('http', 'tcp', 'udp')."""
        proto = protocol.strip().lower()
        raw = self.get_rawdata()
        routers_key = "routers" if proto == "http" else f"{proto}Routers"
        services_key = "services" if proto == "http" else f"{proto}Services"
        middlewares_key = "middlewares" if proto == "http" else f"{proto}Middlewares"

        routers_map = raw.get(routers_key) or {}
        services_map = raw.get(services_key) or {}
        middlewares_map = raw.get(middlewares_key) or {}

        routers: List[Dict[str, Any]] = []
        for r_name, r_obj in routers_map.items():
            if not isinstance(r_obj, dict):
                continue
            routers.append({
                "name": r_name,
                "status": r_obj.get("status", "enabled"),
                "rule": r_obj.get("rule", ""),
                "priority": r_obj.get("priority", 0),
                "entryPoints": r_obj.get("entryPoints") or r_obj.get("using") or [],
                "service": r_obj.get("service", ""),
                "middlewares": r_obj.get("middlewares") or [],
                "tls": bool(r_obj.get("tls")),
                "provider": r_obj.get("provider") or (r_name.split("@")[-1] if "@" in r_name else "kubernetescrd"),
                "error": r_obj.get("error") or [],
            })

        services: List[Dict[str, Any]] = []
        for s_name, s_obj in services_map.items():
            if not isinstance(s_obj, dict):
                continue
            lb = s_obj.get("loadBalancer") or {}
            wrr = s_obj.get("weighted") or {}
            mir = s_obj.get("mirroring") or {}
            stype = "weighted" if wrr else ("mirroring" if mir else "loadBalancer")
            services.append({
                "name": s_name,
                "type": stype,
                "status": s_obj.get("status", "enabled"),
                "serverStatus": s_obj.get("serverStatus") or {},
                "servers": lb.get("servers") or [],
                "weighted_services": wrr.get("services") or [],
                "mirrors": mir.get("mirrors") or [],
                "usedBy": s_obj.get("usedBy") or [],
                "error": s_obj.get("error") or [],
            })

        middlewares: List[Dict[str, Any]] = []
        for m_name, m_obj in middlewares_map.items():
            if not isinstance(m_obj, dict):
                continue
            middlewares.append({
                "name": m_name,
                "status": m_obj.get("status", "enabled"),
                "type": m_obj.get("type", ""),
                "usedBy": m_obj.get("usedBy") or [],
                "error": m_obj.get("error") or [],
            })

        return {
            "protocol": proto,
            "reachable": bool(raw),
            "routers": routers,
            "services": services,
            "middlewares": middlewares,
        }

    def get_runtime_health(self) -> Dict[str, Any]:
        """Combine /api/overview totals with every router/service/middleware in error or warning state."""
        overview = self.get_overview()
        raw = self.get_rawdata()
        errors: List[Dict[str, Any]] = []
        warnings: List[Dict[str, Any]] = []

        for proto in ("http", "tcp", "udp"):
            snap = self.get_protocol_snapshot(proto)
            for kind, items in (
                ("router", snap["routers"]),
                ("service", snap["services"]),
                ("middleware", snap["middlewares"]),
            ):
                for item in items:
                    status = str(item.get("status", "enabled")).lower()
                    item_errs = item.get("error") or []
                    if isinstance(item_errs, str):
                        item_errs = [item_errs]
                    if status == "disabled" or item_errs:
                        errors.append({
                            "protocol": proto,
                            "kind": kind,
                            "name": item["name"],
                            "status": item.get("status", "disabled"),
                            "messages": item_errs,
                        })
                    elif status == "warning":
                        warnings.append({
                            "protocol": proto,
                            "kind": kind,
                            "name": item["name"],
                            "status": "warning",
                            "messages": item_errs,
                        })
                    # Also flag DOWN servers in loadBalancer services
                    if kind == "service":
                        srv_status = item.get("serverStatus") or {}
                        down_urls = [u for u, st in srv_status.items() if str(st).upper() != "UP"]
                        if down_urls:
                            warnings.append({
                                "protocol": proto,
                                "kind": "service_backend",
                                "name": item["name"],
                                "status": "degraded",
                                "messages": [f"Backend server(s) DOWN: {', '.join(down_urls)}"],
                            })

        return {
            "reachable": bool(overview or raw),
            "overview": overview,
            "error_count": len(errors),
            "warning_count": len(warnings),
            "errors": errors,
            "warnings": warnings,
        }

    def find_runtime_router(self, namespace: str, route_name: str, protocol: str = "http") -> Optional[Dict[str, Any]]:
        """Locate the runtime router entry corresponding to a Kubernetes IngressRoute/Ingress."""
        snap = self.get_protocol_snapshot(protocol)
        prefix = f"{namespace}-{route_name}".lower()
        for r in snap["routers"]:
            r_name = str(r.get("name", "")).lower()
            if r_name.startswith(prefix) or route_name.lower() in r_name:
                return r
        return None
