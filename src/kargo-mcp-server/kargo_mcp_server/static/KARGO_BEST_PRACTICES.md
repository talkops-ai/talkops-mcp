# Kargo Best Practices

## Pipeline Design

### Stage Topology
- **Keep pipelines shallow**: 3-4 stages maximum (dev → staging → production)
- **Fan-out for regions**: Use parallel stages for multi-region deployments
- **Avoid deep chains**: Long pipelines slow down delivery velocity

### Warehouse Configuration
- **One warehouse per artifact group**: Group related images together
- **Use semver filtering**: Avoid promoting unstable/pre-release versions
- **Set reconciliation intervals**: Balance freshness vs API load

### Freight Management
- **Auto-promotion for dev**: Speed up inner-loop development
- **Manual approval for production**: Gate critical deployments
- **Verification after every stage**: Catch issues early

## Promotion Steps

### Built-in Steps
- `git-clone` / `git-push` — Git operations
- `helm-update-chart` / `helm-update-image` — Helm value updates
- `argocd-update` — ArgoCD application sync
- `yaml-update` — Generic YAML patching
- `http` — Webhook notifications

### Custom Steps
- Use `PromotionTask` CRD for reusable step sequences
- Parameterize with stage variables for environment-specific config
- Keep steps idempotent for safe retries

## Security

### RBAC Best Practices
- Use project-scoped roles for team access
- Gate production stages with manual approval policies
- Use PASSTHROUGH auth mode for fine-grained RBAC enforcement
- Audit all promotion activities

### Secrets
- Store credentials in Kubernetes Secrets
- Reference secrets in promotion steps, never inline
- Rotate credentials regularly

## Observability
- Monitor warehouse sync status for artifact discovery issues
- Track promotion duration for performance baselines
- Set up alerts for failed promotions and verification failures
- Use `kargo_describe_topology` to audit pipeline structure
