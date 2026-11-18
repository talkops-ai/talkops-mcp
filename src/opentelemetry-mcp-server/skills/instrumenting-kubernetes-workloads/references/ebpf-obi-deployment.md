# OpenTelemetry eBPF Instrumentation (OBI) Deployment Reference

## Table of Contents

1. [What Is OpenTelemetry eBPF Instrumentation (OBI)](#1-what-is-opentelemetry-ebpf-instrumentation-obi)
2. [Linux Kernel & Cgroup Prerequisites](#2-linux-kernel--cgroup-prerequisites)
3. [Least-Privilege Linux Capabilities (`SEC_PRIVILEGED_CONTAINER`)](#3-least-privilege-linux-capabilities-sec_privileged_container)
4. [Kubernetes Metadata Decoration & Target Selection](#4-kubernetes-metadata-decoration--target-selection)
5. [Auditing OBI DaemonSets with `otel_audit_security_posture`](#5-auditing-obi-daemonsets-with-otel_audit_security_posture)

---

## 1. What Is OpenTelemetry eBPF Instrumentation (OBI)

OpenTelemetry eBPF Instrumentation (OBI, donated from Grafana Beyla) attaches eBPF uprobes and kprobes to running processes to capture HTTP/1.1, HTTP/2, gRPC, SQL, Redis, and Kafka spans and RED metrics without modifying application code or restarting workloads.

Ideal use cases:
- **Go**, **Rust**, **C++**, or **native binaries** where language-agent injection is unsupported or requires per-binary offsets.
- Multi-language clusters needing immediate baseline RED metrics and distributed traces without rolling restarts.
- TLS traffic inspection (`uprobes` on OpenSSL, BoringSSL, Go `crypto/tls`) before encryption.

---

## 2. Linux Kernel & Cgroup Prerequisites

- **Linux Kernel**: `>= 5.8` (with BTF — BPF Type Format enabled at `/sys/kernel/btf/vmlinux`).
- **PID Namespace**: `hostPID: true` is required in DaemonSet mode so OBI can discover and attach uprobes to container processes across the node.

---

## 3. Least-Privilege Linux Capabilities (`SEC_PRIVILEGED_CONTAINER`)

Do **not** deploy OBI with `privileged: true` unless running on legacy kernels (`< 5.8`). `otel_audit_security_posture` flags `privileged: true` with `SEC_PRIVILEGED_CONTAINER`.

Instead, configure explicit least-privilege Linux capabilities:

```yaml
securityContext:
  privileged: false
  runAsUser: 0
  capabilities:
    drop:
      - ALL
    add:
      - BPF
      - PERFMON
      - SYS_PTRACE
      - NET_RAW
      - CHECKPOINT_RESTORE
      - DAC_READ_SEARCH
      - SYS_RESOURCE
```

| Capability | Purpose |
|---|---|
| `BPF` | Load eBPF programs and maps into the kernel |
| `PERFMON` | Attach kprobes, uprobes, and tracepoints |
| `SYS_PTRACE` | Inspect `/proc/<pid>/exe` and symbol tables for uprobe attachment |
| `NET_RAW` | Capture socket-level L4/L7 traffic correlation |
| `DAC_READ_SEARCH` | Read container binary headers across filesystem namespaces |
| `SYS_RESOURCE` | Adjust `RLIMIT_MEMLOCK` for eBPF ring buffers |

---

## 4. Kubernetes Metadata Decoration & Target Selection

Enable Kubernetes pod metadata enrichment in OBI so emitted spans and metrics carry `k8s.pod.name`, `k8s.namespace.name`, and `k8s.deployment.name`:

```yaml
env:
  - name: OTEL_EBPF_KUBE_METADATA_ENABLE
    value: "true"
  - name: OTEL_EBPF_OPEN_PORT
    value: "80,443,8080-8090,9090"
  - name: OTEL_EXPORTER_OTLP_ENDPOINT
    value: "http://otel-agent.opentelemetry-system.svc.cluster.local:4317"
```

Use `scripts/render_obi_manifest.py` to generate a production-hardened OBI DaemonSet + ServiceAccount + ClusterRole + ClusterRoleBinding bundle for GitOps or Helm deployment.

---

## 5. Auditing OBI DaemonSets with `otel_audit_security_posture`

After deploying OBI via GitOps/Helm:
1. Run `otel_survey_cluster` to verify the eBPF agent DaemonSet is detected (`app.kubernetes.io/name=obi` or `app.kubernetes.io/name=beyla`).
2. Run `otel_audit_security_posture` in the OBI namespace to verify that `SEC_PRIVILEGED_CONTAINER` is not raised and RBAC bindings follow least privilege.
