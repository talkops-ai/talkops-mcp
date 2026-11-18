# Grafana Tempo 2.x vs 3.x Architecture Reference

## 1. Ingestion Pipeline Comparison

| Capability | Tempo 2.x Distributed | Tempo 3.x Distributed (Kafka + Block-Builder) |
| :--- | :--- | :--- |
| Write Path | `distributor` -> `ingester` (in-memory WAL + local blocks) -> Object Storage | `distributor` -> `ingest` (stateless Kafka producer) -> Kafka -> `block-builder` -> Object Storage |
| Live Tail / Recent Reads | Querier fans out to `ingester` in-memory ring + Object Storage | `block-builder` streams blocks to Object Storage; monitor `tempo_ingest_group_partition_lag_seconds` (`PARTITION_LAG_OBSERVED`) |
| Default Block Format | `vParquet3` / `vParquet4` (Tempo 2.5+) | `vParquet4` default with dedicated attribute columns |
| Structural & Cohort TraceQL | TraceQL structural (`>`, `>>`, `~`), `select()`, `compare()` | Full `vParquet4` column pushdown for `compare()`, `topk()`, and `with(most_recent=true)` |

## 2. Diagnostic Implications

- **Tempo 2.x**: Unhealthy `ingester` ring members (`RING_MEMBER_UNHEALTHY`) immediately threaten recent trace durability and live query completeness.
- **Tempo 3.x**: Because `ingest` is stateless and writes to Kafka, inspect `PARTITION_LAG_OBSERVED` (`tempo_ingest_group_partition_lag_seconds`) and `block-builder` component readiness (`COMPONENT_NOT_RUNNING`).
