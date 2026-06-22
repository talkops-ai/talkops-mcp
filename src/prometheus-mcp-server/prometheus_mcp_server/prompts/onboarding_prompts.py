"""Application onboarding guided workflow prompts."""

from mcp.types import PromptMessage, TextContent
from prometheus_mcp_server.prompts.base import BasePrompt


class OnboardingPrompts(BasePrompt):
    """Onboarding workflow prompts for Prometheus monitoring."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.prompt(
            name="prom-k8s-app-onboarding-guided",
            description="Guided workflow for instrumenting and onboarding a Kubernetes application to Prometheus",
        )
        def prom_k8s_app_onboarding(
            backend_id: str,
            language: str = "python",
            namespace: str = "default",
            service_name: str = "my-app",
        ) -> list[PromptMessage]:
            prompt_text = f"""# 🚀 Prometheus K8s App Onboarding Guide

## Context
- **Backend**: {backend_id}
- **Language**: {language}
- **Namespace**: {namespace}
- **Service**: {service_name}

---

## Phase 1: Verify Backend

1. **Check backend health**:
   ```
   Resource: prom://system/backends/{backend_id}
   ```

---

## Phase 2: Choose Instrumentation Strategy

1. **Get recommendation**:
   ```
   Tool: prom_recommend_instrumentation(workload_type="custom_app", language="{language}", environment="kubernetes")
   ```

---

## Phase 3: Validate Metrics Endpoint

After the user deploys the instrumented application:

1. **Test the /metrics endpoint**:
   ```
   Tool: prom_test_endpoint(endpoint_url="http://{service_name}.{namespace}:8080/metrics")
   ```

---

## Phase 4: Configure Prometheus Scraping

> **IMPORTANT**: Use the exact Kubernetes Service name, not the app name.
> First run: `kubectl get svc -n {namespace}` to verify the real service name.
> If Prometheus lives in a different namespace (e.g. `monitoring`), use `target_namespace`.

1. **Apply ServiceMonitor** (same namespace):
   ```
   Tool: prom_apply_servicemonitor(namespace="{namespace}", service_name="{service_name}")
   ```

   **OR cross-namespace** (service in `{namespace}`, Prometheus in `monitoring`):
   ```
   Tool: prom_apply_servicemonitor(namespace="monitoring", service_name="{service_name}", target_namespace="{namespace}")
   ```

   **Cleanup stale monitors** if retrying:
   ```
   Tool: prom_delete_servicemonitor(monitor_name="{service_name}-monitor", namespace="monitoring")
   ```

---

## Phase 5: Verify Metrics Ingestion

1. **Discover new metrics**:
   ```
   Tool: prom_explore_labels(backend_id="{backend_id}", metric_name="http_requests_total")
   ```

2. **Run a test query**:
   ```
   Tool: prom_query_instant(backend_id="{backend_id}", query="rate(http_requests_total[5m])")
   ```

---

## ✅ Onboarding Complete!

Your application is now instrumented and scraped by Prometheus.
"""
            return [
                PromptMessage(role="user", content=TextContent(type="text", text=prompt_text))
            ]

        @mcp_instance.prompt(
            name="prom-k8s-exporter-onboarding-guided",
            description="Guided workflow for onboarding a third-party system via exporters on Kubernetes",
        )
        def prom_k8s_exporter_onboarding(
            backend_id: str,
            workload_type: str = "postgres",
            namespace: str = "default",
        ) -> list[PromptMessage]:
            prompt_text = f"""# 🚀 Prometheus Exporter Onboarding Guide

## Context
- **Backend**: {backend_id}
- **Workload**: {workload_type}
- **Namespace**: {namespace}

---

## Phase 1: Get Exporter Recommendation

1. **Recommend exporter**:
   ```
   Tool: prom_recommend_exporter(service_type="{workload_type}", environment="kubernetes")
   ```

---

## Phase 2: Install Exporter

1. **Deploy exporter**:
   ```
   Tool: prom_install_exporter(exporter_type="{workload_type}_exporter", namespace="{namespace}")
   ```

---

## Phase 3: Validate Exporter

1. **Test endpoint**:
   ```
   Tool: prom_test_endpoint(endpoint_url="http://{workload_type}_exporter.{namespace}:9187/metrics")
   ```

---

## Phase 4: Configure Scraping

1. **Apply ServiceMonitor**:
   ```
   Tool: prom_apply_servicemonitor(namespace="{namespace}", service_name="{workload_type}_exporter")
   ```

---

## Phase 5: Verify

1. **Verify in Prometheus**:
   ```
   Tool: prom_verify_exporter(backend_id="{backend_id}", endpoint_url="http://{workload_type}_exporter.{namespace}:9187/metrics", job="{workload_type}_exporter")
   ```

---

## ✅ Exporter Onboarding Complete!
"""
            return [
                PromptMessage(role="user", content=TextContent(type="text", text=prompt_text))
            ]

        @mcp_instance.prompt(
            name="prom-vm-legacy-onboarding-guided",
            description="Guided workflow for onboarding applications on VM/legacy (non-Kubernetes) environments",
        )
        def prom_vm_legacy_onboarding(
            backend_id: str,
            workload_type: str = "custom_app",
            language: str = "python",
            target_host: str = "myhost",
            target_port: str = "8080",
        ) -> list[PromptMessage]:
            prompt_text = f"""# 🚀 Prometheus VM/Legacy Onboarding Guide

## Context
- **Backend**: {backend_id}
- **Workload**: {workload_type}
- **Language**: {language}
- **Target**: {target_host}:{target_port}

---

## Phase 1: Choose Instrumentation Strategy

1. **Get recommendation**:
   ```
   Tool: prom_recommend_instrumentation(workload_type="{workload_type}", language="{language}", environment="vm")
   ```

---

## Phase 2: Instrument or Install Exporter

### For Custom Applications:
1. Instrument the application with the appropriate Prometheus client library.
2. Deploy the instrumented application on your VM.

### For Third-Party Systems:
1. Download and install the appropriate exporter binary.
2. Configure it as a systemd service:
   ```
   [Unit]
   Description=Prometheus Exporter
   After=network.target

   [Service]
   ExecStart=/usr/local/bin/<exporter> --web.listen-address=:{target_port}
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```

---

## Phase 3: Validate Metrics Endpoint

1. **Test the /metrics endpoint**:
   ```
   Tool: prom_test_endpoint(endpoint_url="http://{target_host}:{target_port}/metrics")
   ```

---

## Phase 4: Configure Prometheus Scraping (file_sd)

1. **Add target to file_sd_configs**:
   ```
   Tool: prom_manage_file_sd(file_sd_path="/etc/prometheus/file_sd/targets.json", targets=["{target_host}:{target_port}"], target_labels={{"job": "{workload_type}"}}, backend_id="{backend_id}")
   ```

---

## Phase 5: Verify Metrics Ingestion

1. **Check target is up**:
   ```
   Tool: prom_query_instant(backend_id="{backend_id}", query="up{{job='{workload_type}'}}")
   ```

---

## ✅ VM/Legacy Onboarding Complete!
"""
            return [
                PromptMessage(role="user", content=TextContent(type="text", text=prompt_text))
            ]

