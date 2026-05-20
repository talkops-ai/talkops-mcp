"""Exporter catalog and manifest builder for common Prometheus exporters."""

from typing import Any, Dict, List, Literal, Optional, Tuple

from prometheus_mcp_server.models.exporter import ExporterInfo


from prometheus_mcp_server.config import SUPPORTED_EXPORTERS


def list_exporters() -> List[ExporterInfo]:
    """List all supported exporters."""
    return list(SUPPORTED_EXPORTERS.values())


def recommend_exporters(
    service_type: str,
    environment: Literal["kubernetes", "vm"],
) -> Tuple[List[ExporterInfo], str]:
    """Recommend exporters for a given service type.

    Returns:
        Tuple of (matching exporters, advisory notes)
    """
    svc = service_type.lower()
    recs: List[ExporterInfo] = []

    for exp in SUPPORTED_EXPORTERS.values():
        if environment in exp.supported_environments and svc in exp.type:
            recs.append(exp)

    if not recs:
        # Try partial match
        for exp in SUPPORTED_EXPORTERS.values():
            if environment in exp.supported_environments and (
                svc in exp.description.lower() or svc in exp.type
            ):
                recs.append(exp)

    notes = ""
    if not recs:
        recs = [SUPPORTED_EXPORTERS["node_exporter"]]
        notes = (
            f"No specific exporter found for '{service_type}'. "
            "Returning node_exporter as a baseline. "
            "Consider writing a custom exporter or using application-level instrumentation."
        )
    else:
        notes = f"Found {len(recs)} exporter(s) for '{service_type}'."

    return recs, notes


def build_exporter_manifests(
    exporter_type: str,
    namespace: str,
    service_name: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Build Kubernetes manifests for an exporter.

    Returns:
        List of Kubernetes manifest dictionaries.
    """
    exp = SUPPORTED_EXPORTERS.get(exporter_type)
    if not exp:
        raise ValueError(f"Unknown exporter_type '{exporter_type}'")

    cfg = config or {}
    scope = cfg.get("scope", exp.default_scope or "deployment")
    # Sanitize name for Kubernetes RFC 1123 compliance (no underscores allowed)
    name = (service_name or exporter_type).replace("_", "-")
    k8s_container_name = exporter_type.replace("_", "-")
    labels = {"app": name, "exporter": exporter_type}
    
    # Use metrics port or first port found
    port = cfg.get("port", exp.default_ports.get("metrics", 9100))
    image = cfg.get("image", exp.image or f"{exporter_type}:latest")

    manifests: List[Dict[str, Any]] = []

    # Map env vars to args based on config_model
    args: List[str] = []
    env_vars: List[Dict[str, str]] = []
    env_input = cfg.get("env", {})
    if isinstance(env_input, list):
        env_vars = env_input
    elif isinstance(env_input, dict):
        # Map env dict to args if maps_to_flag exists, otherwise to env vars
        for key, val in env_input.items():
            mapped_to_arg = False
            for field in exp.config_model.required + exp.config_model.optional:
                if field.name == key and field.maps_to_flag:
                    args.append(f"{field.maps_to_flag}={val}")
                    mapped_to_arg = True
                    break
            if not mapped_to_arg:
                env_vars.append({"name": key, "value": str(val)})

    container: Dict[str, Any] = {
        "name": k8s_container_name,
        "image": image,
        "ports": [{"containerPort": port, "name": "metrics"}],
    }
    
    # Add other default ports if any
    for p_name, p_val in exp.default_ports.items():
        if p_name != "metrics":
            container["ports"].append({"containerPort": p_val, "name": p_name})

    if args:
        container["args"] = args
    if env_vars:
        container["env"] = env_vars

    volumes: List[Dict[str, Any]] = []
    volume_mounts: List[Dict[str, Any]] = []

    # Handle ConfigMap
    if exp.k8s_nuances.requires_configmap:
        cm_name = f"{name}-config"
        # Generate a placeholder config if none provided
        config_data = cfg.get("config_data", exp.default_config_data or "# Auto-generated placeholder config\n")
        manifests.append({
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": cm_name, "labels": labels, "namespace": namespace},
            "data": {"config.yml": config_data}
        })
        volumes.append({
            "name": "config-volume",
            "configMap": {"name": cm_name}
        })
        mount_path = exp.k8s_nuances.configmap_mount_path or "/etc/config"
        volume_mounts.append({
            "name": "config-volume",
            "mountPath": mount_path
        })
        
    if volume_mounts:
        container["volumeMounts"] = volume_mounts

    pod_template: Dict[str, Any] = {
        "metadata": {"labels": labels},
        "spec": {"containers": [container]},
    }
    if volumes:
        pod_template["spec"]["volumes"] = volumes

    # Handle RBAC
    if exp.k8s_nuances.requires_rbac:
        sa_name = f"{name}-sa"
        manifests.extend([
            {
                "apiVersion": "v1",
                "kind": "ServiceAccount",
                "metadata": {"name": sa_name, "namespace": namespace, "labels": labels}
            },
            {
                "apiVersion": "rbac.authorization.k8s.io/v1",
                "kind": "ClusterRole",
                "metadata": {"name": f"{name}-role", "labels": labels},
                "rules": [
                    {"apiGroups": [""], "resources": ["nodes", "nodes/proxy", "services", "endpoints", "pods"], "verbs": ["get", "list", "watch"]},
                    {"apiGroups": ["extensions", "networking.k8s.io"], "resources": ["ingresses"], "verbs": ["get", "list", "watch"]},
                    {"apiGroups": ["apps"], "resources": ["daemonsets", "deployments", "replicasets", "statefulsets"], "verbs": ["get", "list", "watch"]}
                ]
            },
            {
                "apiVersion": "rbac.authorization.k8s.io/v1",
                "kind": "ClusterRoleBinding",
                "metadata": {"name": f"{name}-rolebinding", "labels": labels},
                "roleRef": {"apiGroup": "rbac.authorization.k8s.io", "kind": "ClusterRole", "name": f"{name}-role"},
                "subjects": [{"kind": "ServiceAccount", "name": sa_name, "namespace": namespace}]
            }
        ])
        pod_template["spec"]["serviceAccountName"] = sa_name

    # Handle Workload
    if scope == "daemonset":
        workload = {
            "apiVersion": "apps/v1",
            "kind": "DaemonSet",
            "metadata": {"name": name, "labels": labels, "namespace": namespace},
            "spec": {
                "selector": {"matchLabels": labels},
                "template": pod_template,
            },
        }
    else:
        workload = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": name, "labels": labels, "namespace": namespace},
            "spec": {
                "replicas": cfg.get("replicas", 1),
                "selector": {"matchLabels": labels},
                "template": pod_template,
            },
        }
    manifests.append(workload)

    # Handle Service
    svc = {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {"name": name, "labels": labels, "namespace": namespace},
        "spec": {
            "selector": labels,
            "ports": [{"port": port, "targetPort": port, "name": "metrics"}],
        },
    }
    # Expose extra UDP ports if requested (e.g. statsd)
    if exp.k8s_nuances.requires_udp_service:
        for p_name, p_val in exp.default_ports.items():
            if p_name != "metrics":
                svc["spec"]["ports"].append({"port": p_val, "targetPort": p_val, "name": p_name, "protocol": "UDP"})

    manifests.append(svc)

    return manifests


def build_servicemonitor_manifest(
    name: str,
    namespace: str,
    service_name: str,
    port_name: str = "metrics",
    path: str = "/metrics",
    interval: str = "30s",
    labels: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Build a ServiceMonitor CRD manifest.

    Returns:
        ServiceMonitor manifest dict
    """
    sm_labels = {"app": service_name}
    if labels:
        sm_labels.update(labels)

    return {
        "apiVersion": "monitoring.coreos.com/v1",
        "kind": "ServiceMonitor",
        "metadata": {
            "name": name,
            "namespace": namespace,
            "labels": sm_labels,
        },
        "spec": {
            "selector": {
                "matchLabels": {"app": service_name},
            },
            "endpoints": [
                {
                    "port": port_name,
                    "path": path,
                    "interval": interval,
                }
            ],
        },
    }
