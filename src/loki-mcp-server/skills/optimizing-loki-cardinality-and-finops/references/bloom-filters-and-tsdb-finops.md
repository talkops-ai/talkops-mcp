# Loki 3.x Bloom Filters and TSDB v13 FinOps Guide

## Table of Contents
1. [TSDB v13 Index Schema Best Practices](#1-tsdb-v13-index-schema-best-practices)
2. [Chunk Target Size and Compression Tuning](#2-chunk-target-size-and-compression-tuning)
3. [Loki 3.x Bloom Filters for Needle-in-a-Haystack Queries](#3-loki-3x-bloom-filters-for-needle-in-a-haystack-queries)
4. [Per-Tenant and Per-Stream Ingestion Limits](#4-per-tenant-and-per-stream-ingestion-limits)

---

## 1. TSDB v13 Index Schema Best Practices

Loki 3.x requires `store: tsdb` with `schema: v13` and `24h` index periods:
```yaml
schema_config:
  configs:
    - from: "2024-04-01"
      store: tsdb
      object_store: s3
      schema: v13
      index:
        prefix: loki_index_
        period: 24h
```
- **Why TSDB v13**: Supports native Structured Metadata, Bloom filters, and up to 70% lower memory overhead on index gateways compared to legacy `boltdb-shipper`.

---

## 2. Chunk Target Size and Compression Tuning

```yaml
ingester:
  chunk_encoding: snappy        # Use 'zstd' if storage cost > CPU cost; 'snappy' for balanced query speed
  chunk_target_size: 1572864    # 1.5 MB target compressed chunk size
  chunk_idle_period: 30m        # Flush idle streams after 30m
  max_chunk_age: 2h             # Force flush every 2h
```
- If average chunk size is `< 256 KB`, you have **too many streams** (high label cardinality). Demote `pod`, `instance`, or dynamic labels to `structured_metadata`.

---

## 3. Loki 3.x Bloom Filters for Needle-in-a-Haystack Queries

Bloom filters allow Loki to skip downloading and decompressing 95%+ of chunks when searching for high-cardinality structured metadata (`trace_id="4bf9..."`) or literal strings (`|= "order-987654"`):

```yaml
bloom_build:
  enabled: true
  builder:
    planner_address: loki-bloom-planner:9095
bloom_gateway:
  enabled: true
  client:
    addresses: dnssrvnoa+_grpc._tcp.loki-bloom-gateway-headless.logging.svc.cluster.local
limits_config:
  bloom_gateway_enable_filtering: true
  bloom_creation_enabled: true
```

---

## 4. Per-Tenant and Per-Stream Ingestion Limits

Protect the cluster against noisy neighbor workloads in `limits_config`:
```yaml
limits_config:
  ingestion_rate_mb: 32
  ingestion_burst_size_mb: 64
  per_stream_rate_limit: 5MB
  per_stream_rate_limit_burst: 15MB
  max_global_streams_per_user: 50000
  max_line_size: 256KB
  max_line_size_truncate: true
```
