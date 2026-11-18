# Progressive Delivery Strategy Playbooks

## 1. Standard Canary (`5% -> 10% -> 25% -> 50% -> 100%`)

Best for stateless HTTP/gRPC services where gradual exposure reduces blast radius.

```json
[
  {"setWeight": 5},
  {"pause": {"duration": "2m"}},
  {"setWeight": 25},
  {"pause": {"duration": "5m"}},
  {"setWeight": 50},
  {"pause": {}}
]
```

## 2. Cost-Conscious Canary (`setCanaryScale`)

When traffic routing (`TraefikService` or Gateway API `HTTPRoute`) is configured, decouple canary pod count from traffic percentage using `setCanaryScale` so you can validate a single canary pod with 5% traffic before scaling up replicas:

```json
[
  {"setCanaryScale": {"replicas": 1}},
  {"setWeight": 5},
  {"pause": {"duration": "5m"}},
  {"setCanaryScale": {"matchTrafficWeight": true}},
  {"setWeight": 25},
  {"pause": {"duration": "5m"}},
  {"setWeight": 50},
  {"pause": {}}
]
```

> **Important**: `setCanaryScale` requires `trafficRouting` to be configured on `spec.strategy.canary`. Without a traffic router, Argo Rollouts approximates weight by replica ratio.

## 3. Blue-Green Instant Cutover

Best for workloads that cannot run mixed schema/API versions simultaneously or require smoke testing on `{name}-preview` before switching production traffic on `{name}-active`.

- `auto_promotion_enabled: false` (recommended for production manual verification)
- `scale_down_delay_seconds: 30` (keeps the old active ReplicaSet warm for 30s after cutover to prevent in-flight connection drops and allow instant rollback)
- `preview_replica_count: 1` (optional cost optimization while paused in preview; scales to full `replicas` before cutover)

## 4. Rolling Update via Argo Rollouts

Use `strategy="rolling"` (empty canary `steps: []`) when migrating a workload to Argo Rollouts for unified observability (`argorollout://rollouts/list`, `argo_diagnose_rollout`) before introducing canary weights or traffic routers.
