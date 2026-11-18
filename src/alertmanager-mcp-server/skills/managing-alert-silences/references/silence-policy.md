# Alertmanager Silence Safety Policy (`SP001`–`SP010`)

Every silence candidate evaluated by `am_preview_silence`, `am_create_silence`, `am_silence_alert`, `am_update_silence`, or `scripts/validate_silence_request.py` is checked against these 10 deterministic rules:

| Rule ID | Severity | Rule Name | Enforcement Criteria | Remediation |
| :--- | :--- | :--- | :--- | :--- |
| **`SP001`** | `error` | Valid Non-Empty Matchers | At least 1 matcher with valid label syntax (`^[a-zA-Z_][a-zA-Z0-9_]*$`) and RE2-compatible regex. | Provide valid Alertmanager matchers; avoid PCRE lookarounds (`(?=...)`) or backreferences (`\1`). |
| **`SP002`** | `error` | Positive Non-Empty Matcher Required | At least 1 matcher must be positive (`=` or `=~`) and must NOT match the empty string `""`. | Add a positive matcher like `alertname="HighLatency"` or `service="checkout"`. |
| **`SP003`** | `error` | No Wildcard Regex Matchers | Positive regex matchers cannot be unanchored match-alls (`.*`, `.+`, `^.*$`, `^.+$`). | Replace wildcard regex with explicit values or bounded alternation (`service=~"api|worker"`). |
| **`SP004`** | `error` | Forbidden Sole Broad Labels | Positive matchers cannot consist solely of `severity`, `env`, `environment`, `cluster`, `region`, or `datacenter`. | Add a narrowing selector (`alertname`, `service`, `instance`, `job`, or `namespace`). |
| **`SP005`** | `error` | Watchdog Heartbeat Protection | Cannot target `Watchdog`, `DeadMansSwitch`, or `AlertmanagerWatchdog`. | Never silence the pipeline heartbeat alert. |
| **`SP006`** | `error` | Explicit RFC3339 Timezone & Window | `starts_at` and `ends_at` must include explicit timezone offsets (`Z` or `±HH:MM`), `ends_at > starts_at`, and `ends_at > now`. | Format timestamps as `YYYY-MM-DDTHH:MM:SSZ`. |
| **`SP007`** | `error` | Maximum Silence Duration Cap | Total window `(ends_at - starts_at)` must be $\le$ `AM_MAX_SILENCE_MINUTES` (default `1440` minutes / 24h), including across `am_update_silence`. | Shorten the silence window; use routing `mute_time_intervals` for recurring schedules. |
| **`SP008`** | `error` | Explicit Author Attribution | `created_by` / `updated_by` must be non-empty and not a placeholder (`mcp`, `anonymous`, `unknown`). | Pass the operator handle or email (e.g. `sre-oncall@example.com`). |
| **`SP009`** | `error` / `warning` | Actionable Comment & Ticket Reference | `comment` must be $\ge 3$ chars, match `AM_SILENCE_COMMENT_PATTERN` if configured (`error`), and ideally include a ticket/change ID (`JIRA-123`, `INC001`, `CHG-42`, `#123`) (`warning`). | Include the change or incident reference in `comment`. |
| **`SP010`** | `warning` (gate) | Blast-Radius Confirmation Gate | Triggered when `affected_alert_count >= AM_SILENCE_CONFIRM_THRESHOLD` (default `50`) or when critical alerts are matched without `alertname`/`instance`/`pod` scoping. | Require explicit user confirmation (`confirm=True` or MCP elicitation). |
