# Incident Summary Template

## Table of Contents

1. [Structured Triage Report Format](#1-structured-triage-report-format)

## 1. Structured Triage Report Format

```markdown
## Traefik Routing Incident Triage: `<namespace>/<name>` (`<kind>`)

- **Verdict**: `HEALTHY` | `UNHEALTHY`
- **Diagnosis Codes**: `<CODE_1>`, `<CODE_2>`
- **Runtime Router**: `<router_name>` (`status: <enabled|disabled>`)
- **Root Cause Evidence**:
  - <Concrete evidence from traefik_diagnose_route, traefik_trace_request, or traefik_analyze_logs>
- **Metrics Impact**:
  - 5xx Error Rate: `<baseline>% -> <comparison>%`
  - P95 Latency: `<baseline>ms -> <comparison>ms`
- **Proposed Remediation (`dry_run=True` Preview)**:
  - Tool: `<traefik_*>`
  - Diff Summary: `<diff>`
```
