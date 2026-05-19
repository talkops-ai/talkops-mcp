"""Silence management guided workflow prompts."""
from mcp.types import PromptMessage, TextContent
from alertmanager_mcp_server.prompts import BasePrompt


class SilencePrompts(BasePrompt):
    def register(self, mcp_instance) -> None:
        @mcp_instance.prompt(name="am-maintenance-silence-guided",
                             description="Guided workflow for creating a maintenance silence")
        def am_maintenance_silence(backend_id: str, service: str = "checkout", env: str = "prod", duration: int = 60) -> list[PromptMessage]:
            return [PromptMessage(role="user", content=TextContent(type="text", text=f"""# 🔇 Maintenance Silence Guide

## Context
- **Backend**: {backend_id}
- **Service**: {service}
- **Environment**: {env}
- **Duration**: {duration} minutes

## Phase 1: Preview Impact (MANDATORY)
```
Tool: am_helper_mgmt(action="preview_silence", backend_id="{backend_id}", matchers=[{{"name": "service", "value": "{service}", "isRegex": false, "isEqual": true}}, {{"name": "env", "value": "{env}", "isRegex": false, "isEqual": true}}])
```
⚠️ If warning_flag is true, narrow your matchers before proceeding.

## Phase 2: Create Silence
```
Tool: am_silence_mgmt(action="create", backend_id="{backend_id}", matchers=[{{"name": "service", "value": "{service}", "isRegex": false, "isEqual": true}}, {{"name": "env", "value": "{env}", "isRegex": false, "isEqual": true}}], duration_minutes={duration}, comment="Planned maintenance for {service}")
```

## Phase 3: Confirm
```
Tool: am_silence_mgmt(action="list", backend_id="{backend_id}", state="active")
```

## Phase 4: Extend if Needed
```
Tool: am_silence_mgmt(action="extend", backend_id="{backend_id}", silence_id="<from step 2>", add_minutes=30)
```

## Phase 5: Clean Up
```
Tool: am_silence_mgmt(action="expire", backend_id="{backend_id}", silence_id="<from step 2>")
```
"""))]
