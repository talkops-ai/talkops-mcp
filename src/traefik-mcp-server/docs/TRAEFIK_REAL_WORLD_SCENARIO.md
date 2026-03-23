# Real-World Traefik Workflows and Usage Scenarios

## 1. Overview

Traefik is a cloud‑native reverse proxy, load balancer, and edge router that automatically discovers services from providers such as Docker, Kubernetes, and Consul, and configures routing dynamically. It can act as a traditional reverse proxy, a Kubernetes ingress controller, or an API gateway, handling TLS termination, load balancing, routing, and cross‑cutting concerns like authentication and rate limiting.[1][2][3][4][5]

This document consolidates the main **workflows** teams implement with Traefik in production today, across HTTP and TCP, and across container platforms. Each workflow describes the scenario, typical configuration approach, and how it fits into broader architectures.

***

## 2. Core Reverse Proxy and Virtual Host Routing

### 2.1 Scenario

Expose multiple HTTP applications on the same IP and port (usually 80/443) and route requests based on hostname or path. This is the most common Traefik usage: a smart reverse proxy in front of a set of services.[2][4][5][1]

### 2.2 Typical workflow

- **Set up entrypoints** for HTTP and HTTPS, e.g., `:80` and `:443`.
- **Define HTTP routers** using rules like `Host(`app1.example.com`)` or `Host(`example.com`) && PathPrefix(`/api`)` to map incoming requests to services.[6][5]
- **Attach services** that define upstream URLs or Kubernetes services, with load balancers distributing requests among instances.[5][2]
- **Add middlewares** for path rewrites, redirects, header manipulation, or compression as needed.[7][5]

This pattern is widely documented in tutorials, blog posts, and example configurations for both Docker Compose and Kubernetes.[8][2][5]

***

## 3. Kubernetes Ingress Controller Workflows

### 3.1 Scenario

Use Traefik as the main ingress controller for a Kubernetes cluster, handling external traffic for many services via native Kubernetes Ingress or Traefik CRDs (`IngressRoute`, `TraefikService`, `Middleware`).[9][2][5]

### 3.2 Typical workflows

1. **Simple ingress routing:**
   - Deploy Traefik via Helm as a LoadBalancer Service or DaemonSet.[10][11]
   - Use Kubernetes `Ingress` resources or `IngressRoute` CRDs to route external traffic into cluster services.

2. **CRD‑based advanced routing:**
   - Use `IngressRoute` to express complex routing (multiple routes, middlewares, TLS options) beyond what the standard `Ingress` supports.[9]
   - Use `TraefikService` for weighted load‑balancing and mirroring.

3. **Multi‑namespace and multi‑tenant ingress:**
   - Use namespaces, entrypoints, and host rules to isolate tenants.
   - Apply different middlewares per namespace or tenant (e.g., authentication, rate limits).

Traefik’s integration with Kubernetes is one of its primary selling points and is a widely used ingress solution in managed clusters like EKS, AKS, and GKE.[2][8][5]

***

## 4. Docker and Docker Swarm Routing Workflows

### 4.1 Scenario

Run Traefik as an edge router for Docker or Swarm, automatically discovering containers via labels and routing requests accordingly.[5][2]

### 4.2 Typical workflows

- **Single‑node Docker reverse proxy:**
  - Run Traefik side‑by‑side with app containers using Docker Compose.[2]
  - Use container labels such as `traefik.http.routers.myapp.rule=Host(`myapp.localhost`)` to define routes.

- **Swarm edge routing:**
  - Deploy Traefik as a Swarm service on manager nodes.
  - Attach labels to Swarm services to configure routing, TLS, and middlewares.

This pattern is documented extensively in community examples and official tutorials, showing how Traefik watches the Docker socket and updates routes as containers appear or disappear.[5][2]

***

## 5. API Gateway and Microservices Edge

### 5.1 Scenario

Use Traefik as an API gateway in front of microservices: centralizing auth, rate limiting, routing, and request/response transformations before traffic reaches internal services.[3][4][1]

### 5.2 Typical workflows

- **Central entrypoints** receive all external API traffic.
- **Routers** dispatch by hostname or path to microservices (e.g., `/users`, `/orders`).[6][5]
- **Middlewares** perform:
  - Authentication and authorization (basic auth, forwardAuth/OAuth2/OIDC).[7][5]
  - Rate limiting to protect services from overload.[7][5]
  - Request/response rewriting (headers, paths, redirects).
- **Per‑service policies** (timeouts, retries, circuit breakers) are configured in services/middlewares to improve resilience.[3][7]

This aligns with Traefik’s positioning as an API gateway for modern, cloud‑native applications.[4][1][3]

***

## 6. Automatic HTTPS, TLS Termination, and Redirects

### 6.1 Scenario

Provide HTTPS for services with automatic certificate management (Let’s Encrypt), TLS termination at the edge, and HTTP→HTTPS redirects.[3][2][5]

### 6.2 Typical workflows

- **Configure ACME/Let’s Encrypt** with HTTP‑01 or TLS‑ALPN‑01 challenge, using a certificate resolver.[5]
- **Enable TLS on routers** and reference the resolver, so certificates are requested and renewed automatically.
- **Enforce HTTPS** by:
  - Using middlewares that redirect HTTP to HTTPS.
  - Listening only on HTTPS entrypoints for sensitive services.
- **Tune TLS options** using `tlsOptions` (min version, cipher suites, client auth), sometimes combined with client certificate authentication for B2B or internal APIs.[12][5]

Automatic HTTPS is prominently highlighted in vendor and community material as one of Traefik’s most valuable features.[2][3][5]

***

## 7. Advanced HTTP Traffic Management (Canary, A/B, Blue‑Green)

### 7.1 Scenario

Control rollout of new versions using canary releases, A/B testing, and blue‑green deployments with Traefik’s traffic splitting and routing capabilities, often automated by tools such as Flagger.[13][14][10]

### 7.2 Canary and progressive delivery workflows

- **Weighted canary with TraefikService:**
  - Use `TraefikService` CRDs with `weighted` specs to split traffic between stable and canary services (e.g., 90/10, 75/25, etc.).[15][16][13][10][9]
  - Combine with metrics (Prometheus) to automate promotion or rollback using controllers like Flagger.[14][13][10]

- **Kubernetes + Flagger integration:**
  - Flagger creates ClusterIP services and `TraefikService` for stable/canary backends and drives traffic shifting based on KPIs such as success rate and latency.[13][10][14]

### 7.3 A/B and header‑based routing

- **Header/cookie‑based routing:**
  - Use `IngressRoute` or router rules to match headers (e.g., `X-Canary: true`) or cookies to direct specific users to a canary or experiment version.[16][5]
  - Often used for internal testing, beta users, or experiments.

### 7.4 Blue‑green patterns

- **Blue‑green via DNS or service swap:**
  - Maintain “blue” and “green” backends and switch traffic at DNS or service level while Traefik continues to route based on hostname.
  - Traefik’s dynamic discovery makes it easy to update backends without changing router rules.

These patterns are documented in progressive‑delivery tutorials and Flagger’s Traefik integration, and are widely adopted in Kubernetes environments.[10][14][13]

***

## 8. Traffic Mirroring / Shadow Launch

### 8.1 Scenario

Mirror a portion of live traffic from a stable service to a new version (shadow) without affecting user responses. This is used to validate performance and behavior under real load before any user‑visible rollout.[17][18][15][9]

### 8.2 Typical workflow

- **Define a `TraefikService` with `mirroring`**:
  - Primary service handles responses.
  - One or more mirror services receive mirrored copies of requests, optionally with configurable percentage of traffic.[18][15][17][9]
- **Deploy the new version** as the mirror backend.
- **Monitor metrics** (latency, error rates, resource usage) for the shadow service using Prometheus or other observability tools.
- **Disable mirroring** when testing is complete or promote the version using canary or blue‑green workflows.

Community examples and gists show `TraefikService` mirroring configurations for EKS and other Kubernetes environments.[19][17][18]

***

## 9. TCP Routing, TLS Passthrough, and IP Allowlisting

### 9.1 Scenario

Route non‑HTTP protocols such as PostgreSQL, Redis, MQTT, or custom TCP services through Traefik, using SNI or ports, optionally with IP allowlists and TLS passthrough.[20][21][22]

### 9.2 Typical workflows

- **SNI‑based TCP routing:**
  - Use `IngressRouteTCP` or TCP routers with rules like `HostSNI(`redis.example.com`)` to route TLS connections based on SNI.[21][22][12]

- **TLS passthrough vs termination:**
  - Passthrough mode forwards TLS untouched to the backend (common for databases that terminate TLS themselves).[12][6]
  - Termination at Traefik allows sharing certificates and centralizing TLS settings.

- **IP allowlisting (MiddlewareTCP):**
  - Use `MiddlewareTCP` (e.g., `ipAllowList`) to restrict which client IP ranges can connect to sensitive services such as databases.[22][23][20][21]

Examples from official docs, blogs, and community threads show TCP routers for PostgreSQL and Redis, combined with IP allowlists and custom entrypoints.[23][20][21][22][12]

***

## 10. Security, Authentication, and Authorization

### 10.1 Scenario

Secure access to services and the Traefik dashboard/API using authentication, authorization, and network controls.[24][25][7][5]

### 10.2 Typical workflows

- **Dashboard and API protection:**
  - Ensure `api@internal` and the dashboard are only exposed on internal entrypoints or behind authentication middlewares.[25][24][5]
  - Apply basic auth or forward auth and limit accessible paths (e.g., `/api`, `/dashboard`).

- **User authentication:**
  - Use HTTP middlewares for basic auth or digest auth.
  - Use `forwardAuth` to integrate with external identity providers (OAuth2, OIDC, SSO gateways), centralizing auth at the edge.[7][5]

- **Network‑level controls:**
  - Apply IP whitelist/allowlist middlewares to restrict access to admin interfaces or internal tools.

These patterns are widely recommended in official docs and community posts to avoid accidental exposure of Traefik’s admin surface and sensitive services.[24][25][5][7]

***

## 11. Multi‑Cluster, Multi‑Tenant, and Multi‑Environment Routing

### 11.1 Scenario

Support multiple environments (dev, staging, production), tenants, or clusters, while using Traefik as a central or per‑cluster edge router.[1][3][5]

### 11.2 Typical workflows

- **Environment separation:**
  - Use different entrypoints, hostnames, or paths to separate environments (e.g., `api.dev.example.com` vs `api.example.com`).
  - Use different Traefik instances per cluster or per environment.

- **Tenant isolation:**
  - Route by tenant subdomain (`tenantA.example.com`, `tenantB.example.com`) with corresponding services and middlewares.
  - Apply per‑tenant rate limits, auth, and IP restrictions.

- **Hybrid/multi‑cloud setups:**
  - Use Traefik in each cluster and front with DNS‑based traffic steering or global load balancers.

Traefik’s dynamic configuration and provider model make it suitable for complex, multi‑tenant architectures that require fine‑grained routing and security at the edge.[1][3][5]

***

## 12. Observability, Metrics, and Tracing

### 12.1 Scenario

Monitor traffic, errors, and latency through metrics, logs, and distributed tracing to troubleshoot and optimize services.[13][10][5]

### 12.2 Typical workflows

- **Metrics integration:**
  - Enable Prometheus metrics and scrape Traefik endpoints.[11][10]
  - Use dashboards (Grafana, built‑in tools) to track request rates, error rates, latency, and backend health.

- **Access logs and log shipping:**
  - Configure structured access logs and ship them to log aggregators for analysis.

- **Distributed tracing:**
  - Enable tracing integrations (Jaeger, Zipkin, etc.) to track request flows through Traefik to downstream services.

These workflows are essential when Traefik is used with progressive delivery tools like Flagger, which rely heavily on metrics to make rollout decisions.[14][10][13]

***

## 13. Plugin and Middleware Extension Workflows

### 13.1 Scenario

Extend Traefik with custom logic using plugins and custom middlewares, beyond the built‑in set.[5][7]

### 13.2 Typical workflows

- **Plugin middlewares:**
  - Use Go‑based or WASM‑based plugins from the Traefik Hub/registry or internal repositories.
  - Configure plugins via dynamic config like any other middleware.

- **Custom transformations:**
  - Implement request/response transformation, custom authentication, A/B test assignment, or bespoke logging.

This extension pattern is increasingly common in organizations that need domain‑specific behavior at the edge while keeping the core proxy standardized.[7][5]

***

## 14. Migration and Consolidation Workflows

### 14.1 Scenario

Migrate from legacy reverse proxies (NGINX, HAProxy, Apache, cloud‑specific load balancers) to Traefik to gain dynamic discovery, automatic TLS, and modern routing features.[1][3][2]

### 14.2 Typical workflows

- **Side‑by‑side deployment:**
  - Run Traefik in parallel with the existing proxy.
  - Duplicate routes in Traefik and test using internal DNS or Host headers.

- **Gradual cutover:**
  - Switch DNS, update load balancer targets, or change Kubernetes Service selectors to shift traffic from the old proxy to Traefik.[3]

- **Decommission legacy components:**
  - Once Traefik is stable in production, retire legacy proxies.

Vendor guides and community blogs often describe this migration as a staged process, leveraging Traefik’s compatibility with existing Kubernetes services and DNS‑based routing.[1][2][3]

***

## 15. Summary of Traefik Workflows

Across real‑world deployments, the main categories of Traefik workflows are:

- **Core reverse proxy and ingress** (host/path routing for HTTP services).
- **Kubernetes ingress controller** deployment with CRDs for advanced routing.
- **Container platform routing** for Docker and Swarm.
- **API gateway** patterns with auth, rate limiting, and transformations.
- **TLS automation** and HTTPS enforcement.
- **Advanced delivery**: canary, A/B, blue‑green, and traffic mirroring.
- **TCP routing** and network security for non‑HTTP services.
- **Security hardening** and dashboard protection.
- **Multi‑tenant and multi‑environment architectures.**
- **Observability and integration with metrics/tracing.**
- **Extensibility via plugins and middlewares.**
- **Migration from legacy reverse proxies to Traefik.**

These workflows reflect how teams are actually using Traefik in the field, as seen in official documentation, third‑party tutorials, and open‑source progressive delivery tooling.[16][10][13][2][3][1][5]