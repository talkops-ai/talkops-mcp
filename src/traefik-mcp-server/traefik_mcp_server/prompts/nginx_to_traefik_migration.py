"""NGINX to Traefik migration prompts.

Provides step-by-step guidance for migrating from Ingress NGINX to Traefik.
"""

from typing import Optional
from traefik_mcp_server.prompts.base import BasePrompt


class NginxToTraefikMigrationPrompts(BasePrompt):
    """NGINX to Traefik Migration Prompts.
    
    Provides guided instructions for moving from NGINX Ingress to Traefik
    with zero downtime using side-by-side execution.
    """
    
    def register(self, mcp_instance) -> None:
        """Register migration prompts with FastMCP.
        
        Args:
            mcp_instance: FastMCP server instance
        """
        
        @mcp_instance.prompt()
        async def nginx_to_traefik_migration_guide(phase: str = "overview") -> str:
            """Provide NGINX to Traefik migration guidance.
            
            This prompt gives you the commands and steps needed to perform a true
            zero-downtime migration from NGINX Ingress to Traefik without changing
            your existing Ingress YAMLs right away.
            
            Args:
                phase: Migration phase to show:
                       "overview", "phase1", "phase2", "phase3", "phase4",
                       "monitoring", "rollback"
            
            Returns:
                Formatted markdown guide for the requested phase
            """
            
            valid_phases = ["overview", "phase1", "phase2", "phase3", "phase4", "monitoring", "rollback"]
            
            # Normalize and validate phase
            phase = phase.lower()
            if phase not in valid_phases:
                return f"""# ❌ Invalid Phase: {phase}

Valid phases are:
- `overview`: Complete migration strategy and prerequisites
- `phase1`: Install Traefik alongside NGINX
- `phase2`: Validate Traefik routing
- `phase3`: Cutover DNS traffic
- `phase4`: Clean up NGINX
- `monitoring`: What to watch during cutover
- `rollback`: How to abort the migration
"""

            # ------------------------------------------------------------------
            # OVERVIEW
            # ------------------------------------------------------------------
            if phase == "overview":
                return """# 🔄 NGINX to Traefik Migration Strategy

> **Goal:** Migrate from NGINX Ingress Controller to Traefik with **Zero Downtime**.

## How it Works
Traefik has a native `kubernetesIngressNginx` provider that watches your **existing** `Ingress` resources and automatically translates NGINX annotations (like `ssl-redirect`, `rewrite-target`, CORS, etc.) into Traefik configuration. 

You do **NOT** need to rewrite your `Ingress` YAML files on Day 1.

## The Side-by-Side (Active-Active) Strategy
```text
Current:     DNS → NGINX LBIP → NGINX → Your Services
Phase 1 & 2: DNS → NGINX LBIP → NGINX → Your Services
                 (Test) → Traefik LBIP → Traefik → Your Services
Phase 3:     DNS (Updated) → Traefik LBIP → Traefik → Your Services
Phase 4:     Remove NGINX Controller 
```

## Prerequisites Checklist
Before starting, ensure you have:
- [ ] Validated your cluster can support multiple `LoadBalancer` services on ports 80/443 simultaneously.
- [ ] Backed up your Ingresses: `kubectl get ingress -A -o yaml > ingress-backup.yaml`
- [ ] Backed up NGINX configs: `kubectl get cm -A -l app.kubernetes.io/name=ingress-nginx -o yaml > nginx-cm-backup.yaml`

---
**Next Step:** Ask for `nginx_to_traefik_migration_guide(phase="phase1")` to begin the installation.
"""

            # ------------------------------------------------------------------
            # PHASE 1
            # ------------------------------------------------------------------
            if phase == "phase1":
                return """# 📦 Phase 1: Install Traefik Side-by-Side

In this phase, you install Traefik alongside your existing NGINX controller. Traefik will get its own external IP but will listen to the same `Ingress` resources as NGINX.

## 1. Add Traefik Helm Repo
Run the following commands in your terminal:
```shell
helm repo add traefik https://traefik.github.io/charts && helm repo update
```

## 2. Install Traefik with NGINX Provider Enabled
We explicitly tell Traefik to look at `nginx` IngressClasses and parse their annotations.

Run the following command in your terminal:
```shell
helm upgrade --install traefik traefik/traefik \\
  --namespace traefik --create-namespace \\
  --set providers.kubernetesIngressNginx.enabled=true \\
  --set providers.kubernetesIngress.publishedService.enabled=false
```

## 3. Verify Both Controllers Are Running
Ensure both NGINX and Traefik have external IPs (LoadBalancers).

Run the following command in your terminal:
```shell
kubectl get svc -n ingress-nginx ingress-nginx-controller && kubectl get svc -n traefik traefik
```

---
**Next Step:** Run `nginx_to_traefik_migration_guide(phase="phase2")` to test the new Traefik pipeline securely.
"""

            # ------------------------------------------------------------------
            # PHASE 2
            # ------------------------------------------------------------------
            if phase == "phase2":
                return """# 🧪 Phase 2: Validate Traefik Routing

Traefik and NGINX are now reading the same `Ingress` rules. DNS still points to NGINX, so production traffic is untouched. We will test Traefik bypassing DNS.

## 1. Get Traefik's External IP
Run the following command in your terminal:
```shell
kubectl get svc -n traefik traefik -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
```

## 2. Test Traffic via `curl` Host Resolution
Pick an existing application (e.g., `myapp.example.com`). Force `curl` to resolve that host to Traefik's IP.

Run the following command in your terminal:
```shell
curl -v -H "Host: myapp.example.com" http://<TRAEFIK_EXTERNAL_IP>/
# OR mapping directly
curl -v --resolve myapp.example.com:80:<TRAEFIK_EXTERNAL_IP> http://myapp.example.com/
```

## 3. Verify NGINX Annotations Worked
Test specific endpoint behaviors that relied on NGINX annotations:
- Check HTTP -> HTTPS redirects
- Check CORS headers
- Check rewrite targets

If everything responds identically to production, Traefik correctly parsed the NGINX configuration!

---
**Next Step:** Run `nginx_to_traefik_migration_guide(phase="phase3")` for the DNS cutover strategy.
"""

            # ------------------------------------------------------------------
            # PHASE 3
            # ------------------------------------------------------------------
            if phase == "phase3":
                return """# 🔀 Phase 3: Traffic Cutover (DNS)

Once validated, it is time to shift live traffic. We shift traffic at the DNS layer.

## The Strategy
You have three options depending on your risk tolerance:

### Option A: Progressive Shift (Weighted DNS) - Safest
If your DNS provider (Route53, Cloudflare, etc.) supports weighted routing:
1. Add Traefik's External IP with a weight of 10% (NGINX at 90%).
2. Monitor error rates for 15-30 minutes.
3. Increase Traefik weight: 25% → 50% → 100%.
4. Drop NGINX record.

### Option B: Blue/Green DNS Switch
1. Lower your DNS TTL for the domain to 60 seconds (do this 24 hours in advance).
2. Swap the DNS A Record from the NGINX IP to the Traefik IP.
3. Wait for DNS propagation.

### Option C: In-Cluster Service Swap (No DNS Change)
If you cannot change DNS but control the cluster, you can repoint the `LoadBalancer` service:
1. Patch the existing NGINX `LoadBalancer` service to point its selectors to Traefik pods instead of NGINX pods.
2. *Note: Traefik handles this natively, but it requires careful coordination of port names/targets.* Options A/B are preferred.

## What to Monitor
During cutover, watch:
```text
Resource: traefik://metrics/{namespace}/{service}/summary
```
Ensure HTTP 5xx errors do not spike and latency remains stable.

---
**Next Step:** Run `nginx_to_traefik_migration_guide(phase="phase4")` for cleanup.
"""

            # ------------------------------------------------------------------
            # PHASE 4
            # ------------------------------------------------------------------
            if phase == "phase4":
                return """# 🧹 Phase 4: Clean Up NGINX

DNS has propagated entirely, and Traefik is handling 100% of traffic. You can now safely remove NGINX.

## 1. Preserve the NGINX IngressClass
IMPORTANT: Do **not** let Helm delete the `nginx` IngressClass object. If it deletes the class, your existing `Ingress` resources might lose their binding!

Create a standalone IngressClass to preserve the binding. Apply the following YAML:
```yaml
apiVersion: networking.k8s.io/v1
kind: IngressClass
metadata:
  name: nginx
  annotations:
    ingressclass.kubernetes.io/is-default-class: "true"
spec:
  controller: traefik.io/ingress-controllers
```

## 2. Uninstall NGINX Controller
Run the following command in your terminal:
```shell
helm uninstall ingress-nginx -n ingress-nginx
```

## 3. Optional Day 2 Modernization
Now that you are safely on Traefik, you can begin migrating individual applications from legacy `networking.k8s.io/v1` Ingress objects to Traefik's native `IngressRoute` CRD to unlock advanced features like Argo Rollouts Traffic Shifting, Middlewares, and TCP/UDP routing.

Use the `convert_nginx_ingress_to_traefik` MCP tool to convert them one by one! This tool will take your NGINX YAML string and output Traefik `IngressRoute` and `StripPrefixRegex` (Middleware) YAMLs.
"""

            # ------------------------------------------------------------------
            # MONITORING
            # ------------------------------------------------------------------
            if phase == "monitoring":
                return """# 📊 Migration Monitoring

During Phase 3 (DNS Cutover), monitor these core metrics closely:

| Metric | What to look for | Tool / Command |
| ------ | ---------------- | -------------- |
| **Provider Loaded** | Confirm Traefik sees NGINX ingresses | `kubectl logs -n traefik deploy/traefik \\| grep ingressNginx` |
| **HTTP Errors** | Monitor for spikes in 5xx or 404s | `traefik://metrics/traefik/traefik/summary` |
| **Latency** | Significant jumps in request duration | `traefik://metrics/traefik/traefik/summary` |
| **Ingress Status** | Ensure Ingress objects don't show sync errors | `kubectl describe ingress` |

If you see continuous 404s on Traefik, a specific NGINX annotation might not have translated correctly or a Secret (TLS) might be missing in the Traefik namespace.
"""

            # ------------------------------------------------------------------
            # ROLLBACK
            # ------------------------------------------------------------------
            if phase == "rollback":
                return """# ⏪ Migration Rollback

If you detect issues during Phase 2 or Phase 3, you can rollback with zero downtime.

## If in Phase 2 (Validation):
No user traffic is affected. You can just uninstall Traefik or ignore it while you fix the configuration.
```shell
helm uninstall traefik -n traefik
```

## If in Phase 3 (DNS Cutover):
If you see errors, Traffic is partially flowing to Traefik.
1. Immediately revert the DNS changes back entirely to the NGINX LoadBalancer IP.
2. Wait for TTL to expire (traffic will drain back to NGINX).
3. Check NGINX logs to verify it is serving ALL traffic again.
4. Uninstall Traefik to clean up the cluster.

> Because NGINX was never removed or altered, the rollback is instantaneous as soon as DNS queries resolve.
"""

            # Fallback
            return "# ❌ Unknown Phase"
            
        return None
