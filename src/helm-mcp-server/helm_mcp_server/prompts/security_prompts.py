"""Security-related prompts."""

from mcp.types import Prompt, PromptMessage, TextContent
from helm_mcp_server.prompts.base import BasePrompt


class SecurityPrompts(BasePrompt):
    """Security prompts."""
    
    def register(self, mcp_instance) -> None:
        """Register prompts with FastMCP."""
        
        @mcp_instance.prompt()
        def helm_security_checklist() -> Prompt:
            """Security considerations for Helm deployments.
            
            This prompt provides a comprehensive security checklist for Helm chart deployments.
            """
            return Prompt(
                name="helm-security-checklist",
                description="Security considerations for Helm deployments",
                arguments=[],
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text="""# Helm Security Checklist

## Pre-Deployment Security

### Image Security
- [ ] Use specific image tags (avoid 'latest')
- [ ] Scan images for vulnerabilities
- [ ] Use images from trusted registries
- [ ] Verify image signatures
- [ ] Enable image pull secrets for private registries

### Secrets Management
- [ ] Never hardcode secrets in values files
- [ ] Use Kubernetes secrets or external secret managers
- [ ] Rotate secrets regularly
- [ ] Use RBAC to restrict secret access
- [ ] Encrypt secrets at rest

### Network Security
- [ ] Configure network policies
- [ ] Use TLS for all service communications
- [ ] Restrict ingress/egress traffic
- [ ] Implement service mesh if needed
- [ ] Review exposed ports and services

### RBAC and Permissions
- [ ] Follow principle of least privilege
- [ ] Use service accounts with minimal permissions
- [ ] Review RBAC roles and bindings
- [ ] Avoid cluster-admin privileges
- [ ] Use namespace-scoped resources when possible

## Configuration Security

### Values Security
- [ ] Review all configuration values
- [ ] Avoid exposing sensitive data in logs
- [ ] Use environment variables for sensitive configs
- [ ] Validate input values
- [ ] Review default values for security implications

### Resource Limits
- [ ] Set appropriate resource requests and limits
- [ ] Prevent resource exhaustion attacks
- [ ] Use resource quotas
- [ ] Monitor resource usage

### Pod Security
- [ ] Enable Pod Security Standards
- [ ] Run containers as non-root when possible
- [ ] Use read-only root filesystems
- [ ] Drop unnecessary capabilities
- [ ] Use security contexts appropriately

## Runtime Security

### Monitoring and Logging
- [ ] Enable security event logging
- [ ] Monitor for suspicious activities
- [ ] Set up alerts for security events
- [ ] Review logs regularly
- [ ] Implement audit logging

### Updates and Patches
- [ ] Keep Kubernetes cluster updated
- [ ] Update Helm charts regularly
- [ ] Apply security patches promptly
- [ ] Review changelogs for security fixes
- [ ] Test updates in non-production first

### Backup and Recovery
- [ ] Implement regular backups
- [ ] Test restore procedures
- [ ] Encrypt backup data
- [ ] Store backups securely
- [ ] Document recovery procedures

## Post-Deployment Security

### Access Control
- [ ] Review who has access to the deployment
- [ ] Implement MFA where possible
- [ ] Use strong authentication
- [ ] Review access logs regularly
- [ ] Remove unnecessary access

### Compliance
- [ ] Ensure compliance with security policies
- [ ] Document security configurations
- [ ] Conduct security reviews
- [ ] Maintain security documentation
- [ ] Follow organizational security standards

## Common Security Risks

- ❌ Exposing services without authentication
- ❌ Using default passwords
- ❌ Storing secrets in plain text
- ❌ Running containers as root
- ❌ Allowing unrestricted network access
- ❌ Not updating dependencies
- ❌ Ignoring security advisories
- ❌ Over-privileged service accounts"""
                        )
                    )
                ]
            )

