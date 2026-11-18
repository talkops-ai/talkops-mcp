# Zero-Downtime Cutover and Rollback Runbook

## Table of Contents

1. [Phase 1 — Pre-Cutover Annotation Audit](#1-phase-1--pre-cutover-annotation-audit)
2. [Phase 2 — Parallel Validation via `traefik_trace_request`](#2-phase-2--parallel-validation-via-traefik_trace_request)
3. [Phase 3 — DNS / LoadBalancer Cutover & Instant Rollback](#3-phase-3--dns--loadbalancer-cutover--instant-rollback)

## 1. Phase 1 — Pre-Cutover Annotation Audit

1. Read `traefik://routes/_all` and filter `kind == "Ingress"`.
2. Run `classify_nginx_annotations.py` on any `Ingress` carrying `nginx.ingress.kubernetes.io/*` annotations.
3. Remediate Tier-3 snippet annotations before cutover.

## 2. Phase 2 — Parallel Validation via `traefik_trace_request`

1. Deploy Traefik v3.6+ with `providers.kubernetesIngressNGINX.enabled=true` watching `ingressClass: nginx` alongside the existing `ingress-nginx` controller.
2. Call `traefik_diagnose_route(kind="Ingress", name=..., namespace=...)` on each critical `Ingress` to verify `healthy: true`.
3. Call `traefik_trace_request` with synthetic production URLs and headers to verify router matching and middleware chains.

## 3. Phase 3 — DNS / LoadBalancer Cutover & Instant Rollback

1. Shift external DNS or LoadBalancer target group weights from `ingress-nginx` Service to Traefik's Service.
2. Monitor `traefik_compare_traffic_metrics` and `traefik_analyze_logs(source="access")`.
3. **Rollback**: Because the original `Ingress` manifests and `nginx.ingress.kubernetes.io/*` annotations remain unmodified in the cluster, rolling back is an instantaneous DNS/LoadBalancer pointer revert to `ingress-nginx`.
