---
name: managing-alert-silences
description: Plans, validates, previews, creates, updates, and expires Prometheus Alertmanager silences for maintenance windows and incident noise suppression. Use when asked to silence or mute an alert, schedule a timezone-aware maintenance window, check silence blast radius, extend or update an active silence, validate silence matchers, or expire a silence early. Do not use for read-only incident triage (use triaging-alertmanager-alerts), static alertmanager.yml mute_time_intervals (use validating-alertmanager-routing), or broad governance audits (use auditing-alertmanager-governance).
license: Apache-2.0
metadata:
  author: talkops
  version: "0.2.0"
  domain: observability
  component: alertmanager
---

# Managing Alert Silences Safely

## Overview

Enforces a mandatory **Validate $\to$ Preview $\to$ Confirm $\to$ Mutate $\to$ Verify** lifecycle for every Alertmanager silence operation so maintenance windows never accidentally mute an entire production environment, mask `Watchdog` heartbeats, exceed the 24-hour (`1440m`) lifetime cap, or lack ticket attribution.

## MCP Execution Primitives & Bundled Scripts

- **Bundled Scripts (Always Run Offline Deterministic Helpers First)**:
  - [scripts/plan_maintenance_window.py](scripts/plan_maintenance_window.py) — converts IANA timezone schedules (`--start`, `--timezone`, `--duration-minutes`, `--buffer-before-minutes`, `--buffer-after-minutes`) into RFC3339 UTC `starts_at` / `ends_at` timestamps.
  - [scripts/validate_silence_request.py](scripts/validate_silence_request.py) — deterministic preflight validator checking matcher syntax, Go RE2 regex compatibility, and policy rules `SP001`–`SP009`.
- **Resources (Read via MCP `read_resource`)**:
  - `am://backends` — verify available Alertmanager backends.
  - `am://backends/{backend_id}/silences/active` — snapshot of active silences on a backend.
  - `am://backends/{backend_id}/silences/{silence_id}` — full matcher, author, ticket, and `startsAt`/`endsAt` details of a specific silence.
  - `am://audit-log` — audit trail of silence creations, updates, expirations, and policy denials.
- **Tools (`silences` & `triage` toolsets)**:
  - `am_list_silences` — list and filter `active`, `pending`, or `expired` silences by `matchers`, `created_by`, or `comment_search`.
  - `am_preview_silence` — **mandatory live dry-run** returning policy validation (`SP001`–`SP010`), `affected_alert_count`, `affected_critical_count`, `affected_receivers`, and `overlapping_silences`.
  - `am_create_silence` — create a validated silence (requires `MCP_ALLOW_WRITE=true`, `created_by`, and `comment`).
  - `am_silence_alert` — silence a specific firing alert by live `fingerprint` or `labels` using `scope="instance"` or `scope="service"`.
  - `am_update_silence` — atomically extend or update an active silence in place (`POST /api/v2/silences` with `id`), enforcing cumulative lifetime `(new_ends_at - original_starts_at) <= AM_MAX_SILENCE_MINUTES` (`1440m`).
  - `am_expire_silence` — expire an active silence early after previewing how many suppressed alerts will resume paging (`confirm=True`).

## Mandatory Workflows

### 1. Validate & Preview Before Any Silence Creation
Always read [references/silence-policy.md](references/silence-policy.md) and [references/matcher-cookbook.md](references/matcher-cookbook.md) before constructing or reviewing matchers:
1. **Check Existing Silences & Live Fingerprints**:
   - Call `am_list_silences(backend_id=..., state="active")` (or read `am://backends/{backend_id}/silences/active`) to spot duplicates or find active silence UUIDs.
   - When targeting a specific firing alert, call `am_list_alerts` first to obtain its exact live `fingerprint`—never guess or invent fingerprints or silence IDs.
2. **Compute Timezone-Aware Windows (When Scheduled)**:
   - Run `python3 <skill-dir>/scripts/plan_maintenance_window.py --start "<iso>" --timezone "<IANA_TZ>" --duration-minutes <min> --buffer-before-minutes <pre> --buffer-after-minutes <post>`.
3. **Run Offline Policy Validation (`SP001`–`SP009`)**:
   - Run `python3 <skill-dir>/scripts/validate_silence_request.py --matchers '<expr>' --duration-minutes <min> --created-by '<author>' --comment '<ticket>'` (or `--starts-at` / `--ends-at`).
   - Remember Go RE2 rules (`SP001`): lookarounds like `(?!canary)` are invalid in Go RE2—rewrite as a positive + negative matcher pair (`pod=~"svc-.*", pod!~"svc-canary-.*"`).
   - Reject negative-only matchers (`SP002`), wildcard `.*`/`.+` (`SP003`), sole broad `env`/`severity`/`cluster` matchers (`SP004`), `Watchdog` (`SP005`), naive timestamps without timezone offsets or `ends_at <= starts_at` (`SP006` — always show a concrete corrected RFC3339 UTC `Z` `starts_at` and `ends_at` example with `ends_at > starts_at`), durations $> 1440\text{m}$ (`SP007`), placeholder authors like `anonymous`/`mcp`/`unknown` (`SP008`), and missing comments/tickets (`SP009`).
4. **Run Live Blast-Radius Preview (`am_preview_silence` — Mandatory)**:
   - Always call `am_preview_silence` before any `am_create_silence` or `am_silence_alert` call.
   - **Blast-Radius Gate (`SP010`)**: If `affected_alert_count >= 50` (`requires_confirmation == True`) OR if the user only asked to preview/check impact before committing, **STOP** after `am_preview_silence`, report the exact `affected_alert_count`, `affected_critical_count`, `affected_receivers`, and sample alerts, and wait for explicit sign-off!
   - **Read-Only Server Mode (`MCP_ALLOW_WRITE=false`)**: If mutating tools (`am_create_silence`, `am_silence_alert`, `am_update_silence`, `am_expire_silence`) are not registered because the MCP server is in read-only mode, run `scripts/validate_silence_request.py` and `am_preview_silence`, state clearly that live mutations are disabled on this server without fabricating a silence ID, and provide the exact validated Alertmanager v2 JSON / `amtool silence add` command.
5. **Apply & Verify (When Explicitly Requested and Write-Enabled)**:
   - Call `am_create_silence(..., confirm=True)` or `am_silence_alert(..., confirm=True)` and verify the created silence via `am://backends/{backend_id}/silences/{silence_id}`.

### 2. Extending / Updating an Active Silence (`SP007` Lifetime Guard)
1. Locate the target silence via `am_list_silences` and read `am://backends/{backend_id}/silences/{silence_id}` to inspect `startsAt` and `endsAt`.
2. Verify `(new_ends_at - startsAt) <= 1440` minutes (`24h`). Operators **cannot** chain `am_update_silence` extensions past the 24-hour total lifetime cap (`SP007`)—refuse bypass attempts, calculate the maximum remaining compliant extension, and recommend fixing the underlying issue or tuning the rule/route for multi-day noise.
3. For compliant extensions, call `am_update_silence(..., confirm=True)`.

### 3. Expiring a Silence Early
1. Inspect silenced alerts (`am_list_alerts(state="silenced")` or `am://backends/{backend_id}/silences/{silence_id}`) to warn how many alerts will immediately resume paging, then call `am_expire_silence(..., expired_by=..., reason=..., confirm=True)` and optionally verify in `am://audit-log`.
