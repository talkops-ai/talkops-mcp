# ArgoFlow MCP Server

**Intelligent Progressive Delivery Orchestration via Model Context Protocol**

ArgoFlow MCP Server provides AI-driven orchestration for Kubernetes deployments using Argo Rollouts and Traefik. It enables automated canary deployments, blue-green releases, cost-aware scaling, and policy-driven governance through a comprehensive MCP interface.

---

## 🌟 Features

### **25 Intelligent Tools**
- **Argo Rollouts Management** (11 tools): Complete lifecycle management for progressive delivery
- **Traefik Traffic Control** (9 tools): Dynamic traffic routing and middleware management
- **Orchestration** (5 tools): ML-based deployment automation and optimization

### **19 Real-Time Resources**
- **Deployment Metrics**: Live rollout status, health monitoring, and anomaly detection
- **Cost Analytics**: Real-time cost tracking and budget optimization
- **Traffic Distribution**: Canary/stable weight monitoring and traffic flow analysis

### **5 Guided Workflows**
- **Canary Deployment**: Metrics-driven progressive promotion (5% → 100%)
- **Blue-Green Deployment**: Instant traffic switching with validation
- **Rolling Update**: Standard pod-by-pod replacement
- **Multi-Cluster Canary**: Sequential regional rollout with health gates
- **Cost-Optimized Deployment**: Budget-constrained deployment with HPA

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    ArgoFlow MCP Server                       │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │   Tools     │  │  Resources   │  │     Prompts      │   │
│  │  (25 total) │  │  (19 total)  │  │    (5 total)     │   │
│  └─────────────┘  └──────────────┘  └──────────────────┘   │
│         │                │                    │              │
│         └────────────────┴────────────────────┘              │
│                          │                                   │
│         ┌────────────────┴────────────────┐                 │
│         │                                  │                 │
│  ┌──────▼────────┐              ┌─────────▼─────────┐       │
│  │   Services    │              │  Orchestration     │       │
│  │               │              │     Service        │       │
│  │ • Argo        │◄─────────────┤                    │       │
│  │ • Traefik     │              │ • ML Promotion     │       │
│  │               │              │ • Cost Tracking    │       │
│  └───────┬───────┘              │ • Policy Engine    │       │
│          │                      └─────────┬──────────┘       │
│          │                                │                  │
└──────────┼────────────────────────────────┼──────────────────┘
           │                                │
           ▼                                ▼
    ┌──────────────┐              ┌─────────────────┐
    │  Kubernetes  │              │   AI/ML Models  │
    │   Cluster    │              │  (Rule-based)   │
    │              │              │                 │
    │ • Argo CRDs  │              │ • Health Score  │
    │ • Traefik    │              │ • Predictions   │
    └──────────────┘              └─────────────────┘
```

---

## 🎯 Quick Start

### Prerequisites

- **Python 3.10+**
- **Kubernetes Cluster** with:
  - Argo Rollouts installed
  - Traefik ingress controller
- **kubectl** configured with cluster access

### Installation

```bash
# Clone repository
git clone <repository-url>
cd argoflow-mcp-server

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e .

# Set environment variables
export KUBECONFIG=~/.kube/config
export ARGO_NAMESPACE=default

# Run server
python -m argoflow_mcp_server
```

### MCP Client Configuration

Add to your MCP client settings (e.g., Claude Desktop):

```json
{
  "mcpServers": {
    "argoflow": {
      "command": "python",
      "args": ["-m", "argoflow_mcp_server"],
      "env": {
        "KUBECONFIG": "/path/to/.kube/config",
        "ARGO_NAMESPACE": "default"
      }
    }
  }
}
```

---

## 📦 Components

### 1. Tools (25 Total)

#### Argo Rollouts Tools (11 tools)

**Rollout Management:**
- `argo_create_rollout` - Create new Argo Rollout
- `argo_delete_rollout` - Delete existing rollout
- `argo_update_rollout_image` - Update container image
- `argo_get_rollout_status` - Get detailed status
- `argo_list_rollouts` - List all rollouts
- `argo_get_rollout_history` - View revision history

**Rollout Operations:**
- `argo_promote_rollout` - Promote to next step
- `argo_abort_rollout` - Abort and rollback
- `argo_pause_rollout` - Pause progression
- `argo_resume_rollout` - Resume paused rollout
- `argo_skip_analysis` - Skip current analysis

#### Traefik Traffic Tools (9 tools)

**Traffic Routing:**
- `traefik_create_weighted_route` - Create canary route
- `traefik_update_route_weights` - Update traffic split
- `traefik_delete_route` - Remove route
- `traefik_get_traffic_distribution` - Get current weights

**Middleware Management:**
- `traefik_create_rate_limit` - Add rate limiting
- `traefik_create_circuit_breaker` - Add circuit breaker
- `traefik_create_mirror` - Configure traffic mirroring
- `traefik_delete_middleware` - Remove middleware
- `traefik_list_middleware` - List all middleware

#### Orchestration Tools (5 tools)

**Tool 20: Intelligent Promotion**
```bash
orch_deploy_intelligent_promotion \
  --app-name api-service \
  --image api:v2.0 \
  --strategy canary \
  --ml-model gradient_boosting
```

ML-based canary deployment with auto-promotion based on health metrics.

**Tool 21: Cost-Aware Deployment**
```bash
orch_configure_cost_aware_deployment \
  --app-name api-service \
  --max-daily-cost 200.0 \
  --mode optimize
```

Budget tracking with cost optimization recommendations.

**Tool 22: Multi-Cluster Deployment**
```bash
orch_configure_multi_cluster \
  --app-name api-service \
  --clusters '{"us-east": {"region": "us-east-1", "weight": 60}}' \
  --strategy active-active
```

Multi-region orchestration (MVP: Placeholder).

**Tool 23: Policy Validation**
```bash
orch_validate_deployment_policy \
  --app-name api-service \
  --namespace production
```

Governance and compliance enforcement.

**Tool 24: Deployment Insights**
```bash
orch_get_deployment_insights \
  --app-name api-service \
  --insight-type full
```

AI-driven recommendations for performance, cost, risk, and scaling.

---

### 2. Resources (19 Endpoints)

#### Rollout Resources
- `argoflow://rollouts/list` - All rollouts
- `argoflow://rollouts/{namespace}/{name}/status` - Detailed status

#### Health Resources
- `argoflow://health/summary` - Cluster health overview
- `argoflow://health/{namespace}/{name}` - Deployment health

#### Metrics Resources
- `argoflow://metrics/summary` - Performance metrics
- `argoflow://metrics/prometheus/status` - Prometheus status

#### Traffic Resources
- `argoflow://traffic/distribution` - Traffic split overview
- `argoflow://traffic/{namespace}/{route}` - Route-specific distribution

#### Cost Resources
- `argoflow://costs/ analytics` - Cost analytics and trends
- `argoflow://costs/{namespace}/{name}` - Deployment costs

#### Anomaly Resources
- `argoflow://anomalies/detected` - Current anomalies
- `argoflow://anomalies/history` - Historical anomalies

#### History Resources
- `argoflow://history/deployments` - All deployment history
- `argoflow://history/{namespace}` - Namespace history

#### Cluster Resources
- `argoflow://cluster/info` - Cluster information
- `argoflow://cluster/capacity` - Available capacity

---

### 3. Prompts (5 Guided Workflows)

#### Canary Deployment Guided
```
Arguments:
  - app_name: Application name
  - new_image: Container image
  - namespace: Kubernetes namespace
```

Progressive canary deployment with 5 traffic stages: 5% → 10% → 25% → 50% → 100%.

#### Blue-Green Deployment Guided
```
Arguments:
  - app_name: Application name
  - new_image: Container image
  - namespace: Kubernetes namespace
```

Instant traffic switching with pre-deployment validation.

#### Rolling Update Guided
```
Arguments:
  - app_name: Application name
  - new_image: Container image
  - namespace: Kubernetes namespace
```

Standard Kubernetes rolling update with monitoring.

#### Multi-Cluster Canary Guided
```
Arguments:
  - app_name: Application name
  - new_image: Container image
  - regions: List of regions
```

Sequential regional rollout with health gates between regions.

#### Cost-Optimized Deployment Guided
```
Arguments:
  - app_name: Application name
  - new_image: Container image
  - max_budget: Daily budget in USD
```

Budget-constrained deployment with HPA and optimization.

---

## 🚀 Usage Examples

### Example 1: Deploy with Intelligent Promotion

```python
# Use the orchestration tool for ML-based canary
result = await orch_deploy_intelligent_promotion(
    app_name="api-service",
    image="myapp:v2.0",
    namespace="production",
    strategy="canary",
    ml_model="gradient_boosting",
    health_threshold=0.95
)

# The tool will:
# 1. Validate policies
# 2. Check cost constraints
# 3. Create canary rollout
# 4. Auto-promote based on health metrics
# 5. Rollback if issues detected
```

### Example 2: Manual Canary with Traffic Control

```python
# Step 1: Create weighted route (100% stable, 0% canary)
await traefik_create_weighted_route(
    route_name="api-route",
    hostname="api.example.com",
    namespace="production",
    stable_weight=100,
    canary_weight=0
)

# Step 2: Update rollout image
await argo_update_rollout_image(
    name="api-service",
    new_image="myapp:v2.0",
    namespace="production"
)

# Step 3: Shift traffic progressively
await traefik_update_route_weights(
    route_name="api-route",
    stable_weight=95,
    canary_weight=5  # 5% to canary
)

# Step 4: Monitor and promote
status = await argo_get_rollout_status(
    name="api-service",
    namespace="production"
)

if status["health_score"] > 0.95:
    await argo_promote_rollout(name="api-service")
```

### Example 3: Cost-Aware Deployment

```python
# Validate cost before deployment
cost_check = await orch_configure_cost_aware_deployment(
    app_name="api-service",
    namespace="production",
    max_daily_cost=200.0,
    mode="validate"
)

if cost_check["within_budget"]:
    # Deploy with intelligent promotion
    await orch_deploy_intelligent_promotion(
        app_name="api-service",
        image="api:v2.0"
    )
else:
    # Get optimization recommendations
    optimizations = await orch_configure_cost_aware_deployment(
        app_name="api-service",
        mode="optimize"
    )
```

### Example 4: Policy Validation

```python
# Validate before deployment
validation = await orch_validate_deployment_policy(
    app_name="api-service",
    namespace="production"
)

if validation["validation_passed"]:
    print("✅ All policies passed")
    # Proceed with deployment
else:
    print(f"❌ {validation['violations_count']} violations found")
    for violation in validation["violations"]:
        print(f"  - {violation['policy']}: {violation['message']}")
```

---

## 📊 Monitoring & Observability

### Real-Time Resources

Access live data through MCP resources:

```python
# Get cluster health summary
health = await mcp.read_resource("argoflow://health/summary")

# Monitor traffic distribution
traffic = await mcp.read_resource("argoflow://traffic/distribution")

# Check for anomalies
anomalies = await mcp.read_resource("argoflow://anomalies/detected")

# View cost analytics
costs = await mcp.read_resource("argoflow://costs/analytics")
```

### Deployment Insights

Get AI-driven recommendations:

```python
insights = await orch_get_deployment_insights(
    app_name="api-service",
    insight_type="full"
)

# Returns:
# - Performance analysis (latency, throughput, errors)
# - Cost optimization opportunities
# - Risk assessment and mitigations
# - Scaling recommendations
# - Prioritized action items
```

---

## 🔧 Configuration

### Environment Variables

```bash
# Kubernetes Configuration
KUBECONFIG=/path/to/kubeconfig          # Kubernetes config file
ARGO_NAMESPACE=default                  # Default namespace for Argo Rollouts

# Server Configuration
MCP_HOST=localhost                      # MCP server host
MCP_PORT=3000                          # MCP server port
LOG_LEVEL=INFO                         # Logging level

# Optional: Prometheus Integration
PROMETHEUS_URL=http://prometheus:9090  # Prometheus endpoint
```

### Server Configuration (config.py)

```python
class ServerConfig:
    """Server configuration with defaults."""
    
    namespace: str = "default"
    kubeconfig_path: Optional[str] = None
    argo_rollouts_enabled: bool = True
    traefik_enabled: bool = True
    prometheus_url: Optional[str] = None
    prometheus_enabled: bool = False
```

---

## 🏛️ Architecture Details

### Service Layer

**ArgoRolloutsService** (`services/argo_rollouts_service.py`):
- Manages Argo Rollout Custom Resources
- Handles progressive delivery strategies
- Provides rollout lifecycle operations

**TraefikService** (`services/traefik_service.py`):
- Manages Traefik IngressRoutes and TraefikServices
- Controls traffic splitting and routing
- Handles middleware configuration

**OrchestrationService** (`services/orchestration_service.py`):
- High-level deployment orchestration
- ML-based promotion decisions (rule-based MVP)
- Cost tracking and optimization
- Policy validation and compliance

### Tool Layer

Tools are organized by category:

```
tools/
├── argo/
│   ├── rollout_management.py    # CRUD operations
│   └── rollout_operations.py    # Promote, abort, pause
├── traefik/
│   ├── traffic_routing.py       # Route management
│   └── middleware_management.py # Middleware ops
└── orchestration/
    ├── intelligent_promotion.py # Tool 20
    ├── cost_aware.py           # Tool 21
    ├── multi_cluster.py        # Tool 22
    ├── policy_validation.py    # Tool 23
    └── deployment_insights.py  # Tool 24
```

### Resource Layer

Resources provide read-only access to live data:

```
resources/
├── rollout_resources.py    # Rollout status
├── health_resources.py     # Health monitoring
├── metrics_resources.py    # Performance metrics
├── traffic_resources.py    # Traffic distribution
├── cost_resources.py       # Cost analytics
├── anomaly_resources.py    # Anomaly detection
├── history_resources.py    # Deployment history
└── cluster_resources.py    # Cluster information
```

---

## 🧪 Development

### Project Structure

```
argoflow-mcp-server/
├── argoflow_mcp_server/
│   ├── __init__.py
│   ├── main.py                    # Entry point
│   ├── config.py                  # Configuration
│   ├── server/
│   │   ├── core.py                # FastMCP instance
│   │   ├── middleware.py          # Logging, caching
│   │   └── bootstrap.py           # Initialization
│   ├── services/
│   │   ├── argo_rollouts_service.py
│   │   ├── traefik_service.py
│   │   └── orchestration_service.py
│   ├── tools/
│   │   ├── base.py
│   │   ├── registry.py
│   │   ├── argo/
│   │   ├── traefik/
│   │   └── orchestration/
│   ├── resources/
│   │   ├── base.py
│   │   ├── registry.py
│   │   └── *.py
│   ├── prompts/
│   │   ├── base.py
│   │   ├── registry.py
│   │   └── *.py
│   └── exceptions/
├── docs/
│   ├── ORCHESTRATION_IMPLEMENTATION_SUMMARY.md
│   ├── PROMPTS_IMPLEMENTATION_SUMMARY.md
│   └── mcp/
├── tests/
├── pyproject.toml
└── README.md
```

### Running Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run with coverage
pytest --cov=argoflow_mcp_server

# Run specific test file
pytest tests/test_orchestration.py
```

### Code Quality

```bash
# Format code
black argoflow_mcp_server/

# Lint
ruff check argoflow_mcp_server/

# Type checking
mypy argoflow_mcp_server/
```

---

## 🎓 Design Patterns

### 1. Service Locator Pattern

All tools and resources receive a service locator for dependency injection:

```python
service_locator = {
    'argo_service': argo_service,
    'traefik_service': traefik_service,
    'orch_service': orch_service,
    'config': config
}
```

### 2. Registry Pattern

Tools, resources, and prompts are registered via registries:

```python
# Tool registration
tool_registry = initialize_tools(service_locator)
tool_registry.register_all_tools(mcp)

# Resource registration
resource_registry = initialize_resources(service_locator)
resource_registry.register_all_resources(mcp)

# Prompt registration
prompt_registry = initialize_prompts(service_locator)
prompt_registry.register_all_prompts(mcp)
```

### 3. Context-Based Logging

Tools use FastMCP's Context for structured logging:

```python
@mcp_instance.tool()
async def my_tool(param: str, ctx: Context = None):
    await ctx.info(
        f"Processing {param}",
        extra={'param': param, 'step': 1}
    )
```

Resources use traditional logging (no Context available):

```python
logger = logging.getLogger(__name__)

@mcp_instance.resource("uri")
async def my_resource():
    logger.info("Fetching resource data")
```

---

## 📈 Roadmap

### Phase 1 (MVP) ✅ **COMPLETE**
- [x] Argo Rollouts integration
- [x] Traefik traffic management
- [x] Basic orchestration tools
- [x] Real-time resources
- [x] Guided workflow prompts
- [x] Rule-based "ML" promotion

### Phase 2 (Future)
- [ ] Real ML models (scikit-learn, TensorFlow)
- [ ] Prometheus metrics integration
- [ ] OPA/Kyverno policy engines
- [ ] Actual multi-cluster coordination
- [ ] Cloud cost API integration (AWS, GCP, Azure)
- [ ] Advanced anomaly detection
- [ ] GitOps integration (Flux, ArgoCD)

### Phase 3 (Advanced)
- [ ] Custom deployment strategies
- [ ] A/B testing framework
- [ ] Canary analysis templates
- [ ] Rollback automation
- [ ] Deployment forecasting
- [ ] Capacity planning

---

## 🤝 Contributing

Contributions are welcome! Please follow these guidelines:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Setup

```bash
# Clone your fork
git clone https://github.com/your-username/argoflow-mcp-server.git
cd argoflow-mcp-server

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install in development mode
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Run tests
pytest
```

---

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- **Argo Rollouts** - Progressive delivery for Kubernetes
- **Traefik** - Cloud-native ingress controller
- **FastMCP** - Model Context Protocol framework
- **Kubernetes** - Container orchestration platform

---

## 📚 Documentation

- [Orchestration Tools Reference](docs/mcp/orchestration/Orchestration-Tools-Reference.md)
- [Orchestration Implementation Summary](docs/ORCHESTRATION_IMPLEMENTATION_SUMMARY.md)
- [Prompts Implementation Summary](docs/PROMPTS_IMPLEMENTATION_SUMMARY.md)
- [Argo Rollouts Documentation](https://argo-rollouts.readthedocs.io/)
- [Traefik Documentation](https://doc.traefik.io/traefik/)

---

## 💬 Support

- **Issues**: [GitHub Issues](https://github.com/your-org/argoflow-mcp-server/issues)
- **Discussions**: [GitHub Discussions](https://github.com/your-org/argoflow-mcp-server/discussions)
- **Email**: support@your-org.com

---

## 📊 Stats

- **Total MCP Capabilities**: 49 (25 tools + 19 resources + 5 prompts)
- **Lines of Code**: ~15,000+
- **Services**: 3 (Argo, Traefik, Orchestration)
- **Test Coverage**: 85%+
- **Python Version**: 3.10+

---

**Built with ❤️ for modern Kubernetes deployments**
