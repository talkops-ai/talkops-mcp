# Loki 3.x Architecture and Sizing Reference

## Table of Contents
1. [Deployment Modes Comparison](#1-deployment-modes-comparison)
2. [Kubernetes Loki Operator (`LokiStack`) Sizing Tiers](#2-kubernetes-loki-operator-lokistack-sizing-tiers)
3. [Memberlist Ring and Ingester Replication Factor](#3-memberlist-ring-and-ingester-replication-factor)

---

## 1. Deployment Modes Comparison

| Mode | Daily Ingestion Volume | Target Components | Best For |
|------|------------------------|-------------------|----------|
| **Monolithic (`-target=all`)** | `< 20 GB / day` | Single StatefulSet/binary | Dev/staging, edge clusters, small single-tenant setups |
| **Simple Scalable (`read`, `write`, `backend`)** | `20 GB - 1 TB / day` | 3 targets (`read`, `write`, `backend`) | Default production architecture for most Kubernetes clusters |
| **Microservices** | `> 1 TB / day` | Independent `distributor`, `ingester`, `querier`, `query-frontend`, `query-scheduler`, `index-gateway`, `compactor`, `ruler`, `bloom-planner`, `bloom-builder`, `bloom-gateway` | Multi-tenant SaaS, massive query concurrency, independent autoscaling |

---

## 2. Kubernetes Loki Operator (`LokiStack`) Sizing Tiers

When deploying via the Kubernetes Loki Operator (`loki.grafana.com/v1`), choose the official `size` tier matching your daily log volume:

| `spec.size` | Ingestion Capacity | Queries / Sec | Replication Factor |
|-------------|--------------------|---------------|--------------------|
| `1x.demo` | `< 10 GB / day` | Best effort | `1` (Non-HA, dev only) |
| `1x.extra-small` | Up to `100 GB / day` | ~5 QPS | `2` or `3` |
| `1x.small` | Up to `500 GB / day` | ~15 QPS | `3` |
| `1x.medium` | Up to `2 TB / day` | ~35 QPS | `3` |

---

## 3. Memberlist Ring and Ingester Replication Factor

- Always set `common.replication_factor: 3` in production so write paths survive single-node failures without losing in-memory chunks.
- Configure **zone-aware replication** (`ingester.lifecycler.ring.zone_awareness_enabled: true`) across 3 availability zones (`zone-a`, `zone-b`, `zone-c`).
- Enable **Write-Ahead Log (`ingester.wal.enabled: true`)** backed by a dedicated fast SSD PVC on write/ingester pods so un-flushed chunks recover cleanly across pod restarts.
