# LogQL Quick Reference


## Query Types

- **Log queries** return log lines.
- **Metric queries** wrap a log query with a `[range]` selector and apply aggregation functions (similar to PromQL).


## Stream Selectors
```logql
{app="checkout"}                    # Exact match
{app="checkout", namespace="prod"}  # Multiple labels
{app=~"check.*"}                    # Regex match
{app!="internal"}                   # Not equal
{app!~"test.*"}                     # Not regex match
```
- Use precise labels like `app`, `namespace`, `cluster` to limit scanned streams.
- **Anchoring:** Stream selector regex (`=~`, `!~`) is **fully anchored** — it must match the entire label value. Use `{app=~".*checkout.*"}` to match a substring, or prefer line filters for substring searches.


## Line Filters
```logql
{app="checkout"} |= "error"         # Contains (case-sensitive)
{app="checkout"} |~ "(?i)error"     # Contains (case-insensitive regex)
{app="checkout"} != "debug"         # Does not contain
{app="checkout"} !~ "health.*check" # Does not match regex
```
- Prefer `|=`/`!=` over regex for performance.
- Line filter regex (`|~`, `!~`) is **unanchored** — it matches substrings (unlike stream selector regex).
- **Chaining:** Filters can be chained; all must match:
```logql
{app="api"} |= "error" != "timeout" |~ "5\\d{2}"
```


## Parsers
```logql
# JSON logs — extract all fields
{app="checkout"} | json

# JSON — extract specific fields only (better performance)
{app="checkout"} | json status="http.status", uid="user_id"

# JSON — nested fields and special characters
{app="checkout"} | json level='["@l"]'

# Key=value logs — extract all fields
{app="checkout"} | logfmt

# Key=value — extract specific fields only
{app="checkout"} | logfmt level, duration

# Pattern parser (preferred over regexp)
{app="checkout"} | pattern "<ip> - - [<timestamp>] \"<method> <path> <_>\" <status> <bytes>"

# Regex parser (when pattern is not enough)
{app="nginx"} | regexp `(?P<ip>\S+) - - \[(?P<ts>.+?)\] "(?P<method>\S+) (?P<path>\S+)" (?P<status>\d+)`

# Unpack (for packed log formats)
{app="checkout"} | unpack
```


## Label Filters (after parsing)
Supported operators on parsed labels:

- Equality: `=`, `==`, `!=`
- Comparison: `>`, `>=`, `<`, `<=` (numeric)
- Regex: `=~`, `!~`
- Combine with `and` / `or`

```logql
{app="checkout"} | json | status >= 500
{app="checkout"} | json | level = "error"
{app="checkout"} | logfmt | duration > 1s
{app="checkout"} | json | method =~ "POST|PUT"
{app="checkout"} | json | status >= 500 and method != "HEAD"
```


## Structured Metadata & Special Labels
```logql
# Filter by structured metadata (NOT in stream selector)
{app="checkout"} | trace_id = "abc123"
{app="checkout"} | user_id = "user-456"

# Drop lines where parsing failed (json/pattern/regexp)
{app="api"} | json | __error__ = ""
```
- `__error__` is set when a parser or unwrap fails; filtering on `__error__=""` is common before range aggregations.
- `__error_details__` provides the specific parse failure reason (e.g. which field failed).


## Label Manipulation Stages
```logql
# Drop specific labels from the output
{app="api"} | json | drop pod, instance

# Keep only specific labels, remove all others
{app="api"} | json | keep app, level, status
```
- `drop` and `keep` control which labels appear in query results without affecting the log lines themselves.


## Decolorize Stage
```logql
# Strip ANSI color codes from log lines (useful for CLI tool output)
{app="cli-tool"} | decolorize
```
- Place before parsers so that ANSI escape sequences don't interfere with `json`, `logfmt`, or `pattern` extraction.


## Formatting Stages
```logql
# line_format: change rendered line using Go templates
{app="ingress"} | json
| line_format "{{.method}} {{.path}} => {{.status}} in {{.duration_ms}}ms"

# label_format: create/modify labels
{app="api"} | json
| label_format route="{{.path}}", level="{{.severity}}"
```
- Both stages support Go template functions as documented in Loki's template functions reference.


## Unwrap (metrics from structured logs)
Use `unwrap` to expose a parsed label as a numeric sample for range aggregations.

```logql
# Sum a numeric field from key=value logs
sum_over_time(
  {app="billing"} | logfmt | unwrap total_amount [1h]
)

# 95th percentile latency by route (JSON logs)
quantile_over_time(
  0.95,
  {app="api"} | json | unwrap duration_ms [5m]
) by (route)

# Convert human-readable duration strings (e.g. "12s30ms") to seconds
avg_over_time(
  {app="api"} | logfmt | unwrap duration_seconds(latency) [5m]
)

# Convert human-readable byte strings (e.g. "5 MiB") to numeric bytes
sum_over_time(
  {app="api"} | logfmt | unwrap bytes(payload_size) [1h]
)
```
- `duration_seconds()` and `bytes()` are conversion functions that can wrap the unwrap label.
- Only label filter expressions (e.g. `| __error__=""`) are allowed after `| unwrap`.


## Metric Queries (range selectors)

A metric query wraps a log query in `[range]` and applies functions.

```logql
# Count logs per second
rate({app="checkout"} [5m])

# Count log lines
count_over_time({app="checkout"} |= "error" [1h])

# Sum extracted values
sum(rate({app="checkout"} | json | unwrap duration [5m])) by (method)

# Bytes rate
bytes_rate({app="checkout"} [5m])

# Top-K by status
topk(5, sum(rate({app="checkout"} [5m])) by (status))
```

### Range aggregations on log lines
```text
rate(log_range)           # Entries per second
count_over_time(range)    # Total entries in range
bytes_rate(range)         # Bytes per second
bytes_over_time(range)    # Total bytes in range
absent_over_time(range)   # 1 when no logs in range (useful for "no logs" alerts)
```


### Range aggregations on unwrapped values
The log query must end with `| unwrap <label>` (and optional `__error__` filter).

```text
rate(unwrapped_range)
sum_over_time(unwrapped_range)
avg_over_time(unwrapped_range)
min_over_time(unwrapped_range)
max_over_time(unwrapped_range)
first_over_time(unwrapped_range)     # First value in the window
last_over_time(unwrapped_range)      # Last value in the window
stdvar_over_time(unwrapped_range)
stddev_over_time(unwrapped_range)
quantile_over_time(φ, unwrapped_range)  # φ between 0 and 1
```

Example:
```logql
# Average latency by cluster
avg_over_time(
  {container="ingress-nginx",service="hosted-grafana"}
  | json
  | unwrap response_latency_seconds
  | __error__ = "" [1m]
) by (cluster)
```


## Binary Operators & Grouping (metrics)

### Arithmetic, comparison, and set operators
```text
+  -  *  /  %  ^       # Arithmetic (^ = power)
== != > >= < <=        # Comparison (filter by default)
and or unless          # Logical/set
```

### The `bool` modifier
By default, comparison operators **filter** — non-matching series are dropped.
Adding `bool` returns `1` (true) or `0` (false) instead.

```logql
# Returns 1 for services with errors, 0 otherwise (useful for alerting)
count_over_time({app="api"} |= "error" [5m]) > bool 0
```

### Example: error rate percentage by app
```logql
sum(rate({app="api"} |= "error" [5m])) by (app)
/
sum(rate({app="api"} [5m])) by (app)
* 100
```

### Grouping
```logql
# Group by labels
sum(rate({app="api"} |= "error" [5m])) by (app, namespace)

# Drop specific labels from the result
max_over_time(
  {app="api"} | json | unwrap duration_ms [5m]
) without (pod)
```

### Vector matching modifiers
When performing binary operations between two vectors:

```text
on(label_list)         # Match only on these labels
ignoring(label_list)   # Ignore these labels when matching
group_left(labels)     # Many-to-one: left side has higher cardinality
group_right(labels)    # One-to-many: right side has higher cardinality
```


## Built-in Functions

```logql
# label_replace: modify/rename labels on metric vectors
label_replace(
  sum(rate({app="api"} [5m])) by (app),
  "service", "$1", "app", "(.*)"
)

# vector: returns a scalar as a vector with no labels
# Useful as a default value when a query returns no data
sum(rate({app="api"} |= "error" [5m])) or vector(0)
```


## Regex and Pattern Best Practices
```logql
# Pattern preferred over regex when possible
{app="web"} | pattern "<ip> - - [<ts>] \"<method> <path> <_>\" <status> <bytes>"

# Regex when you need arbitrary extraction
{job="integrator"}
| regexp `.*W=(?P<writes>.*?),`
| unwrap writes
| __error__ = "" [5m]
```


## Pipeline Order
```text
{stream_selector} line_filter | parser | label_filter | unwrap | line_format | label_format | drop/keep
```
- First: narrow with labels and simple line filters.
- Then: parse and filter on labels.
- Unwrap numeric fields for metric queries.
- Finally: format lines/labels for display or downstream use, drop/keep for cleanup.


## Duration, Byte Literals & Offset
- Duration: `1ns`, `1us`, `1ms`, `1s`, `1m`, `1h`, `1d`, `1w`
- Bytes: `1B`, `1KB`, `1MB`, `1GB`, `1TB`
- Offset: shift the evaluation window for comparisons in time.

```logql
# Window is last 5m, shifted back by 1h
rate({app="api"} [5m] offset 1h)
```


## Performance Tips
- Use precise label selectors (`app`, `namespace`, `cluster`, `job`) to reduce the number of scanned streams.
- Prefer `|= "text"` / `!= "text"` over regex when possible; use regex only where needed.
- Apply line filters before parsers; parse (`json`, `logfmt`, `pattern`, `regexp`) only after you've narrowed down the volume.
- Use parameterised `| json field1, field2` instead of bare `| json` to extract only the fields you need.
- Filter `| __error__ = ""` after parsers and unwrap to avoid polluting metric aggregations with parse failures.