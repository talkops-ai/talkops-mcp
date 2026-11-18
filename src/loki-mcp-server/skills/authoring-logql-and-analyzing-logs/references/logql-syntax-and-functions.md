# LogQL Syntax and Functions Reference

## Table of Contents
1. [Stream Selectors](#1-stream-selectors)
2. [Line Filter Expressions](#2-line-filter-expressions)
3. [Parser Expressions](#3-parser-expressions)
4. [Label and Structured Metadata Filters](#4-label-and-structured-metadata-filters)
5. [Format Expressions](#5-format-expressions)
6. [Metric Queries: Log Range Aggregations](#6-metric-queries-log-range-aggregations)
7. [Unwrapped Range Aggregations](#7-unwrapped-range-aggregations)
8. [Vector Aggregation Operators](#8-vector-aggregation-operators)
9. [Binary Operators, Offset, and IP Matching](#9-binary-operators-offset-and-ip-matching)

---

## 1. Stream Selectors

Every LogQL query starts with a stream selector enclosed in `{}` that filters Loki's TSDB index labels:

| Operator | Meaning | Example |
|----------|---------|---------|
| `=` | Exact equality | `{service_name="checkout"}` |
| `!=` | Not equal | `{env!="dev"}` |
| `=~` | RE2 regex match (fully anchored) | `{service_name=~"checkout\|payment"}` |
| `!~` | RE2 regex does not match | `{namespace!~"kube-.*"}` |

**Rules**:
- At least one matcher must require a non-empty value (e.g., `{app=~".*"}` alone is rejected by Loki).
- Only indexed labels belong inside `{}`. High-cardinality fields (`trace_id`, `user_id`, `request_id`, `pod_ip`) belong in Loki 3.x structured metadata or line filters.

---

## 2. Line Filter Expressions

Line filters perform distributed substring or regex matching against raw log lines **before** parsing:

| Operator | Description | Example |
|----------|-------------|---------|
| `\|=` | Log line contains exact substring (case-sensitive, Bloom-filter accelerated) | `\|= "timeout"` |
| `!=` | Log line does not contain substring | `!= "healthcheck"` |
| `\|~` | Log line matches RE2 regular expression | `\|~ "(?i)error\|exception\|panic"` |
| `!~` | Log line does not match RE2 regular expression | `!~ "GET /healthz"` |

**Tips**:
- Chain multiple `|=` filters from most selective to least selective (`|= "trace_id" |= "error"`).
- Prefer `|=` over `|~` whenever possible; `|=` uses SIMD-accelerated substring search and Loki 3.x Bloom filters.

---

## 3. Parser Expressions

Parsers extract fields from the log line into temporary labels for filtering and aggregation:

### JSON Parser (`| json`)
- Extract all fields (expensive on deeply nested JSON):
  ```logql
  {service_name="api"} |= "error" | json
  ```
- Extract only specific fields (recommended):
  ```logql
  {service_name="api"} |= "error" | json status="http.status", latency_ms="http.duration_ms", first_err="errors[0].code"
  ```

### Logfmt Parser (`| logfmt`)
- Standard `key=value` parsing:
  ```logql
  {service_name="auth"} |= "level=error" | logfmt
  ```
- Targeted extraction with flags (`--strict`, `--keep-empty`):
  ```logql
  {service_name="auth"} | logfmt --strict user_id, duration
  ```

### Pattern Parser (`| pattern`)
Fast, non-regex structural extraction using `<field_name>` and `<_>` (unnamed wildcard):
```logql
{job="nginx"} | pattern `<ip> - <_> [<_>] "<method> <uri> <_>" <status> <bytes>`
```

### Regexp Parser (`| regexp`)
Uses named capture groups `(?P<name>pattern)`:
```logql
{job="custom"} | regexp `(?P<level>[A-Z]+) \[(?P<thread>[^\]]+)\] (?P<msg>.*)`
```

### Unpack Parser (`| unpack`)
Unpacks embedded JSON maps created by Promtail/Alloy `pack` stage.

---

## 4. Label and Structured Metadata Filters

Filter on indexed labels, Loki 3.x structured metadata, or fields extracted by a parser:

- **String comparisons**: `=`, `!=`, `=~`, `!~`
- **Numeric comparisons**: `>`, `>=`, `<`, `<=`
- **Duration & Byte comparisons**:
  ```logql
  {service_name="api"} | json | duration > 500ms and bytes_sent > 10MB
  ```
- **Boolean logic**: Combine with `and`, `or`, and parentheses:
  ```logql
  {service_name="api"} | json | (status >= 500 or status = 429) and method != "OPTIONS"
  ```
- **Ignoring parser errors**:
  ```logql
  {service_name="api"} | json | __error__=""
  ```

---

## 5. Format Expressions

- **`| line_format`**: Rewrites the log line using Go `text/template` syntax:
  ```logql
  {service_name="api"} | json | line_format "{{.level}} [{{.trace_id}}] {{.msg}} ({{.duration_ms}}ms)"
  ```
- **`| label_format`**: Renames or modifies labels:
  ```logql
  {service_name="api"} | json | label_format endpoint="{{.method}} {{.route}}"
  ```
- **`| drop` / `| keep`**: Drops or retains labels/structured metadata in query output:
  ```logql
  {service_name="api"} | json | drop pod_ip, container_id
  ```

---

## 6. Metric Queries: Log Range Aggregations

Operate directly on log stream counts/volumes over a `[range]` window:

| Function | Purpose | Example |
|----------|---------|---------|
| `count_over_time(log- pipeline [range])` | Count of matching log lines in `[range]` | `count_over_time({service_name="api"} \|= "error" [5m])` |
| `rate(log-pipeline [range])` | Matching log lines per second | `rate({service_name="api"} \|= "error" [5m])` |
| `bytes_over_time(log-pipeline [range])` | Total uncompressed bytes in `[range]` | `bytes_over_time({namespace="prod"} [1h])` |
| `bytes_rate(log-pipeline [range])` | Uncompressed bytes per second | `bytes_rate({namespace="prod"} [5m])` |
| `absent_over_time(log-pipeline [range])` | Returns 1 if no logs appear in `[range]` | `absent_over_time({service_name="payment"} [10m])` |

---

## 7. Unwrapped Range Aggregations

Extract a numeric label via `| unwrap <field>` (with optional conversion functions `duration_seconds(label)`, `duration(label)`, `bytes(label)`) and aggregate over `[range]`:

```logql
quantile_over_time(0.95,
  {service_name="api"} |= "latency"
  | json latency="duration"
  | unwrap duration_seconds(latency)
  | __error__="" [5m]
) by (route)
```

Supported functions:
- `rate_counter(unwrapped-pipeline [range])`
- `sum_over_time`, `avg_over_time`, `min_over_time`, `max_over_time`
- `stddev_over_time`, `stdvar_over_time`
- `quantile_over_time(phi, unwrapped-pipeline [range])`
- `first_over_time`, `last_over_time`

> **Always include `| __error__=""` after `| unwrap <field>`** so malformed lines do not fail the metric query with `SampleExtractionErr`.

---

## 8. Vector Aggregation Operators

Aggregate across streams using `by (label1, label2)` or `without (label1)`:
- `sum`, `avg`, `min`, `max`, `count`, `stddev`, `stdvar`
- `topk(k, expr)`, `bottomk(k, expr)`
- `sort(expr)`, `sort_desc(expr)`

---

## 9. Binary Operators, Offset, and IP Matching

- **Arithmetic**: `+`, `-`, `*`, `/`, `%`, `^`
- **Comparison**: `==`, `!=`, `>`, `>=`, `<`, `<=` (use `bool` modifier to return `0`/`1`)
- **Vector matching**: `on (labels)`, `ignoring (labels)`, `group_left`, `group_right`
- **Time Shift (`offset`)**: Compare current rates against historical baselines:
  ```logql
  sum(rate({service_name="api"} |= "error" [5m]))
  /
  sum(rate({service_name="api"} |= "error" [5m] offset 1d))
  ```
- **IP CIDR matching (`ip()`)**:
  ```logql
  {job="nginx"} | logfmt | remote_addr = ip("10.0.0.0/8")
  ```
