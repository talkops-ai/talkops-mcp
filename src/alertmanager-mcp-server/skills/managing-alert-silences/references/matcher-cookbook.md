# Alertmanager Matcher Cookbook for Safe Silences

## Recommended Matcher Patterns

### 1. Single Host / Pod Maintenance (`scope="instance"`)
Mutes all alerts originating from a specific instance undergoing reboot or upgrade:
```json
[
  {"name": "instance", "value": "db-replica-03.prod:9100", "isRegex": false, "isEqual": true},
  {"name": "env", "value": "prod", "isRegex": false, "isEqual": true}
]
```

### 2. Service Deployment Window (`scope="service"`)
Mutes a known noisy alert for a single service in a specific environment:
```json
[
  {"name": "alertname", "value": "HighP99Latency", "isRegex": false, "isEqual": true},
  {"name": "service", "value": "checkout-api", "isRegex": false, "isEqual": true},
  {"name": "env", "value": "prod", "isRegex": false, "isEqual": true}
]
```

### 3. Bounded Multi-Instance Rollout (RE2 Alternation)
Alertmanager implicitly anchors regexes (`^(?:pattern)$`). Use explicit alternation:
```json
[
  {"name": "service", "value": "payment-worker", "isRegex": false, "isEqual": true},
  {"name": "instance", "value": "payment-worker-0[1-3]:8080", "isRegex": true, "isEqual": true}
]
```

## Anti-Patterns (Blocked by Policy)

- **Blocked by `SP002`**: Only negative matchers (`[{"name": "env", "value": "dev", "isRegex": false, "isEqual": false}]`) — matches alerts where `env` is absent!
- **Blocked by `SP003`**: Wildcard regex (`[{"name": "alertname", "value": ".*", "isRegex": true, "isEqual": true}]`) — mutes every alert in Alertmanager!
- **Blocked by `SP004`**: Sole broad label (`[{"name": "env", "value": "prod", "isRegex": false, "isEqual": true}]`) — mutes all of production!
- **Blocked by `SP005`**: Heartbeat alert (`[{"name": "alertname", "value": "Watchdog", "isRegex": false, "isEqual": true}]`).
