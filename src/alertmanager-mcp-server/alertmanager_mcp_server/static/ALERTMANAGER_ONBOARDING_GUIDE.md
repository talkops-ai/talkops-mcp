# Alertmanager Onboarding Guide

## Getting Started

This guide helps you manage alerts and silences through the Alertmanager MCP server.

## Step 1: Discover Backends
```
Tool: am_backend_mgmt(action="list")
```
Find your Alertmanager backend ID.

## Step 2: Check Active Alerts
```
Tool: am_alert_mgmt(action="list", backend_id="<your-id>", label_filters={"env": "prod"})
```

## Step 3: Understand Alert Routing
```
Tool: am_alert_mgmt(action="simulate_routing", backend_id="<your-id>", alert_labels={"alertname": "HighCPU", "service": "api", "env": "prod"})
```

## Step 4: Create a Maintenance Silence

### 4a. Preview first (mandatory):
```
Tool: am_helper_mgmt(action="preview_silence", backend_id="<your-id>", matchers=[{"name": "service", "value": "api", "isRegex": false, "isEqual": true}])
```

### 4b. Create silence:
```
Tool: am_silence_mgmt(action="create", backend_id="<your-id>", matchers=[{"name": "service", "value": "api", "isRegex": false, "isEqual": true}], duration_minutes=60, comment="API maintenance")
```

## Step 5: Test Notification Integrations
```
Tool: am_alert_mgmt(action="push_test", backend_id="<your-id>", alert_labels={"alertname": "MCPTest", "team": "sre"})
```

## Step 6: Clean Up Silences
```
Tool: am_silence_mgmt(action="list", backend_id="<your-id>", state="active")
Tool: am_silence_mgmt(action="expire", backend_id="<your-id>", silence_id="<id>")
```
