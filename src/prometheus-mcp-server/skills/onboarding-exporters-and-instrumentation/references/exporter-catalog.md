# Prometheus Supported Exporters Catalog

Use these exact `exporter_type` identifiers when invoking `prom_install_exporter` or `prom_uninstall_exporter`:

| `exporter_type` | Target System | Default Port | Workload Scope | Key Required / Optional Config Fields (`exporter_config`) |
| :--- | :--- | :--- | :--- | :--- |
| `node_exporter` | Linux OS & hardware metrics | `9100` | `daemonset` | None (mounts host `/proc` and `/sys`) |
| `windows_exporter` | Windows Server OS metrics | `9182` | `daemonset` | None (VM / Windows node agent) |
| `kube-state-metrics` | Kubernetes API object state (`kube_pod_*`, `kube_deployment_*`) | `8080` | `deployment` | Automatically provisions `ServiceAccount`, `ClusterRole`, and `ClusterRoleBinding` |
| `postgres_exporter` | PostgreSQL database metrics (`pg_up`, `pg_stat_*`) | `9187` | `deployment` | `DATA_SOURCE_NAME` (or `DATA_SOURCE_URI`, `DATA_SOURCE_USER`, `DATA_SOURCE_PASS`) |
| `mysqld_exporter` | MySQL / MariaDB metrics (`mysql_up`, `mysql_global_status_*`) | `9104` | `deployment` | `DATA_SOURCE_NAME` (`user:pass@(host:3306)/`) |
| `mongodb_exporter` | MongoDB replica set & shard metrics | `9216` | `deployment` | `MONGODB_URI` (`mongodb://exporter:pass@mongo:27017`) |
| `redis_exporter` | Redis cache & cluster metrics (`redis_up`, `redis_connected_clients`) | `9121` | `sidecar` / `deployment` | `REDIS_ADDR` (`redis://redis:6379`), optional `REDIS_PASSWORD` |
| `memcached_exporter` | Memcached statistics (`memcached_up`) | `9150` | `deployment` | `MEMCACHED_ADDRESS` (`memcached:11211`) |
| `kafka_exporter` | Kafka broker & consumer group lag (`kafka_consumergroup_lag`) | `9308` | `deployment` | `KAFKA_BROKERS` (`kafka-1:9092,kafka-2:9092`), optional `KAFKA_SASL_USER` |
| `rabbitmq_exporter` | RabbitMQ queue depth & node metrics | `9419` | `deployment` | `RABBIT_URL`, `RABBIT_USER`, `RABBIT_PASSWORD` |
| `elasticsearch_exporter` | Elasticsearch / OpenSearch cluster & index metrics | `9114` | `deployment` | `ES_URI` (`http://elasticsearch:9200`), optional `ES_ALL=true`, `ES_INDICES=true` |
| `nginx_exporter` | NGINX `stub_status` metrics (`nginx_connections_active`) | `9113` | `sidecar` | `SCRAPE_URI` (`http://localhost:8080/stub_status`) |
| `apache_exporter` | Apache HTTPD `mod_status` metrics | `9117` | `sidecar` | `SCRAPE_URI` (`http://localhost/server-status?auto`) |
| `haproxy_exporter` | HAProxy backend/frontend metrics | `9101` | `deployment` | `HAPROXY_SCRAPE_URI` (`http://haproxy:8404/stats;csv`) |
| `blackbox_exporter` | Synthetic HTTP, HTTPS, DNS, TCP, ICMP probes | `9115` | `deployment` | Provisions `ConfigMap` for probe modules (`http_2xx`, `tcp_connect`) |
| `snmp_exporter` | Network switch/router SNMP polling | `9116` | `deployment` | Provisions `ConfigMap` at `/etc/prometheus/snmp` |
| `statsd_exporter` | StatsD UDP/TCP to Prometheus bridge | `9102` (metrics), `9125` (UDP) | `deployment` | Exposes both TCP metrics port and UDP ingest port |
| `jmx_exporter` | JVM / Kafka / Cassandra JMX beans | `5556` | `sidecar` | `JMX_CONFIG_PATH` (`/etc/jmx/config.yml`) |
| `php_fpm_exporter` | PHP-FPM FastCGI worker pool & queue telemetry | `9253` | `sidecar` | `PHP_FPM_SCRAPE_URI` (`tcp://127.0.0.1:9000/status`) |
| `aws_cloudwatch_exporter` | AWS CloudWatch metrics exporter (YACE) | `5000` | `deployment` | `CLOUDWATCH_CONFIG_PATH` (`/tmp/config.yml`), `AWS_REGION`, optional `AWS_ROLE_ARN` |

---

## Starter Verification Queries & Alert Rules by Exporter Family

After deploying an exporter with `prom_install_exporter` and verifying scrape health with `prom_verify_metrics_endpoint`, recommend and validate (`prom_validate_rules`) these baseline alerts:

- **Infrastructure (`node_exporter` / `windows_exporter` / `kube-state-metrics`)**:
  - Verification metric: `node_uname_info`, `windows_cs_physical_memory_bytes`, `kube_pod_status_phase`
  - Starter alerts:
    - `NodeFilesystemAlmostOutOfSpace`: `(node_filesystem_avail_bytes{fstype!~"tmpfs|overlay"} / node_filesystem_size_bytes{fstype!~"tmpfs|overlay"}) * 100 < 10` (`for: 10m`)
    - `NodeMemoryPressure`: `(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100 > 90` (`for: 10m`)
    - `KubePodCrashLooping`: `increase(kube_pod_container_status_restarts_total[15m]) > 3` (`for: 5m`)
- **Databases (`postgres_exporter` / `mysqld_exporter` / `mongodb_exporter`)**:
  - Verification metrics: `pg_up == 1`, `mysql_up == 1`, `mongodb_up == 1`
  - Starter alerts:
    - `DatabaseExporterTargetDown`: `(pg_up == 0) or (mysql_up == 0) or (mongodb_up == 0)` (`for: 2m`)
    - `PostgresTooManyConnections`: `sum by (instance) (pg_stat_activity_count) > (pg_settings_max_connections * 0.85)` (`for: 5m`)
- **Caches & Queues (`redis_exporter` / `memcached_exporter` / `kafka_exporter` / `rabbitmq_exporter`)**:
  - Verification metrics: `redis_up == 1`, `memcached_up == 1`, `kafka_brokers > 0`, `rabbitmq_build_info`
  - Starter alerts:
    - `RedisOutOfMemoryNearMax`: `(redis_memory_used_bytes / redis_memory_max_bytes) * 100 > 90 and redis_memory_max_bytes > 0` (`for: 5m`)
    - `KafkaConsumerGroupLagHigh`: `sum by (consumergroup, topic) (kafka_consumergroup_lag) > 10000` (`for: 10m`)
- **Web / Proxies / Synthetic (`nginx_exporter` / `haproxy_exporter` / `apache_exporter` / `php_fpm_exporter` / `blackbox_exporter`)**:
  - Verification metrics: `nginx_up == 1`, `haproxy_up == 1`, `probe_success == 1`
  - Starter alerts:
    - `BlackboxProbeFailed`: `probe_success == 0` (`for: 2m`)
    - `BlackboxSslCertExpiringSoon`: `(probe_ssl_earliest_cert_expiry - time()) / 86400 < 14` (`for: 1h`)

---

## Sidecar Scrape Pattern (`jmx_exporter` `:5556` & `nginx_exporter` `:9113`)

Because `jmx_exporter` (`containerPort: 5556`, named `jmx-metrics`) and `nginx_exporter` (`containerPort: 9113`, named `nginx-metrics`) attach to each Pod's `127.0.0.1` loopback interface, always include a `PodMonitor` (or headless `ServiceMonitor`) in the workload's namespace so Prometheus scrapes every replica directly and preserves per-pod `pod` and `instance` labels:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PodMonitor
metadata:
  name: sidecar-exporters-monitor
  namespace: <target-namespace>
  labels:
    release: kube-prometheus-stack
spec:
  selector:
    matchExpressions:
      - key: app.kubernetes.io/name
        operator: In
        values: ["ad", "kafka", "image-provider"]
  podMetricsEndpoints:
    - port: jmx-metrics      # containerPort: 5556 (jmx_exporter)
      path: /metrics
      interval: 30s
    - port: nginx-metrics    # containerPort: 9113 (nginx_exporter)
      path: /metrics
      interval: 30s
```
