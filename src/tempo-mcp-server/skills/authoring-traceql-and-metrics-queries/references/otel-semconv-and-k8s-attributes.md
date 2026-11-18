# OpenTelemetry Semantic Conventions (v1.20 vs v1.24+) & Kubernetes Attributes

## 1. Dual-Schema HTTP, RPC, Database, and Network Attributes

Always verify which schema version a service emits using `tempo_get_attribute_names` (`scope="span"`).

| Domain | Legacy OTel Semconv (<= v1.20) | Stable OTel Semconv (v1.24+) | Dual-Schema TraceQL Selector Pattern |
| :--- | :--- | :--- | :--- |
| HTTP Status Code | `span.http.status_code` | `span.http.response.status_code` | `{ span.http.status_code >= 500 \|\| span.http.response.status_code >= 500 }` |
| HTTP Method | `span.http.method` | `span.http.request.method` | `{ span.http.method = "POST" \|\| span.http.request.method = "POST" }` |
| HTTP Route | `span.http.route` | `span.http.route` | `{ span.http.route = "/api/v1/checkout" }` |
| URL Path | `span.http.target` | `span.url.path` | `{ span.http.target =~ "/orders.*" \|\| span.url.path =~ "/orders.*" }` |
| Peer / Server Host | `span.net.peer.name` | `span.server.address` | `{ span.net.peer.name = "db.internal" \|\| span.server.address = "db.internal" }` |
| Peer / Server Port | `span.net.peer.port` | `span.server.port` | `{ span.net.peer.port = 5432 \|\| span.server.port = 5432 }` |
| Database System | `span.db.system` | `span.db.system.name` | `{ span.db.system = "postgresql" \|\| span.db.system.name = "postgresql" }` |
| Messaging System | `span.messaging.system` | `span.messaging.system` | `{ span.messaging.system = "kafka" }` |

## 2. Resource & Kubernetes Attributes (`scope="resource"`)

- Service identity: `resource.service.name`, `resource.service.namespace`, `resource.service.version`, `resource.service.instance.id`
- Environment: `resource.deployment.environment` or `resource.deployment.environment.name`
- Kubernetes metadata: `resource.k8s.cluster.name`, `resource.k8s.namespace.name`, `resource.k8s.pod.name`, `resource.k8s.node.name`, `resource.k8s.deployment.name`, `resource.k8s.container.name`
