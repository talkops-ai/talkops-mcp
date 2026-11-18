# Production TraceQL Query Pack

## 1. Error & Exception Queries

- **Failing server spans with projected attributes**:
  `{ kind = server && status = error } | select(resource.service.name, span.http.route, status) with(most_recent=true)`
- **Spans recording an unhandled exception event**:
  `{ event:name = "exception" } | select(resource.service.name, event.exception.type, event.exception.message)`
- **Downstream error propagation (healthy gateway calling failing downstream)**:
  `{ resource.service.name = "api-gateway" && status = ok } >> { status = error }`
- **Missing expected child span (broken async handoff or dropped span)**:
  `{ resource.service.name = "order-service" && name = "POST /orders" } !>> { resource.service.name = "payment-service" }`

## 2. Latency & N+1 Detection Queries

- **N+1 database calls inside a single trace**:
  `{ resource.service.name = "checkout" } >> { span.db.system != "" } | count() > 20`
- **Sibling database queries executed by the same parent span**:
  `{ span.db.system = "postgresql" } ~ { span.db.system = "postgresql" }`
- **Slow client RPCs exceeding 500ms**:
  `{ kind = client && duration > 500ms } | select(resource.service.name, name, duration)`

## 3. TraceQL Metrics Queries

- **Top 10 error-producing service routes**:
  `{ status = error } | rate() by (resource.service.name, span.http.route) | topk(10)`
- **Service p99 latency by Kubernetes pod**:
  `{ resource.service.name = "checkout" && kind = server } | quantile_over_time(duration, 0.99) by (resource.k8s.pod.name)`
- **Service-to-service call rate edge discovery**:
  `{ kind = client } >> { kind = server } | rate() by (resource.service.name)`
- **Automated error cohort comparison**:
  `{ resource.service.name = "checkout" } | compare({ status = error }, 10)`
