# Traffic Routing: Traefik & Gateway API

## Why Traffic Routing Is Required for Fine-Grained Weights

Without `spec.strategy.canary.trafficRouting`, Argo Rollouts splits traffic purely by Kubernetes Service pod replica ratios (e.g., 5% weight requires 20 pods). With `trafficRouting`, Argo Rollouts updates ingress/mesh weights dynamically regardless of replica count.

## Option A: Traefik (`TraefikService` Weighted Round Robin)

Configure on an existing Rollout using `argo_configure_rollout_strategy`:
```json
{
  "name": "payments-api",
  "namespace": "production",
  "traffic_routing": {
    "traefik_service_name": "payments-api-wrr"
  },
  "dry_run": true
}
```

### Prerequisite `TraefikService` CRD
The `TraefikService` must exist in the same namespace and reference `{name}-stable` and `{name}-canary`:
```yaml
apiVersion: traefik.io/v1alpha1
kind: TraefikService
metadata:
  name: payments-api-wrr
  namespace: production
spec:
  weighted:
    services:
      - name: payments-api-stable
        port: 80
        weight: 100
      - name: payments-api-canary
        port: 80
        weight: 0
```

## Option B: Kubernetes Gateway API (`HTTPRoute` Plugin)

Supported for Traefik 3.x, Envoy Gateway, Cilium, and Istio Gateway API implementations via the `argoproj-labs/gatewayAPI` plugin:
```json
{
  "name": "payments-api",
  "namespace": "production",
  "traffic_routing": {
    "gateway_api_config": {
      "httpRoute": "payments-api-route",
      "namespace": "production"
    }
  },
  "dry_run": true
}
```

## Constraints & Pitfalls

1. **Mutually Exclusive**: `traefik_service_name` and `gateway_api_config` cannot both be set on the same Rollout.
2. **Canary Only**: Argo Rollouts does not support `trafficRouting` on `blueGreen` strategy Rollouts.
3. **ArgoCD Drift**: If the Rollout is tracked by ArgoCD (`argocd.argoproj.io/tracking-id`), add `/spec/strategy/canary/trafficRouting` and `TraefikService` `/spec/weighted/services` to `ignoreDifferences`.
