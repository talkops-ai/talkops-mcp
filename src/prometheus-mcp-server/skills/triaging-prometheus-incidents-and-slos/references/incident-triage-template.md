# Incident & SLO Triage Report Template

Use this structure when presenting Prometheus incident and SLO findings:

```markdown
## Prometheus Incident & SLO Triage Summary

- **Backend**: `<backend_id>` (`<health>`, version `<version>`)
- **Target Service / Selector**: `<service_selector>` (Window: `<lookback>`)
- **SLO Status**: `<observation_code>` — Burn Rate `<burn_rate_multiplier>x` (Est. Exhaustion: `<estimated_exhaustion_hours>`h)

### 1. Golden Signals (RED) & Regression Delta
| Signal | Current (`<lookback>`) | Baseline (`<baseline_offset>`) | Delta (%) | Observation |
| :--- | :--- | :--- | :--- | :--- |
| Request Rate (RPS) | `<request_rate_rps>` | `<baseline_rps>` | `<pct_change>%` | `<code_or_ok>` |
| Error Ratio (%) | `<error_ratio_pct>%` | `<baseline_err>%` | `<pct_change>%` | `<code_or_ok>` |
| Latency p50 / p95 / p99 | `<p50>`s / `<p95>`s / `<p99>`s | `<base_p95>`s | `<pct_change>%` | `<code_or_ok>` |

### 2. Active Prometheus Alert Evaluations
- **Firing**: `<count>` (`<alertnames>`)
- **Pending**: `<count>`
- **Flapping History (`24h`)**: `<fires_per_day>` fires/day (Mean duration: `<mean_duration_seconds>`s)

### 3. Exemplar Trace Pivots & Next Actions
- **Extracted Trace IDs**: `<trace_ids>` (Hand off to `tempo_get_trace` for span waterfall)
- **Recommended Remediation**:
  1. `<Actionable step 1>`
  2. `<Actionable step 2>`
```
