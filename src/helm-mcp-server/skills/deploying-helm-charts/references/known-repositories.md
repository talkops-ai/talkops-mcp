# Canonical Helm Repositories Catalog

Use this reference when calling `helm_ensure_repository(repo_name, repo_url)` to add standard upstream chart repositories.

| Repository Alias (`repo_name`) | Canonical URL (`repo_url`) | Common Charts |
|---|---|---|
| `bitnami` | `https://charts.bitnami.com/bitnami` | `postgresql`, `redis`, `mysql`, `mongodb`, `nginx`, `kafka`, `rabbitmq` |
| `argo` | `https://argoproj.github.io/argo-helm` | `argo-cd`, `argo-rollouts`, `argo-workflows`, `argo-events` |
| `prometheus-community` | `https://prometheus-community.github.io/helm-charts` | `kube-prometheus-stack`, `prometheus`, `alertmanager` |
| `grafana` | `https://grafana.github.io/helm-charts` | `grafana`, `loki`, `tempo`, `promtail`, `mimir-distributed` |
| `ingress-nginx` | `https://kubernetes.github.io/ingress-nginx` | `ingress-nginx` |
| `traefik` | `https://traefik.github.io/charts` | `traefik` |
| `jetstack` | `https://charts.jetstack.io` | `cert-manager`, `trust-manager` |
| `autoscaler` | `https://kubernetes.github.io/autoscaler` | `cluster-autoscaler` |
| `metrics-server` | `https://kubernetes-sigs.github.io/metrics-server/` | `metrics-server` |
| `external-secrets` | `https://charts.external-secrets.io` | `external-secrets` |
| `open-telemetry` | `https://open-telemetry.github.io/opentelemetry-helm-charts` | `opentelemetry-collector`, `opentelemetry-operator`, `opentelemetry-demo`, `opentelemetry-kube-stack` |
| `talkops` | `https://talkops-ai.github.io/OTEL-APP` | `postgresql`, `valkey-cart`, `flagd`, `kafka`, `ad`, `cart`, `checkout`, `currency`, `email`, `frontend`, `frontend-proxy`, `image-provider`, `load-generator`, `payment`, `product-catalog`, `quote`, `recommendation`, `shipping` |

## Chart Reference Conventions

- Always pass chart references to MCP tools in explicit `<repo_name>/<chart_name>` format (for example, `bitnami/postgresql` or `argo/argo-cd`) or OCI format (`oci://registry.example.com/charts/app`).
- Never rely on implicit repository guessing for bare chart names.
