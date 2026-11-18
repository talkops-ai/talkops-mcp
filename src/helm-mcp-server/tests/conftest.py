"""Shared pytest fixtures for Helm MCP Server unit and integration tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional, Set
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from helm_mcp_server.config import HelmConfig, KubernetesConfig, ServerConfig
from helm_mcp_server.server.bootstrap import ServerBootstrap
from helm_mcp_server.services.helm_service import HelmService
from helm_mcp_server.services.kubernetes_service import KubernetesService

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "helm"


def _load_fixture(name: str) -> Any:
    """Load and parse a JSON fixture from tests/fixtures/helm/."""
    with open(FIXTURES_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def _text(content: Any) -> str:
    """Extract text from a FastMCP ContentBlock."""
    return str(getattr(content, "text", content))


def get_text(result: Any) -> str:
    """Extract text from a FastMCP 2.13+ CallToolResult or ResourceResult list."""
    if hasattr(result, "content") and result.content:
        return _text(result.content[0])
    if isinstance(result, list) and result:
        return _text(result[0])
    return str(result)


class HelmSubprocessController:
    """Configurable controller for mocked Helm CLI subprocess execution."""

    def __init__(self) -> None:
        self.commands: List[List[str]] = []
        self.existing_releases: Set[str] = {"prod/my-postgres", "default/my-postgres", "monitoring/kube-prom"}
        self.configured_repos: List[Dict[str, str]] = _load_fixture("repo_list.json")
        self.fail_on_subcommands: Dict[str, str] = {}
        self.custom_outputs: Dict[str, str] = {}
        self.release_status_override: Optional[str] = None

    def resolve_output(self, cmd: List[str]) -> tuple[int, str, str]:
        """Determine (returncode, stdout, stderr) for a given helm CLI command."""
        self.commands.append(list(cmd))

        if not cmd or cmd[0] != "helm":
            return 1, "", f"Unexpected binary: {cmd}"

        args = cmd[1:]
        subkey = " ".join(args[:2]) if len(args) >= 2 else (args[0] if args else "")

        for trigger, err_msg in self.fail_on_subcommands.items():
            if trigger in " ".join(args):
                return 1, "", err_msg

        if subkey in self.custom_outputs:
            return 0, self.custom_outputs[subkey], ""

        # helm repo list
        if args[:2] == ["repo", "list"]:
            if not self.configured_repos:
                return 1, "", "Error: no repositories to show"
            return 0, json.dumps(self.configured_repos), ""

        # helm repo add <name> <url>
        if args[:2] == ["repo", "add"]:
            repo_name = args[2] if len(args) > 2 else "custom"
            repo_url = args[3] if len(args) > 3 else "https://example.com/charts"
            self.configured_repos.append({"name": repo_name, "url": repo_url})
            return 0, f'"{repo_name}" has been added to your repositories', ""

        # helm repo update
        if args[:2] == ["repo", "update"]:
            return 0, "Successfully got an update from the chart repository", ""

        # helm search repo <query>
        if args[:2] == ["search", "repo"]:
            charts = _load_fixture("search_charts.json")
            return 0, json.dumps(charts), ""

        # helm show chart <ref>
        if args[:2] == ["show", "chart"]:
            chart_ref = args[2] if len(args) > 2 else ""
            if "nonexistent" in chart_ref:
                return 1, "", f'Error: chart "{chart_ref}" not found'
            info = _load_fixture("chart_info.json")
            return 0, yaml.safe_dump(info, sort_keys=False), ""

        # helm show values <ref>
        if args[:2] == ["show", "values"]:
            chart_ref = args[2] if len(args) > 2 else ""
            if "nonexistent" in chart_ref:
                return 1, "", f'Error: chart "{chart_ref}" not found'
            values = _load_fixture("chart_values.json")
            return 0, yaml.safe_dump(values, sort_keys=False), ""

        # helm show readme <ref>
        if args[:2] == ["show", "readme"]:
            chart_ref = args[2] if len(args) > 2 else ""
            if "nonexistent" in chart_ref:
                return 1, "", f'Error: chart "{chart_ref}" not found'
            readme_data = _load_fixture("chart_readme.json")
            return 0, readme_data["readme"], ""

        # helm list
        if args[0] == "list":
            releases = _load_fixture("release_list.json")
            if "-n" in args:
                ns = args[args.index("-n") + 1]
                releases = [r for r in releases if r.get("namespace") == ns]
            if "--failed" in args:
                releases = [r for r in releases if r.get("status") == "failed"]
            elif "--deployed" in args:
                releases = [r for r in releases if r.get("status") == "deployed"]
            return 0, json.dumps(releases), ""

        # helm status <release>
        if args[0] == "status":
            release_name = args[1] if len(args) > 1 else "my-postgres"
            ns = args[args.index("-n") + 1] if "-n" in args else "default"
            key = f"{ns}/{release_name}"
            if key not in self.existing_releases:
                return 1, "", f'Error: release: not found: "{release_name}"'
            status_payload = _load_fixture("release_status.json")
            status_payload["name"] = release_name
            status_payload["namespace"] = ns
            if self.release_status_override:
                status_payload["info"]["status"] = self.release_status_override
            return 0, json.dumps(status_payload), ""

        # helm history <release>
        if args[0] == "history":
            release_name = args[1] if len(args) > 1 else "my-postgres"
            ns = args[args.index("-n") + 1] if "-n" in args else "default"
            if f"{ns}/{release_name}" not in self.existing_releases:
                return 1, "", f'Error: release: not found: "{release_name}"'
            history = _load_fixture("release_history.json")
            return 0, json.dumps(history), ""

        # helm get values <release>
        if args[:2] == ["get", "values"]:
            release_name = args[2] if len(args) > 2 else "my-postgres"
            ns = args[args.index("-n") + 1] if "-n" in args else "default"
            if f"{ns}/{release_name}" not in self.existing_releases:
                return 1, "", f'Error: release: not found: "{release_name}"'
            values = _load_fixture("release_values.json")
            return 0, json.dumps(values), ""

        # helm get manifest <release>
        if args[:2] == ["get", "manifest"]:
            release_name = args[2] if len(args) > 2 else "my-postgres"
            ns = args[args.index("-n") + 1] if "-n" in args else "default"
            if f"{ns}/{release_name}" not in self.existing_releases:
                return 1, "", f'Error: release: not found: "{release_name}"'
            manifest_data = _load_fixture("rendered_manifests.json")
            return 0, manifest_data["current_manifest"], ""

        # helm template <release> <chart>
        if args[0] == "template":
            manifest_data = _load_fixture("rendered_manifests.json")
            raw_manifest = manifest_data["current_manifest"]
            # If a -f <values_file> was passed, reflect image tag or replica overrides in rendered YAML
            if "-f" in args:
                values_path = args[args.index("-f") + 1]
                try:
                    with open(values_path, encoding="utf-8") as vf:
                        vdict = yaml.safe_load(vf) or {}
                    if isinstance(vdict, dict):
                        tag = vdict.get("image", {}).get("tag") if isinstance(vdict.get("image"), dict) else None
                        if tag:
                            raw_manifest = raw_manifest.replace(
                                "docker.io/bitnami/postgresql:16.2.0",
                                f"docker.io/bitnami/postgresql:{tag}",
                            )
                        replicas = vdict.get("replicas")
                        if replicas is not None:
                            raw_manifest = raw_manifest.replace("replicas: 1", f"replicas: {replicas}")
                except Exception:
                    pass
            return 0, raw_manifest, ""

        # helm install <release> <chart>
        if args[0] == "install":
            release_name = args[1] if len(args) > 1 else "new-release"
            ns = args[args.index("-n") + 1] if "-n" in args else "default"
            self.existing_releases.add(f"{ns}/{release_name}")
            payload = _load_fixture("install_output.json")
            payload["name"] = release_name
            payload["namespace"] = ns
            return 0, json.dumps(payload), ""

        # helm upgrade <release> <chart>
        if args[0] == "upgrade":
            release_name = args[1] if len(args) > 1 else "my-postgres"
            ns = args[args.index("-n") + 1] if "-n" in args else "default"
            if f"{ns}/{release_name}" not in self.existing_releases:
                return 1, "", f'Error: UPGRADE FAILED: "{release_name}" has no deployed releases'
            payload = _load_fixture("upgrade_output.json")
            payload["name"] = release_name
            payload["namespace"] = ns
            return 0, json.dumps(payload), ""

        # helm rollback <release> [revision]
        if args[0] == "rollback":
            release_name = args[1] if len(args) > 1 else "my-postgres"
            ns = args[args.index("-n") + 1] if "-n" in args else "default"
            if f"{ns}/{release_name}" not in self.existing_releases:
                return 1, "", f'Error: release: not found: "{release_name}"'
            return 0, "Rollback was a success! Happy Helming!", ""

        # helm uninstall <release>
        if args[0] == "uninstall":
            release_name = args[1] if len(args) > 1 else "my-postgres"
            ns = args[args.index("-n") + 1] if "-n" in args else "default"
            if f"{ns}/{release_name}" not in self.existing_releases:
                return 1, "", f'Error: uninstall: Release not loaded: {release_name}: release: not found'
            self.existing_releases.discard(f"{ns}/{release_name}")
            return 0, f'release "{release_name}" uninstalled', ""

        return 0, "{}", ""


@pytest.fixture
def mock_helm_subprocess() -> Any:
    """Patch asyncio.create_subprocess_exec and is_helm_installed with HelmSubprocessController."""
    controller = HelmSubprocessController()

    async def _fake_exec(*cmd: str, **kwargs: Any) -> Any:
        returncode, stdout_str, stderr_str = controller.resolve_output(list(cmd))
        proc = MagicMock()
        proc.returncode = returncode
        proc.communicate = AsyncMock(
            return_value=(stdout_str.encode("utf-8"), stderr_str.encode("utf-8"))
        )
        proc.kill = MagicMock()
        return proc

    with (
        patch("helm_mcp_server.services.helm_service.is_helm_installed", return_value=True),
        patch("asyncio.create_subprocess_exec", side_effect=_fake_exec),
    ):
        yield controller


def _make_healthy_deployment(name: str = "my-postgres", replicas: int = 1) -> Any:
    """Build a mock healthy Kubernetes Deployment object."""
    return SimpleNamespace(
        metadata=SimpleNamespace(name=name),
        spec=SimpleNamespace(replicas=replicas),
        status=SimpleNamespace(
            updated_replicas=replicas,
            ready_replicas=replicas,
            available_replicas=replicas,
            unavailable_replicas=0,
            conditions=[
                SimpleNamespace(
                    type="Progressing",
                    status="True",
                    reason="NewReplicaSetAvailable",
                    message=f"ReplicaSet '{name}-abc' has successfully progressed.",
                )
            ],
        ),
    )


def _make_healthy_pod(name: str = "my-postgres-0") -> Any:
    """Build a mock healthy Kubernetes Pod object."""
    return SimpleNamespace(
        metadata=SimpleNamespace(name=name),
        status=SimpleNamespace(
            phase="Running",
            container_statuses=[
                SimpleNamespace(
                    name="postgresql",
                    restart_count=0,
                    state=SimpleNamespace(waiting=None, terminated=None),
                    last_state=SimpleNamespace(terminated=None),
                )
            ],
            init_container_statuses=[],
            conditions=[
                SimpleNamespace(type="PodScheduled", status="True", reason=None, message=None),
                SimpleNamespace(type="Ready", status="True", reason=None, message=None),
            ],
        ),
    )


@pytest.fixture
def mock_k8s_module(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Mock kubernetes Python client in sys.modules for deterministic cluster tests."""
    mock_k8s = MagicMock()
    mock_client = MagicMock()
    mock_config = MagicMock()

    # Contexts
    contexts = [
        {
            "name": "dev-cluster",
            "context": {"cluster": "dev-eks", "user": "dev-admin", "namespace": "default"},
        },
        {
            "name": "prod-cluster",
            "context": {"cluster": "prod-eks", "user": "prod-admin", "namespace": "prod"},
        },
    ]
    mock_config.list_kube_config_contexts.return_value = (contexts, contexts[0])
    mock_config.load_kube_config = MagicMock()
    mock_config.load_incluster_config = MagicMock()
    mock_config.new_client_from_config = MagicMock(return_value=MagicMock(name="api_client"))

    # CoreV1Api
    core_v1 = MagicMock()
    core_v1.list_node.return_value = SimpleNamespace(
        items=[
            SimpleNamespace(metadata=SimpleNamespace(name="node-1")),
            SimpleNamespace(metadata=SimpleNamespace(name="node-2")),
        ]
    )
    core_v1.list_namespace.return_value = SimpleNamespace(
        items=[
            SimpleNamespace(metadata=SimpleNamespace(name="default")),
            SimpleNamespace(metadata=SimpleNamespace(name="prod")),
            SimpleNamespace(metadata=SimpleNamespace(name="argocd")),
        ]
    )
    core_v1.get_api_resources.return_value = SimpleNamespace(
        resources=[
            SimpleNamespace(kind="Pod", name="pods"),
            SimpleNamespace(kind="Service", name="services"),
            SimpleNamespace(kind="ConfigMap", name="configmaps"),
            SimpleNamespace(kind="Secret", name="secrets"),
            SimpleNamespace(kind="PersistentVolumeClaim", name="persistentvolumeclaims"),
        ]
    )
    core_v1.list_namespaced_pod.return_value = SimpleNamespace(
        items=[_make_healthy_pod("my-postgres-0")]
    )

    # AppsV1Api
    apps_v1 = MagicMock()
    apps_v1.get_api_resources.return_value = SimpleNamespace(
        resources=[
            SimpleNamespace(kind="Deployment", name="deployments"),
            SimpleNamespace(kind="StatefulSet", name="statefulsets"),
            SimpleNamespace(kind="DaemonSet", name="daemonsets"),
        ]
    )
    apps_v1.list_namespaced_deployment.return_value = SimpleNamespace(
        items=[_make_healthy_deployment("my-postgres", replicas=1)]
    )
    apps_v1.list_namespaced_stateful_set.return_value = SimpleNamespace(items=[])

    # VersionApi
    version_api = MagicMock()
    version_api.get_code.return_value = SimpleNamespace(git_version="v1.29.2-eks-1234")

    # ApisApi
    apis_api = MagicMock()
    apis_api.get_api_versions.return_value = SimpleNamespace(
        groups=[
            SimpleNamespace(
                name="networking.k8s.io",
                preferred_version=SimpleNamespace(group_version="networking.k8s.io/v1"),
                versions=[SimpleNamespace(group_version="networking.k8s.io/v1")],
            ),
            SimpleNamespace(
                name="cert-manager.io",
                preferred_version=SimpleNamespace(group_version="cert-manager.io/v1"),
                versions=[SimpleNamespace(group_version="cert-manager.io/v1")],
            ),
        ]
    )

    # ApiextensionsV1Api
    ext_api = MagicMock()
    ext_api.list_custom_resource_definition.return_value = SimpleNamespace(
        items=[
            SimpleNamespace(
                metadata=SimpleNamespace(name="certificates.cert-manager.io"),
                spec=SimpleNamespace(names=SimpleNamespace(kind="Certificate")),
            )
        ]
    )

    mock_client.CoreV1Api.return_value = core_v1
    mock_client.AppsV1Api.return_value = apps_v1
    mock_client.VersionApi.return_value = version_api
    mock_client.ApisApi.return_value = apis_api
    mock_client.ApiextensionsV1Api.return_value = ext_api

    mock_k8s.client = mock_client
    mock_k8s.config = mock_config

    monkeypatch.setitem(sys.modules, "kubernetes", mock_k8s)
    monkeypatch.setitem(sys.modules, "kubernetes.client", mock_client)
    monkeypatch.setitem(sys.modules, "kubernetes.config", mock_config)

    return SimpleNamespace(
        kubernetes=mock_k8s,
        client=mock_client,
        config=mock_config,
        core_v1=core_v1,
        apps_v1=apps_v1,
        version_api=version_api,
        apis_api=apis_api,
        ext_api=ext_api,
    )


@pytest.fixture
def write_config() -> ServerConfig:
    """Return a ServerConfig with write operations enabled (`allow_write=True`)."""
    return ServerConfig(
        allow_write=True,
        toolsets=["all"],
        helm=HelmConfig(timeout=30),
        kubernetes=KubernetesConfig(kubeconfig="/tmp/fake-kubeconfig"),
    )


@pytest.fixture
def readonly_config() -> ServerConfig:
    """Return the default read-only ServerConfig (`allow_write=False`)."""
    return ServerConfig(
        allow_write=False,
        toolsets=["all"],
        helm=HelmConfig(timeout=30),
        kubernetes=KubernetesConfig(kubeconfig="/tmp/fake-kubeconfig"),
    )


@pytest.fixture
def k8s_service(write_config: ServerConfig, mock_k8s_module: Any) -> KubernetesService:
    """Return a KubernetesService wired to the mocked kubernetes module."""
    return KubernetesService(write_config)


@pytest.fixture
def helm_service(
    write_config: ServerConfig,
    k8s_service: KubernetesService,
    mock_helm_subprocess: HelmSubprocessController,
) -> HelmService:
    """Return a HelmService wired to write_config, k8s_service, and mocked helm subprocess."""
    return HelmService(write_config, k8s_service=k8s_service)


@pytest.fixture
def bootstrapped_mcp(
    write_config: ServerConfig,
    mock_helm_subprocess: HelmSubprocessController,
    mock_k8s_module: Any,
) -> Any:
    """Return a fully bootstrapped FastMCP instance with write access enabled."""
    mcp, _ = ServerBootstrap.initialize(write_config)
    return mcp


@pytest.fixture
def readonly_mcp(
    readonly_config: ServerConfig,
    mock_helm_subprocess: HelmSubprocessController,
    mock_k8s_module: Any,
) -> Any:
    """Return a fully bootstrapped FastMCP instance in default read-only mode."""
    mcp, _ = ServerBootstrap.initialize(readonly_config)
    return mcp
