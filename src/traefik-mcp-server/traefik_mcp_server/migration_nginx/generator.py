"""Migration report generator — produces a single markdown runbook.

The runbook is the primary output of the migration tool.  It contains
inline YAML for the migration-critical files (Middleware CRDs, updated
Ingresses, shadow TraefikService) and references boilerplate files
(Helm install, verification, DNS, cleanup) as steps.

Structured ``GeneratedFile`` objects are kept internally for the ``apply``
path but are NOT returned as a JSON files dict — saving significant
context for AI agent consumers.
"""

from typing import Any, Dict, List, Optional

from traefik_mcp_server.migration_nginx.scanner import ScanResult
from traefik_mcp_server.migration_nginx.analyzer import AnalysisReport
from traefik_mcp_server.migration_nginx.migrator_traefik import GeneratedFile



def generate_migration_report(
    scan_result: ScanResult,
    analysis: AnalysisReport,
    files: Optional[List[GeneratedFile]] = None,
    migration_plan: Optional[Dict[str, Any]] = None,
) -> str:
    """Generate the 00-migration-report.md as a phased operational runbook.

    The runbook inlines YAML for migration-critical files and references
    boilerplate as steps — giving agents everything they need in a single
    compact string.
    """
    all_files = files or []

    # Classify files by category for phased output
    middleware_files = [f for f in all_files if f.category == "middleware"]
    ingress_files = [f for f in all_files if f.category == "ingress"]
    shadow_files = [f for f in all_files if f.category == "shadow"]
    serverstransport_files = [f for f in all_files if f.category == "serverstransport"]
    service_patch_files = [f for f in all_files if f.category == "service_patch"]
    has_shadow = len(shadow_files) > 0

    lines: List[str] = [
        "# NGINX → Traefik Migration Runbook",
        "",
        f"**Cluster:** {scan_result.cluster_name or '(unknown)'}  ",
        f"**Controller:** {scan_result.controller.type} "
        f"(v{scan_result.controller.version}, ns/{scan_result.controller.namespace})  ",
        f"**Target:** {analysis.target}  ",
        f"**Namespaces:** {', '.join(scan_result.namespaces) if scan_result.namespaces else 'all'}",
        "",
        "---",
        "",
    ]

    # ── Compatibility Summary ──────────────────────────────────────────────
    lines.extend([
        "## Compatibility Summary",
        "",
        "| Metric | Count |",
        "|--------|-------|",
        f"| **Total Ingresses** | {analysis.summary.total} |",
        f"| ✅ Fully compatible | {analysis.summary.fully_compatible} |",
        f"| ⚠️ Needs workaround | {analysis.summary.needs_workaround} |",
        f"| ❌ Has unsupported | {analysis.summary.has_unsupported} |",
        "",
    ])

    for ir in analysis.ingress_reports:
        status_icon = {"ready": "✅", "workaround": "⚠️", "breaking": "❌"}.get(ir.overall_status, "❓")
        lines.append(f"### {status_icon} {ir.namespace}/{ir.name}")
        lines.append("")

        if not ir.mappings:
            lines.append("_No nginx annotations detected._")
            lines.append("")
            continue

        lines.append("| Annotation | Status | Target Resource | Note |")
        lines.append("|-----------|--------|-----------------|------|")
        for m in ir.mappings:
            badge = {"supported": "✅", "partial": "⚠️", "unsupported": "❌"}.get(m.status, "❓")
            lines.append(
                f"| `{m.original_key}` | {badge} {m.status} | {m.target_resource or '—'} | {m.note} |"
            )
        lines.append("")

    lines.extend(["---", ""])

    # ── Phase 1 — Prerequisites ────────────────────────────────────────────
    lines.extend([
        "## Phase 1 — Prerequisites",
        "",
        "1. **Install Traefik** alongside NGINX (zero-downtime parallel running):",
        "   ```bash",
        "   # Files in 01-install-traefik/",
        "   helm repo add traefik https://traefik.github.io/charts && helm repo update",
        "   helm upgrade --install traefik traefik/traefik \\",
        "     --namespace traefik --create-namespace \\",
        '     --set providers.kubernetesIngressNginx.enabled=true \\',
        '     --version ">=3.6.2"',
        "   kubectl rollout status deployment/traefik -n traefik --timeout=120s",
        "   ```",
    ])

    if has_shadow:
        lines.extend([
            "2. **Provision shadow workloads** — shadow mode is enabled. Create the",
            "   shadow Service and Deployment for each mirrored backend before applying.",
            "   The migrator does NOT create workloads; only the TraefikService mirror CRD.",
        ])

    lines.extend(["", "---", ""])

    # ── Phase 2 — Apply Migration ──────────────────────────────────────────
    lines.extend([
        "## Phase 2 — Apply Migration",
        "",
    ])

    step = 1

    # Step: Middlewares
    if middleware_files:
        lines.append(f"### Step {step}: Apply Middleware CRDs")
        lines.append("")
        for mf in middleware_files:
            lines.append(f"**{mf.description}**")
            lines.append("```yaml")
            lines.append(mf.content.rstrip())
            lines.append("```")
            lines.append("")
        step += 1

    # Step: ServersTransport CRDs
    if serverstransport_files:
        lines.append(f"### Step {step}: Apply ServersTransport CRDs (backend timeouts/TLS)")
        lines.append("")
        lines.append("These configure backend connection properties — timeouts, TLS verification — ")
        lines.append("that NGINX handled via `proxy-*-timeout` and `backend-protocol` annotations.")
        lines.append("")
        for stf in serverstransport_files:
            lines.append(f"**{stf.description}**")
            lines.append("```yaml")
            lines.append(stf.content.rstrip())
            lines.append("```")
            lines.append("")
        step += 1

    # Step: Service sticky session patches
    if service_patch_files:
        lines.append(f"### Step {step}: Apply Service sticky session patches")
        lines.append("")
        lines.append("These patch backend K8s Services with Traefik sticky cookie annotations — ")
        lines.append("migrated from NGINX `affinity` and `session-cookie-*` annotations.")
        lines.append("")
        for spf in service_patch_files:
            lines.append(f"**{spf.description}**")
            lines.append("```yaml")
            lines.append(spf.content.rstrip())
            lines.append("```")
            lines.append("")
        step += 1

    # Step: Ingresses
    if ingress_files:
        lines.append(f"### Step {step}: Apply updated Ingresses")
        lines.append("")
        for igf in ingress_files:
            lines.append(f"**{igf.description}**")
            lines.append("```yaml")
            lines.append(igf.content.rstrip())
            lines.append("```")
            lines.append("")
        step += 1

    # Step: Shadow
    if shadow_files:
        lines.append(f"### Step {step}: Apply TraefikService mirrors (shadow testing)")
        lines.append("")
        for sf in shadow_files:
            lines.append(f"**{sf.description}**")
            lines.append("```yaml")
            lines.append(sf.content.rstrip())
            lines.append("```")
            lines.append("")
        step += 1

    if analysis.target == "gateway-api":
        # Gateway API specific: HTTPRoutes and Gateway
        httproute_files = [f for f in all_files if f.category == "httproute"]
        gateway_files = [f for f in all_files if f.category == "gateway"]

        if gateway_files:
            lines.append(f"### Step {step}: Apply Gateway resource")
            lines.append("")
            for gf in gateway_files:
                lines.append(f"**{gf.description}**")
                lines.append("```yaml")
                lines.append(gf.content.rstrip())
                lines.append("```")
                lines.append("")
            step += 1

        if httproute_files:
            lines.append(f"### Step {step}: Apply HTTPRoutes")
            lines.append("")
            for hf in httproute_files:
                lines.append(f"**{hf.description}**")
                lines.append("```yaml")
                lines.append(hf.content.rstrip())
                lines.append("```")
                lines.append("")
            step += 1

    lines.extend(["---", ""])

    verify_file = next((f for f in all_files if f.category == "verify"), None)
    
    # ── Phase 3 — Validate ─────────────────────────────────────────────────
    lines.extend([
        "## Phase 3 — Validate",
        "",
        "1. **Run verification script:**",
        "   ```bash"
    ])
    if verify_file:
        lines.append(verify_file.content.strip())
    else:
        lines.append("   bash 04-verify.sh")
    lines.extend([
        "   ```",
    ])

    if has_shadow:
        lines.extend([
            "2. **Monitor shadow traffic** — mirrored responses are discarded (no user impact).",
            "   Check Traefik access logs and shadow backend metrics to validate parity:",
            "   ```bash",
            "   kubectl logs -n traefik -l app.kubernetes.io/name=traefik -f | grep mirror",
            "   ```",
        ])

    lines.extend(["", "---", ""])

    # ── Phase 4 — Cutover / Switch ─────────────────────────────────────────
    lines.extend([
        "## Phase 4 — Cutover / Switch",
        "",
        "You have two options for cutting over traffic:",
        "",
        "**Option A: DNS Cutover (Zero Downtime, Side-by-Side)**",
        "1. Set DNS TTL to **60s** before making changes",
        "2. Add Traefik LoadBalancer IP alongside NGINX in DNS records",
        "3. Monitor both controllers: `kubectl logs -n traefik -l app.kubernetes.io/name=traefik -f`",
        "4. Once confident, remove NGINX IP from DNS — wait 24–48 hours for TTL propagation",
        "",
        "**Option B: In-Cluster Instant Switch**",
        "If you want to instantly switch traffic at the Kubernetes level rather than waiting for DNS,",
        "re-run the migration tool with the `switch=True` parameter:",
        "```",
        "Tool: traefik_nginx_migration",
        "Parameters:",
        "  action: apply",
        "  namespace: <namespace>",
        "  switch: true",
        "```",
        "This will patch the `ingressClassName` from `nginx` to `traefik` on the fly.",
        "",
        "_(Detailed guide in `05-dns-migration.md`)_",
        "",
        "---",
        "",
    ])

    # ── Phase 5 — Post-Migration ───────────────────────────────────────────
    cleanup_yaml = next((f for f in all_files if f.rel_path.endswith("01-preserve-ingressclass.yaml")), None)
    
    lines.extend([
        "## Phase 5 — Post-Migration",
        "",
        "### Cleanup",
        "Remove NGINX after migration is verified complete (100% migrated):",
        "```bash",
        "# Preserve IngressClass so Traefik keeps watching",
        "cat <<EOF | kubectl apply -f -"
    ])
    
    if cleanup_yaml:
        lines.append(cleanup_yaml.content.strip())
    else:
        lines.extend([
            "apiVersion: networking.k8s.io/v1",
            "kind: IngressClass",
            "metadata:",
            "  name: nginx",
            "  annotations:",
            "    ingressclass.kubernetes.io/is-default-class: \"false\"",
            "    helm.sh/resource-policy: keep",
            "spec:",
            "  controller: k8s.io/ingress-nginx"
        ])
        
    lines.extend([
        "EOF",
        "",
        "# Uninstall NGINX",
        "bash 06-cleanup/02-remove-nginx.sh",
        "```",
        "",
    ])
    lines.extend([
        "### Rollback (if needed)",
        "If the migration breaks traffic, use the MCP tool to instantly revert:",
        "```",
        "Tool: traefik_nginx_migration",
        "Parameters:",
        "  action: revert",
        "  namespace: <namespace>",
        "  ingress_name: <ingress_name>",
        "",
        "Prerequisites:",
        "  - MCP_ALLOW_WRITE=true",
        "  - Must be the same server session that ran action=apply",
        "```",
        "This strips Traefik annotations, restores original NGINX annotations from cache,",
        "and deletes generated Middleware CRDs.",
        "",
    ])

    # ── Agent Intelligence (if migration_plan was used) ────────────────────
    if migration_plan:
        lines.extend(["---", "", "## Agent Intelligence — Migration Plan Overrides", ""])
        for key, val in migration_plan.items():
            if not isinstance(val, dict):
                continue
            lines.append(f"### `{key}`")
            ignore = val.get("ignore_annotations", [])
            inject = val.get("inject_middlewares", [])
            shadow = val.get("shadow_mode", False)
            shadow_pct = val.get("shadow_mirror_percent", 20)
            if ignore:
                lines.append(f"- **Ignored annotations:** {', '.join(f'`{a}`' for a in ignore)}")
            if inject:
                lines.append(f"- **Injected middlewares:** {', '.join(f'`{m}`' for m in inject)}")
            if shadow:
                lines.append(f"- **Shadow mode:** enabled ({shadow_pct}% mirror)")
            lines.append("")

    lines.append("_Generated by Traefik MCP Server — native NGINX migration pipeline._")

    return "\n".join(lines)


def bundle_migration_output(
    files: List[GeneratedFile],
    scan_result: ScanResult,
    analysis: AnalysisReport,
    migration_plan: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Bundle migration output as a single markdown runbook string.

    The runbook inlines YAML for migration-critical files and describes
    boilerplate as steps — saving significant context for AI consumers
    compared to the previous files-dict schema.

    Structured ``GeneratedFile`` objects are still available internally
    for the ``apply`` path.
    """
    report_md = generate_migration_report(
        scan_result, analysis, files=files, migration_plan=migration_plan,
    )

    categories = sorted(set(f.category for f in files))
    total_inline_files = sum(
        1 for f in files if f.category in (
            "middleware", "ingress", "shadow", "httproute", "gateway",
            "serverstransport", "service_patch",
        )
    )

    return {
        "migration": {
            "runbook": report_md,
            "bundleSummary": {
                "total_files": len(files),
                "inline_files": total_inline_files,
                "categories": categories,
            },
        },
    }
