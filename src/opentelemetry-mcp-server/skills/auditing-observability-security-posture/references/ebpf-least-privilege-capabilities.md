# eBPF Agent Least-Privilege Capabilities Reference (`SEC_PRIVILEGED_CONTAINER`)

## Table of Contents

1. [Why `privileged: true` Is an Anti-Pattern](#1-why-privileged-true-is-an-anti-pattern)
2. [Required Linux Capabilities for OBI / Beyla](#2-required-linux-capabilities-for-obi--beyla)
3. [Host Namespace & Volume Mount Hardening](#3-host-namespace--volume-mount-hardening)
4. [Auditing eBPF DaemonSets with `otel_audit_security_posture`](#4-auditing-ebpf-daemonsets-with-otel_audit_security_posture)

---

## 1. Why `privileged: true` Is an Anti-Pattern

Running an eBPF DaemonSet (`obi` or `beyla`) with `securityContext.privileged: true` grants full root equivalence over the host node, including access to all `/dev` block devices, kernel modules (`CAP_SYS_MODULE`), and host network interfaces.
On Linux kernels `>= 5.8`, `CAP_BPF` and `CAP_PERFMON` allow loading eBPF programs without `CAP_SYS_ADMIN` or `privileged: true`.

---

## 2. Required Linux Capabilities for OBI / Beyla

Drop `ALL` capabilities and add only the minimal required set:

```yaml
securityContext:
  privileged: false
  runAsUser: 0
  allowPrivilegeEscalation: false
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

---

## 3. Host Namespace & Volume Mount Hardening

- `hostPID: true`: Required so OBI can scan `/proc/<pid>` to discover target service binaries on the same node.
- `hostNetwork`: Set `hostNetwork: false` unless L4 host-network socket correlation is explicitly required.
- Mount `/sys/kernel/security` and `/sys/fs/cgroup` as `readOnly: true`.

---

## 4. Auditing eBPF DaemonSets with `otel_audit_security_posture`

When `otel_audit_security_posture` inspects the cluster:
- It discovers eBPF DaemonSets matching `app.kubernetes.io/name in (obi, beyla, opentelemetry-ebpf-instrumentation)`.
- If any container sets `securityContext.privileged: true`, it emits `SEC_PRIVILEGED_CONTAINER` with remediation guidance to switch to explicit `BPF` and `PERFMON` capabilities.
