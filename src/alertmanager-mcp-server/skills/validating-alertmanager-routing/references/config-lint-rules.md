# Alertmanager Configuration Lint Rules (`LINT001`–`LINT008`)

`scripts/lint_alertmanager_config.py` enforces these 8 static analysis checks on Alertmanager configurations:

| Rule ID | Severity | Check Description | Remediation |
| :--- | :--- | :--- | :--- |
| **`LINT001`** | `error` | Missing `route` block or missing root `route.receiver`. | Define a root `route` with an explicit default `receiver`. |
| **`LINT002`** | `error` | Route references a `receiver` name that does not exist in `receivers`. | Add the receiver to top-level `receivers` or fix the typo. |
| **`LINT003`** | `warning` | Receiver defined in `receivers` is never referenced by any route node. | Remove dead receivers or wire them into `route.routes`. |
| **`LINT004`** | `error` | Route references a `mute_time_intervals` or `active_time_intervals` name not defined in `time_intervals` / `mute_time_intervals`. | Define the named interval in top-level `time_intervals`. |
| **`LINT005`** | `warning` | Route or `inhibit_rules` uses deprecated `match` or `match_re` fields instead of `matchers` (`source_matchers` / `target_matchers`). | Migrate `match`/`match_re` to `matchers: ['key="val"', 're=~"pat"']`. |
| **`LINT006`** | `warning` | Unconditional child route (no matchers) with `continue: false` shadows subsequent sibling routes. | Add matchers to the catch-all child route, move it last, or set `continue: true`. |
| **`LINT007`** | `error` | Invalid matcher syntax or PCRE-only regex unsupported by Go RE2. | Fix matcher syntax (`name="value"`) and use RE2-compatible regular expressions. |
| **`LINT008`** | `warning` | Inhibition rule has identical `source_matchers` and `target_matchers` or empty `equal` labels. | Differentiate source/target matchers and specify `equal` scoping labels. |
