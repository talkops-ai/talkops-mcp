# Incident Root-Cause Brief Template

## Table of Contents
1. [Executive Summary](#1-executive-summary)
2. [Impact and Blast Radius](#2-impact-and-blast-radius)
3. [Dominant & Newly Introduced Error Signatures](#3-dominant--newly-introduced-error-signatures)
4. [Cross-Service Trace Timeline](#4-cross-service-trace-timeline)
5. [Root Cause & Remediation Actions](#5-root-cause--remediation-actions)

---

Use this structured format when presenting incident triage conclusions to the user:

```markdown
## 1. Executive Summary
- **Incident Status**: [Active / Mitigated / Resolved]
- **Primary Root Cause Service**: `<service_name>` (`<namespace>`)
- **Triggering Failure**: <1-2 sentence summary of the exact technical cause>
- **Detection Window**: `<start_iso>` to `<end_iso>`

## 2. Impact and Blast Radius
- **Total Log Volume**: `<total_lines>` lines (`<volume_delta_pct>%` vs baseline)
- **Error Log Volume**: `<error_lines>` lines (`<error_ratio_pct>%` error ratio, `<error_delta_pct>%` vs baseline)
- **Affected Upstream/Downstream Services**: `<list of services>`

## 3. Dominant & Newly Introduced Error Signatures
| Signature / Pattern | Current Count | Baseline Count | Status |
|---------------------|---------------|----------------|--------|
| `<pattern_1>`       | `<count>`     | `0`            | **NEW REGRESSION** |
| `<pattern_2>`       | `<count>`     | `<base_count>` | Elevated |

## 4. Cross-Service Trace Timeline (`trace_id=<trace_id>`)
1. `<timestamp_1>` — `<service_a>` (`INFO`): Incoming request received
2. `<timestamp_2>` — `<service_b>` (`ERROR`): `<exact root-cause error log>`
3. `<timestamp_3>` — `<service_a>` (`ERROR`): Upstream 502/504 cascade

## 5. Root Cause & Remediation Actions
- **Immediate Mitigation**: <rollback / scale / config toggle>
- **Permanent Fix**: <code / query / alert change>
```
