---
name: reviewing-helm-release-security
description: Audits Helm chart values and rendered Kubernetes manifests for security misconfigurations including privileged containers, root execution, mutable image tags, missing resource limits, hostPath mounts, and hardcoded secrets. Use before deploying to production or when conducting a security posture review of a Helm release.
---

# Reviewing Helm Release Security Procedure

## Overview

Execute this security audit workflow before deploying or upgrading production Helm workloads, or when asked to audit an existing release.

---

## Phase 1: Retrieve Target Manifests & Values

> **MCP-First Inspection:** Retrieve chart schemas, rendered manifests, and live release state via the Helm MCP server (`helm_render_manifests`, `helm://charts/...`, `helm://releases/...`) rather than running raw `kubectl` or `helm pull` shell commands. If a required chart repository is not yet registered in `helm://repositories`, call `helm_ensure_repository` first.

1. **For a proposed (pre-deploy) release:**
   - Call `helm_render_manifests(chart_ref="<repo>/<chart>", namespace="<ns>", values={...}, version="<version>", include_full=True)`.
   - Save the rendered YAML to a temporary file for local deterministic scanning.
2. **For an already deployed release:**
   - Read resource `helm://releases/{namespace}/{release}/values` and `helm://releases/{namespace}/{release}/manifest`.

---

## Phase 2: Run Deterministic Security Scanner

1. Execute the bundled security scanner script against the rendered Kubernetes manifests:
   ```bash
   python3 ./scripts/scan_manifest_security.py <rendered-manifests.yaml>
   ```
2. The script outputs a structured JSON report containing `passed` (`bool`), `summary` (`high`, `medium`, `low` counts), and `findings` (each with `severity`, `resource`, `rule`, and `remediation`).

---

## Phase 3: Evaluate Findings & Remediate

1. Consult [security-checklist.md](./references/security-checklist.md) to map each finding to the corresponding Helm values override, and **always organize your audit report grouped by severity (`HIGH`, `MEDIUM`, `LOW`)** covering Pod Security Standards, image pinning, secrets/redaction, RBAC, networking, and resource limits.
2. **High-Severity Findings (Block Production Deployment until Resolved):**
   - `privileged: true` or `allowPrivilegeEscalation: true` (including privileged `chown` `initContainers` — replace with `podSecurityContext.fsGroup` and `runAsUser`)
   - Host namespace sharing (`hostNetwork: true`, `hostPID: true`, `hostIPC: true`) or `hostPath` volumes
   - Wildcard RBAC rules (`verbs: ["*"]` or `resources: ["*"]` in `ClusterRole` / `Role`)
3. **Medium-Severity Findings (Remediate via Values Overrides):**
   - Missing `runAsNonRoot: true` in pod/container `securityContext`
   - Mutable image tags (`:latest`, `:main`, `:master`)
   - Missing CPU/memory `resources.limits` and `resources.requests`
4. **Gate Outcome & Re-Verification:**
   - Whenever proposing any Helm `values` overrides—whether remediating scanner findings or adding `emptyDir` writable mounts (`/tmp`, `/var/cache/nginx`, `/var/run`) to support `readOnlyRootFilesystem: true`—always explicitly advise re-rendering the release manifests via `helm_render_manifests` and re-running `scan_manifest_security.py` to confirm `summary.high == 0` before calling `helm_plan_release`, `helm_install_chart`, or `helm_upgrade_release` (even if you also verified a sample render locally).
   - When a manifest passes cleanly (`passed: true`, `high == 0`, `medium == 0`), explicitly state that the release is cleared to proceed to `helm_plan_release` and `helm_install_chart` or `helm_upgrade_release`.
