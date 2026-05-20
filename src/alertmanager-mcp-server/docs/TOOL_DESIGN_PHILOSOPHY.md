# MCP Tool Design Philosophy: Granular Tools vs Action-Enum Pattern

## TL;DR

We chose **one tool per action** (e.g. `am_list_alerts`, `am_create_silence`, `am_expire_silence`) over a single "super tool" with an action enum (e.g. `am_silence_mgmt(action="list"|"create"|"expire")`).

This is not a stylistic preference — it is an **LLM ergonomics decision** backed by industry research and real-world failure data from production MCP deployments.

---

## The Two Patterns

### Pattern A: Action-Enum ("Super Tool")

```python
@mcp.tool()
async def am_silence_mgmt(
    action: Literal["list", "create", "expire", "extend"],
    backend_id: str,
    # list-only params
    state: Optional[str] = None,
    limit: Optional[int] = 50,
    # create-only params
    matchers: Optional[List[Dict]] = None,
    duration_minutes: Optional[int] = None,
    comment: Optional[str] = None,
    created_by: Optional[str] = None,
    # expire-only params
    silence_id: Optional[str] = None,
    # extend-only params
    add_minutes: Optional[int] = None,
) -> Any:
    ...
```

One tool, one schema, four behaviors. The LLM picks the action via an enum.

### Pattern B: Granular ("One Tool Per Action")

```python
@mcp.tool()
async def am_list_silences(backend_id: str, state: Optional[str] = None, limit: int = 50) -> Any: ...

@mcp.tool()
async def am_create_silence(backend_id: str, matchers: List[Dict], duration_minutes: int, ...) -> Any: ...

@mcp.tool()
async def am_expire_silence(backend_id: str, silence_id: str) -> Any: ...

@mcp.tool()
async def am_update_silence(backend_id: str, silence_id: str, add_minutes: int, ...) -> Any: ...
```

Four tools, each with a focused schema and a clear name.

---

## Why We Chose Granular Tools

### 1. LLM Tool Selection Accuracy

When an LLM sees 19 well-named tools, its task is **simple classification**:

> "The user wants to silence an alert" → `am_create_silence` ✅

With an action-enum tool, the LLM must do **two things**:

> "The user wants to silence an alert" → `am_silence_mgmt` → then also set `action="create"` and figure out which of the 12 optional parameters to fill.

Every additional decision point increases the chance of the model picking the wrong path. In production MCP deployments, action-enum tools show **2-3x higher tool-call failure rates** compared to granular tools.

### 2. Parameter Sprawl and Hallucination

The action-enum pattern creates a "God Schema" — a single tool with dozens of parameters where most are irrelevant for any given action:

| Parameter | `list` | `create` | `expire` | `extend` |
|:----------|:------:|:--------:|:--------:|:--------:|
| `state` | ✅ | ❌ | ❌ | ❌ |
| `matchers` | ❌ | ✅ | ❌ | ❌ |
| `silence_id` | ❌ | ❌ | ✅ | ✅ |
| `duration_minutes` | ❌ | ✅ | ❌ | ❌ |
| `add_minutes` | ❌ | ❌ | ❌ | ✅ |
| `comment` | ❌ | ✅ | ❌ | ❌ |

The LLM sees all parameters at once and cannot easily distinguish which are required for which action. This leads to:

- **Hallucinated parameters**: The model passes `duration_minutes` when doing an `expire` action.
- **Missing required parameters**: The model omits `matchers` when doing a `create` because it is marked `Optional` (it has to be, since it's irrelevant for `list`).
- **Cross-contamination**: The model reuses parameter values from a previous `list` call when constructing a `create` call.

With granular tools, each schema contains **only the parameters that matter**. `am_expire_silence` has exactly 2 parameters: `backend_id` and `silence_id`. There is nothing to hallucinate.

### 3. ToolAnnotations Cannot Work on Multi-Action Tools

The MCP spec provides `ToolAnnotations` to signal tool behavior to the orchestrator:

```python
ToolAnnotations(
    readOnlyHint=True,     # Does this tool only read data?
    destructiveHint=False,  # Could this tool destroy data?
    idempotentHint=True,    # Is this tool safe to retry?
)
```

With a multi-action tool, these annotations **cannot be set correctly**:

- `am_silence_mgmt(action="list")` is `readOnlyHint=True`
- `am_silence_mgmt(action="create")` is `readOnlyHint=False`
- `am_silence_mgmt(action="expire")` is `destructiveHint=True`

You cannot annotate a single tool as both read-only and destructive. This breaks the orchestrator's ability to implement human-in-the-loop approval for dangerous actions.

With granular tools:

```python
am_list_silences   → readOnlyHint=True,  destructiveHint=False  ✅
am_create_silence  → readOnlyHint=False, destructiveHint=False  ✅
am_expire_silence  → readOnlyHint=False, destructiveHint=True   ✅
```

### 4. Docstrings Become Precise and Actionable

Each tool gets its own docstring optimized for LLM reasoning:

```python
async def am_expire_silence(...):
    """Expire a silence to reactivate alert notifications.

    Use this when a maintenance window ends early or when alerts need to
    be re-enabled. MUTATES STATE.

    Returns:
    - {"success": true, "message": str}

    Common errors:
    - Silence not found: Verify the silence_id via am_list_silences.
    """
```

With an action-enum tool, the docstring must explain **all four actions** in one block, making it longer, harder to parse, and more likely to confuse the model about which section applies.

### 5. The Unix Philosophy

> *"Make each program do one thing well."*

This principle translates directly to MCP tool design. A tool named `am_create_silence` **communicates its purpose through its name alone**. A tool named `am_silence_mgmt` communicates nothing — the LLM must read the full description and parameter schema to understand what it does.

---

## When Action-Enum Might Be Acceptable

The enum pattern is not always wrong. It can work for:

- **Internal code organization**: Using a Command Pattern internally while exposing granular tools externally.
- **Truly polymorphic operations**: Where the same parameters apply to all actions (rare).
- **Prototype/MVP phase**: When iterating quickly and tool count doesn't matter yet.

We used the action-enum pattern in our v2 implementation during rapid prototyping. The v3 refactor moved to granular tools before the public release.

---

## Our Tool Inventory

After the v4 refactor (which moved read-only data snapshots into resources), the Alertmanager MCP server exposes **14 granular tools**:

| Domain | Tools | ReadOnly |
|:-------|:------|:--------:|
| **Alerts** | `am_list_alerts`, `am_list_alert_groups`, `am_push_test_alert` | Mixed |
| **Silences** | `am_list_silences`, `am_create_silence`, `am_update_silence`, `am_expire_silence` | Mixed |
| **Helpers** | `am_preview_silence`, `am_silence_alert` | Mixed |
| **Routing** | `am_explain_routing`, `am_audit_default_route` | ✅ |
| **Governance** | `am_list_recent_changes`, `am_validate_silence_policy` | ✅ |
| **Triage** | `am_summarize_oncall` | ✅ |

*Note: Discovery tools, config export, routing tree, and receiver listing were moved to Resource URIs (e.g. `am://system/backends`, `am://system/config`) in v4 to further distinguish actionable tools from data snapshots.*

Each tool has:
- A `verb_noun` name for instant LLM classification
- Precise `ToolAnnotations` for orchestrator safety
- A focused parameter schema with only relevant fields
- A structured docstring with "When to use", "Returns", and "Common errors"

---

## References

- [Anthropic MCP Best Practices (2025)](https://modelcontextprotocol.io/docs/concepts/tools)
- [MCP Spec: ToolAnnotations](https://spec.modelcontextprotocol.io/specification/2025-06-18/server/tools/#annotations)
- Internal production data from MCP deployments showing 2-3x failure rate reduction with granular tools
- Unix Philosophy: *The Art of Unix Programming* by Eric S. Raymond
