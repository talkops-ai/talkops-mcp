# ArgoFlow MCP Server Instructions

## Overview

The **ArgoFlow MCP Server** provides comprehensive progressive delivery and traffic management capabilities for Kubernetes using Argo Rollouts and Traefik. This server enables safe, controlled application deployments with automated canary releases, traffic shifting, and intelligent rollback capabilities.

## Core Capabilities

### 1. Argo Rollouts Management
- **Progressive Delivery Strategies**
  - Canary deployments with customizable traffic steps
  - Blue-Green deployments for instant switching
  - Rolling updates with configurable parameters
  
- **Deployment Control**
  - Create and configure rollouts
  - Monitor rollout status and health
  - Promote rollouts incrementally or fully
  - Abort and rollback to stable versions
  - Pause and resume deployment progression

- **Advanced Features**
  - Automated analysis with Prometheus metrics
  - Historical audit trails
  - Container image updates
  - Emergency override capabilities

### 2. Traefik Traffic Management
- **Weighted Traffic Routing**
  - Create weighted routes for canary deployments
  - Progressive traffic shifting (5% → 10% → 25% → 50% → 100%)
  - Real-time traffic distribution monitoring
  
- **Protection Middleware**
  - Rate limiting to protect canary services
  - Circuit breakers for automatic rollback
  - Traffic mirroring for shadow testing
  - Anomaly detection integration

## Available Tools (20 tools)

### Argo Rollouts Tools (12)

#### Rollout Management
1. `argo_create_rollout` - Create new rollout with strategy
2. `argo_get_rollout_status` - Get detailed rollout status
3. `argo_list_rollouts` - List all rollouts in namespace
4. `argo_delete_rollout` - Delete rollout resource
5. `argo_update_rollout_image` - Update container image
6. `argo_get_rollout_history` - Get historical audit trail

#### Rollout Operations
7. `argo_promote_rollout` - Promote to next step or fully
8. `argo_abort_rollout` - Abort and rollback to stable
9. `argo_pause_rollout` - Pause rollout progression
10. `argo_resume_rollout` - Resume paused rollout
11. `argo_set_analysis_template` - Configure automated analysis
12. `argo_skip_analysis_promote` - Emergency override

### Traefik Tools (8)

#### Traffic Routing
1. `traefik_create_weighted_route` - Create canary route
2. `traefik_update_route_weights` - Adjust traffic distribution
3. `traefik_delete_route` - Cleanup after rollout
4. `traefik_get_traffic_distribution` - Monitor current weights

#### Middleware Management
5. `traefik_add_rate_limiting` - Protect from overload
6. `traefik_add_circuit_breaker` - Auto-rollback on errors
7. `traefik_enable_traffic_mirroring` - Shadow testing
8. `traefik_detect_anomalies` - Anomaly detection

## Common Workflows

### Progressive Canary Deployment

```
1. Create Argo Rollout (canary strategy)
   → argo_create_rollout(name="api", image="api:v2.0", strategy="canary")

2. Setup Traefik Route (100% stable, 0% canary)
   → traefik_create_weighted_route(route_name="api", hostname="api.example.com")

3. Add Protection Middleware
   → traefik_add_circuit_breaker(middleware_name="api-breaker", threshold=0.30)
   → traefik_add_rate_limiting(middleware_name="api-limit", average=100)

4. Progressive Traffic Shift
   → argo_promote_rollout(name="api")  # Move to next step
   → traefik_update_route_weights(route_name="api", stable_weight=90, canary_weight=10)  # 10%
   
   → argo_promote_rollout(name="api")
   → traefik_update_route_weights(route_name="api", stable_weight=75, canary_weight=25)  # 25%
   
   → argo_promote_rollout(name="api")
   → traefik_update_route_weights(route_name="api", stable_weight=50, canary_weight=50)  # 50%

5. Complete Rollout
   → traefik_update_route_weights(route_name="api", stable_weight=0, canary_weight=100)  # 100%
   → traefik_delete_route(route_name="api")
```

### Emergency Rollback

```
1. Detect Issues
   → argo_get_rollout_status(name="api")
   → traefik_get_traffic_distribution(route_name="api")

2. Abort Rollout
   → argo_abort_rollout(name="api")  # Rollback Argo
   → traefik_update_route_weights(route_name="api", stable_weight=100, canary_weight=0)  # Rollback traffic
```

### Shadow Testing

```
1. Enable Traffic Mirroring
   → traefik_enable_traffic_mirroring(
       route_name="api",
       main_service="api-production",
       mirror_service="api-staging",
       mirror_percent=20
     )

2. Monitor Staging Performance
   → Use metrics to validate canary before real traffic shift
```

## Best Practices

### Progressive Rollout
- Start with low traffic percentages (5-10%)
- Wait for metrics validation between steps
- Use circuit breakers for automatic protection
- Monitor error rates and latency

### Traffic Management
- Always create weighted routes before promoting rollouts
- Sync Argo promotions with Traefik weight updates
- Use rate limiting to protect canary services
- Enable mirroring for pre-deployment validation

### Safety and Monitoring
- Configure circuit breakers with appropriate thresholds
- Set up automated analysis with Prometheus
- Monitor rollout history for audit trails
- Use pause/resume for manual validation gates

## Configuration

The server is configured via environment variables:

### Server Settings
- `MCP_PORT` - Server port (default: 8765)
- `MCP_ALLOW_WRITE` - Enable write operations (default: false)
- `MCP_DEBUG` - Enable debug mode (default: false)

### Argo Rollouts
- `ARGO_DEFAULT_STRATEGY` - Default strategy (canary/bluegreen/rolling)
- `ARGO_REQUIRE_MANUAL_PROMOTION` - Require manual promotion (default: true)
- `ARGO_AUTO_ROLLBACK` - Auto-rollback on failure (default: true)

### Traefik
- `TRAEFIK_DEFAULT_WEIGHT_STEP` - Default weight increment (default: 10)
- `TRAEFIK_CIRCUIT_BREAKER_THRESHOLD` - Circuit breaker threshold (default: 0.30)

See `.env.example` for complete configuration options.

## Requirements

- Kubernetes cluster with kubectl access
- Argo Rollouts installed (CRDs must be available)
- Traefik installed (CRDs must be available)
- Optional: Prometheus for automated analysis

## Getting Started

1. Ensure Argo Rollouts and Traefik are installed in your cluster
2. Configure environment variables (see `.env.example`)
3. Start the server: `uv run argoflow-mcp-server`
4. Use the tools to manage progressive deployments

## Support

For issues, feature requests, or questions, please refer to the project documentation.

---

**Version**: 0.1.0  
**Status**: Production Ready  
**Total Tools**: 20 (12 Argo + 8 Traefik)
