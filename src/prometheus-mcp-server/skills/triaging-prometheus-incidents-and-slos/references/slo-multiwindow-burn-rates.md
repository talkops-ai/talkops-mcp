# Google SRE Multi-Window Multi-Burn-Rate Reference

## Burn Rate Formula

For an SLO target $S$ (e.g., $0.999$) over a compliance window $W$ (typically 30 days = 720 hours), the error budget is $E = 1 - S = 0.001$.
A **burn rate** of $B$ means the service is consuming its error budget $B$ times faster than the sustainable rate:

$$\text{Burn Rate } B = \frac{\text{Error Ratio}_{\text{window}}}{1 - S}$$

$$\text{Hours to Exhaustion} = \frac{W_{\text{hours}}}{B}$$

## Standard Multi-Window Threshold Matrix (30-Day Window)

| Severity Tier | Observation Code | Long Window | Short Window | Burn Rate ($B$) | Budget Consumed | Action |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Critical (Page)** | `PAGE_CRITICAL_FAST_BURN` | `1h` | `5m` | `14.4x` | 2% in 1h | Immediate page; rollback or mitigate now. |
| **High (Page)** | `PAGE_HIGH_BURN` | `6h` | `30m` | `6.0x` | 5% in 6h | Page on-call; investigate sustained degradation. |
| **Warning (Ticket)** | `TICKET_SLOW_BURN` | `24h` | `2h` | `3.0x` | 10% in 24h | Create daytime ticket; inspect error trends. |
| **Low (Ticket)** | `TICKET_SLOW_BURN` | `72h` | `6h` | `1.0x` | 10% in 3d | Track chronic low-grade errors. |

## Why Both Long and Short Windows Are Required
- The **long window** (`1h`, `6h`, `24h`) prevents alerting on brief 30-second micro-bursts that do not threaten the 30-day error budget.
- The **short window** (`5m`, `30m`, `2h`, always $\frac{1}{12}$ of the long window) ensures the alert **resolves quickly** once recovery completes instead of staying firing for hours while the long window ages out.
