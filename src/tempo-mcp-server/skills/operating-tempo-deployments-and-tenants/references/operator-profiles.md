# Tempo Operator (`tempo.grafana.com/v1alpha1`) Sizing Profiles

## 1. Profile Selection Matrix

| Profile | Kind | Target Ingestion Rate | Replicas (`distributor` / `ingester` / `querier`) | Total Memory / CPU | Object Storage |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `dev` | `TempoMonolithic` | `< 1 MB/s` (`< 1,000 spans/s`) | 1 monolithic pod | `2Gi` / `1000m` | S3 / MinIO / GCS (`inMemory` only for ephemeral tests) |
| `small-prod` | `TempoStack` | `1–10 MB/s` (`1k–10k spans/s`) | `2` / `3` / `2` | `12Gi` / `6000m` | S3 / GCS / Azure Blob + `replicationFactor: 2` |
| `large-prod` | `TempoStack` | `10–50+ MB/s` (`10k–50k+ spans/s`) | `4` / `6` / `4` | `48Gi` / `24000m` | S3 / GCS / Azure Blob + `replicationFactor: 3` |

## 2. Canonical `TempoStack` (`v1alpha1`) Structure

```yaml
apiVersion: tempo.grafana.com/v1alpha1
kind: TempoStack
metadata:
  name: tempo-prod
  namespace: observability
spec:
  storage:
    secret:
      name: tempo-s3-credentials
      type: s3
  storageSize: 50Gi
  replicationFactor: 2
  retention:
    global:
      traces: 336h
  resources:
    total:
      limits:
        cpu: "6000m"
        memory: 12Gi
  template:
    distributor:
      replicas: 2
    ingester:
      replicas: 3
    querier:
      replicas: 2
    queryFrontend:
      replicas: 2
    compactor:
      replicas: 1
```
