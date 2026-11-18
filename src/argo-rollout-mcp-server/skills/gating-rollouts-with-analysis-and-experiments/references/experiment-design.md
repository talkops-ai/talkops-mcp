# Argo Experiment Design & `specRef` Resolution

## How `argo_create_experiment` Resolves `specRef`

Standalone Argo `Experiment` CRDs require full pod `template` specs in `spec.templates[*]`. For convenience, `argo_create_experiment` accepts `specRef` shortcuts when `rollout_name` is provided:
- `specRef: "stable"` or `specRef: "active"` -> resolves pod template from the Rollout's `status.stableRS` ReplicaSet (`{rollout_name}-{stableRS}`).
- `specRef: "canary"` or `specRef: "preview"` -> resolves pod template from the Rollout's `status.currentPodHash` ReplicaSet (`{rollout_name}-{currentPodHash}`).

### Example `templates` Payload
```json
[
  {"name": "baseline", "replicas": 1, "specRef": "stable"},
  {"name": "candidate", "replicas": 1, "specRef": "canary"}
]
```

## Isolation from Live Service Traffic

When resolving `specRef` templates, `argo_create_experiment` injects `experiment-variant: {template_name}` into `selector.matchLabels` and `template.metadata.labels` so the Experiment's ReplicaSet pods are isolated and do not accidentally receive live production traffic without explicit routing.

## Traefik Traffic Routing Limitation

Weighted Experiment traffic splitting (`spec.templates[*].weight`) is **only** supported by SMI, AWS ALB, and Istio traffic routers — **not** Traefik.
When using Traefik:
- Use Experiments for **side-by-side metrics comparison** (`analyses` attached to the `Experiment`) or synthetic load generation.
- Use `argo_compare_canary_metrics` during canary steps for live production traffic comparison.
