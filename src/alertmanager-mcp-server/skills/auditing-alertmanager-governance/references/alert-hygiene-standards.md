# Alert Hygiene & Taxonomy Standards

## Mandatory Labels
| Label (Configurable via Env) | Default Key | Purpose |
| :--- | :--- | :--- |
| `AM_LABEL_SEVERITY` | `severity` | Determines paging vs. ticket routing (`critical`, `warning`, `info`). |
| `AM_LABEL_ENV` | `env` | Separates production from staging/development (`prod`, `staging`, `dev`). |
| `AM_LABEL_SERVICE` | `service` | Identifies the impacted microservice or infrastructure component. |
| `AM_LABEL_TEAM` | `team` | Routes alerts to the owning engineering squad. |

## Mandatory Annotations (`AM_REQUIRED_ANNOTATIONS`)
- **`summary`**: Concise 1-sentence description of what is broken and user impact.
- **`runbook_url`**: Direct HTTPS link to the operational runbook for investigating and mitigating the alert.
