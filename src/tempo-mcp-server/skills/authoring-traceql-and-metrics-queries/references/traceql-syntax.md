# TraceQL 2.x / 3.x Syntax Reference

## Table of Contents

1. [Attribute Scopes & Intrinsics](#1-attribute-scopes--intrinsics)
2. [Comparison & Regex Operators](#2-comparison--regex-operators)
3. [Structural & Descendant Operators](#3-structural--descendant-operators)
4. [Trace-Level Aggregators & Pipeline Clauses](#4-trace-level-aggregators--pipeline-clauses)
5. [Query Hints (`with(...)`)](#5-query-hints-with)

## 1. Attribute Scopes & Intrinsics

- **Intrinsic fields** (unscoped):
  - `duration`, `traceDuration`, `name`, `status` (`ok`, `error`, `unset`), `kind` (`server`, `client`, `producer`, `consumer`, `internal`), `rootServiceName`, `rootName`, `span:id`, `trace:id`.
- **Scoped attributes**:
  - `resource.<key>`: Resource-level attributes (`resource.service.name`, `resource.k8s.pod.name`).
  - `span.<key>`: Span-level attributes (`span.http.route`, `span.db.system`).
  - `.key`: Unscoped attribute lookup across resource and span scopes (slower than explicit scope).
  - `event:<field>` / `event.<key>`: Span events (`{ event:name = "exception" && event.exception.type = "TimeoutError" }`).
  - `link:<field>` / `link.<key>`: Span links (`{ link:traceID != "" }`, `{ link:spanID != "" }`).
  - `instrumentation:<field>`: Instrumentation scope metadata (`{ instrumentation:name = "io.opentelemetry.okhttp-3.0" }`).

## 2. Comparison & Regex Operators

- Equality / inequality: `=`, `!=`
- Numeric / duration comparisons: `>`, `>=`, `<`, `<=` (duration units: `ns`, `us`, `ms`, `s`, `m`, `h`)
- Regex match / negation: `=~`, `!~`
- Boolean combinators inside `{ ... }`: `&&` (AND), `||` (OR)
- Span-set combinators outside `{ ... }`: `&&`, `||`

## 3. Structural & Descendant Operators

- `{A} > {B}`: Span `{A}` is the **direct parent** of span `{B}`.
- `{A} >> {B}`: Span `{A}` is an **ancestor** (at any depth) of span `{B}`.
- `{A} ~ {B}`: Span `{A}` and span `{B}` are **siblings** sharing the same parent span.
- `{A} !> {B}`: Span `{A}` has **no direct child** matching `{B}`.
- `{A} !>> {B}`: Span `{A}` has **no descendant** matching `{B}`.
- `{A} >> {B} >> {C}`: Multi-hop ancestor chain.

## 4. Trace-Level Aggregators & Pipeline Clauses

- `| count() > N`: Filter traces where the preceding span-set has more than `N` spans.
- `| avg(duration) > 200ms`, `| max(duration) > 1s`, `| min(duration)`, `| sum(duration)`.
- `| by(resource.service.name)`: Group spans by attribute before applying a trace-level aggregator.
- `| select(resource.service.name, span.http.route, status)`: Project specific attributes into search results so `tempo_traceql_search` returns enriched span attributes without fetching full OTLP traces.
- `| coalesce()`: Merge spans sets across pipeline stages.

## 5. Query Hints (`with(...)`)

- Append `with(most_recent=true)` to the end of a TraceQL search query on Tempo 2.5+ and 3.x (or pass `most_recent=True` to `tempo_traceql_search`) to search newest blocks first and return recent traces faster during live incidents.
