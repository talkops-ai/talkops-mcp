# GitOps Integration (ArgoCD & Helm)

## Preventing ArgoCD `OutOfSync` Drift

When Argo Rollouts mutates runtime fields (such as `TraefikService` weights, `Rollout` status, or `Deployment` `/spec/replicas` in `workload_ref` mode), ArgoCD detects drift against Git and may revert live traffic weights or replica counts during auto-sync.

Generate the required `ignoreDifferences` stanza with:
```bash
python3 scripts/generate_argocd_ignore_differences.py \
  --include-traefik-service \
  --include-rollout-status \
  --include-rollout-traffic-routing \
  --include-deployment-replicas \
  --deployment-name my-app
```

## Recommended `Application` `ignoreDifferences` Stanza

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
spec:
  ignoreDifferences:
    - group: apps
      kind: Deployment
      name: my-app
      jsonPointers:
        - /spec/replicas
    - group: traefik.io
      kind: TraefikService
      jsonPointers:
        - /spec/weighted/services
    - group: argoproj.io
      kind: Rollout
      jsonPointers:
        - /status
        - /spec/strategy/canary/trafficRouting
```

## GitOps Legacy Deployment Scale-Down

If ArgoCD `selfHeal: true` is enabled on your `Application`, calling `argo_manage_legacy_deployment(action="scale", replicas=0)` directly against the cluster will be reverted by ArgoCD on the next reconciliation loop.
Instead:
1. Run `scripts/generate_scale_down_manifest.py --input deployment.yaml` to produce a declarative `Deployment` manifest with `spec.replicas: 0`.
2. Commit the updated `Deployment` manifest alongside the new `Rollout` manifest in Git.
