# Provider Configuration and Coexistence Rules

## Table of Contents

1. [Enabling `providers.kubernetesIngressNGINX` in Traefik v3.6+](#1-enabling-providerskubernetesingressnginx-in-traefik-v36)
2. [Provider Isolation: `kubernetesIngress` vs `kubernetesIngressNGINX`](#2-provider-isolation-kubernetesingress-vs-kubernetesingressnginx)
3. [Avoiding `INGRESS_PROVIDER_CONFLICT`](#3-avoiding-ingress_provider_conflict)

## 1. Enabling `providers.kubernetesIngressNGINX` in Traefik v3.6+

In the official Traefik Helm chart (`values.yaml`):

```yaml
providers:
  kubernetesIngress:
    enabled: true
    ingressClass: traefik
  kubernetesIngressNGINX:
    enabled: true
    ingressClass: nginx
    controllerClass: k8s.io/ingress-nginx
    watchNamespace: ""
```

Verify activation by reading `traefik://server/capabilities` (`enabled_providers`) and `traefik://instance/static-config`.

## 2. Provider Isolation: `kubernetesIngress` vs `kubernetesIngressNGINX`

- `providers.kubernetesIngress` watches `ingressClassName: traefik` and interprets `traefik.ingress.kubernetes.io/*` annotations.
- `providers.kubernetesIngressNGINX` watches `ingressClassName: nginx` and interprets `nginx.ingress.kubernetes.io/*` annotations.

## 3. Avoiding `INGRESS_PROVIDER_CONFLICT`

Never place both `nginx.ingress.kubernetes.io/*` and `traefik.ingress.kubernetes.io/*` annotations on the same `Ingress` resource. If an `Ingress` requires a Tier-3 native Traefik feature (such as a complex `chain` or `circuitBreaker`), either:
1. Keep the `Ingress` purely on `kubernetesIngressNGINX` for Tier-1 features, or
2. Promote that specific route to a native `traefik.io/v1alpha1` `IngressRoute` via `traefik_configure_http_route(dry_run=True)`.
