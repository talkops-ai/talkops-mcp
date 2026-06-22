# Loki MCP Server — Natural Language Prompt Reference

**For every tool, resource, and prompt documented in [WORKFLOW_JOURNEYS.md](WORKFLOW_JOURNEYS.md), this guide provides ready-to-use natural language prompts you can give to an AI agent.**

Copy any prompt below exactly or adapt it for your service names, labels, and time ranges.

> **Design**: All 8 tools are **read-only**. No tool modifies your Loki backend or cluster.

---

## Table of Contents

1. [Discovery](#discovery)
2. [Structure](#structure)
3. [Safety](#safety)
4. [Execution](#execution)
5. [Guided Workflow Prompts](#guided-workflow-prompts)
6. [Resource Reads](#resource-reads)

---

## Discovery

> **Tool**: `get_cluster_labels`

```
What labels are available in my Loki cluster?
```
```
List all label names in Loki.
```
```
Show me the label taxonomy for the last 24 hours.
```
```
What dimensions can I query logs by?
```

> **Tool**: `get_label_values`

```
What services are sending logs to Loki?
```
```
Show me all values for the "app" label.
```
```
What namespaces exist in Loki?
```
```
List all environments in the "env" label.
```
```
Show me app values scoped to the production namespace.
```

> **Tool**: `get_active_series`

```
Validate that the selector '{app="checkout"}' matches active log streams.
```
```
How many active series exist for '{namespace="production"}'?
```
```
Check the cardinality of labels for '{app="api-gateway"}'.
```
```
Are there any high-cardinality labels in '{namespace="production"}'?
```

---

## Structure

> **Tool**: `get_log_patterns`

```
What are the structural log patterns for the "checkout" service?
```
```
Show me recurring log shapes for '{app="api-gateway"}' in the last 3 hours.
```
```
What pattern parsers would work for "payment-service" logs?
```

> **Tool**: `get_detected_fields`

```
What fields can I query in "checkout-service" logs?
```
```
Show me the JSON/logfmt fields available for '{app="api-gateway"}'.
```
```
What's the log structure for "order-service"? Are the logs JSON or logfmt?
```
```
Discover fields and their types for '{app="payment-service"}'.
```

---

## Safety

> **Tool**: `get_query_stats`

```
How expensive would it be to query '{app="checkout"}' for the last hour?
```
```
Preflight check: how many streams, chunks, and bytes would '{namespace="production"}' touch?
```
```
Is it safe to query all logs from the production namespace for the last 24 hours?
```

---

## Execution

> **Tool**: `execute_logql_instant`

```
What is the current error rate for "checkout-service"?
```
```
How many log lines per second is "api-gateway" producing right now?
```
```
What's the current request rate across all services in production?
```
```
Show me the instant count of error logs for "payment-service".
```

> **Tool**: `execute_logql_query`

```
Show me error logs from "checkout-service" in the last hour.
```
```
Find all logs containing "timeout" from the "api-gateway" in the last 30 minutes.
```
```
Search for HTTP 500 errors in "payment-service" logs — parse as JSON and filter by status_code=500.
```
```
Show me the error rate over time for "checkout-service" in the last 6 hours with 5-minute steps.
```
```
Find all logs from the production namespace matching "panic" or "fatal" in the last 15 minutes.
```
```
Run a rate query: rate of error logs for "order-service" over the last 3 hours.
```
```
Query the average latency from "api-gateway" logs — parse JSON, unwrap latency_ms, over the last 2 hours.
```

---

## Guided Workflow Prompts

These invoke MCP prompts that return structured multi-step workflows:

> **Prompt**: `investigate_errors`

```
Investigate errors for the "checkout-service" over the last hour.
```
```
Help me investigate a burst of errors from "api-gateway".
```
```
Triage error logs for "payment-service" in the last 30 minutes.
```

> **Prompt**: `check_health`

```
Run a health check for "payment-service".
```
```
Is "checkout-service" producing logs? Check the health.
```
```
Verify the Loki connection and check if "api-gateway" is healthy.
```

> **Prompt**: `analyze_log_structure`

```
Analyze the log structure for "api-gateway".
```
```
What format are "checkout-service" logs? JSON, logfmt, or plain text?
```
```
Discover the fields and patterns in "order-service" logs.
```

> **Prompt**: `build_logql_query`

```
Build a LogQL query to find slow HTTP requests with status 500.
```
```
Help me construct a LogQL query for error logs in checkout with latency above 500ms.
```
```
Create a LogQL query to count timeouts per service in the last hour.
```

> **Prompt**: `explore_schema`

```
Explore the full label schema of this Loki cluster.
```
```
Give me a complete inventory of services, namespaces, and label cardinality.
```
```
What does the label landscape look like? Any cardinality issues?
```

---

## Resource Reads

> **Resource**: `loki://system/health`

```
Is Loki reachable and healthy?
```
```
Check the Loki system health.
```

> **Resource**: `loki://schema/labels`

```
Show me all label names in the Loki schema.
```

> **Resource**: `loki://config/guardrails`

```
What are the current query guardrails and safety limits?
```
```
What's the maximum time window I can query?
```

> **Resource**: `loki://config/backends`

```
Show me the configured Loki backend connection details.
```
```
What URL and auth is the MCP server using for Loki?
```

> **Resource**: `loki://reference/logql`

```
Show me the LogQL syntax reference.
```
```
How do I write a LogQL query?
```

> **Resource**: `loki://reference/best-practices`

```
Show me Loki best practices.
```
```
What are the cardinality rules and labeling guidelines?
```

> **Resource**: `loki://reference/query-templates`

```
Show me common LogQL query templates.
```
```
What are some useful LogQL queries to start with?
```

> **Resource**: `loki://reference/label-governance`

```
Show me the label governance guide.
```
```
What are the label naming conventions and cardinality rules?
```

---

*Document Version: 1.0 | Companion to [WORKFLOW_JOURNEYS.md](WORKFLOW_JOURNEYS.md)*
