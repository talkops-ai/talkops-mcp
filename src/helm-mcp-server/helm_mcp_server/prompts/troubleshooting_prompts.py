"""Troubleshooting-related prompts."""

from mcp.types import Prompt, PromptArgument, PromptMessage, TextContent
from helm_mcp_server.prompts.base import BasePrompt


class TroubleshootingPrompts(BasePrompt):
    """Troubleshooting prompts."""
    
    def register(self, mcp_instance) -> None:
        """Register prompts with FastMCP."""
        
        @mcp_instance.prompt()
        def helm_troubleshooting_guide(error_type: str) -> Prompt:
            """Troubleshooting guide for common Helm issues.
            
            Arguments:
                error_type: Type of error (e.g., "pod-crashloop", "pending", "connection")
            """
            
            troubleshooting_map = {
                "pod-crashloop": """# Pod CrashLoopBackOff

## Symptoms
- Pod enters CrashLoopBackOff state
- Pod restarts constantly
- Logs show application errors

## Diagnosis
1. Check pod logs: `kubectl logs <pod-name>`
2. Check previous logs: `kubectl logs <pod-name> --previous`
3. Describe pod: `kubectl describe pod <pod-name>`
4. Check resource limits: `kubectl top pod <pod-name>`

## Solutions
- Review application logs for errors
- Check if resource limits are sufficient
- Verify configuration values are correct
- Check mount points and volumes
- Verify secrets and configmaps exist
- Review Helm values for misconfigurations
- Check for image pull errors""",
                "pending": """# Pod Stuck in Pending

## Symptoms
- Pod shows status 'Pending'
- No error messages visible

## Diagnosis
1. Describe pod: `kubectl describe pod <pod-name>`
2. Check node capacity: `kubectl top nodes`
3. Check PVC status: `kubectl get pvc`
4. Review node selectors and taints

## Solutions
- Check available resources on nodes
- Verify PVC is bound
- Check node selector requirements
- Look for resource quotas
- Verify node taints and tolerations
- Check for storage class issues""",
                "connection": """# Connection Errors

## Symptoms
- Cannot connect to service
- Connection timeout
- DNS resolution fails

## Diagnosis
1. Verify service exists: `kubectl get svc`
2. Check endpoints: `kubectl get endpoints`
3. Test DNS: `kubectl run -it --rm debug --image=busybox --restart=Never -- nslookup service-name`
4. Check network policies
5. Verify service ports match pod ports

## Solutions
- Verify service selector matches pods
- Check service ports configuration
- Review network policies
- Test connectivity with debug pod
- Verify DNS configuration
- Check firewall rules""",
                "image-pull": """# Image Pull Errors

## Symptoms
- Pod shows ImagePullBackOff or ErrImagePull
- Cannot pull container image

## Diagnosis
1. Check pod events: `kubectl describe pod <pod-name>`
2. Verify image name and tag
3. Check image pull secrets
4. Test image accessibility

## Solutions
- Verify image name and tag are correct
- Check image pull secrets are configured
- Ensure registry credentials are valid
- Verify network access to registry
- Check for private registry authentication
- Review image pull policy settings""",
                "helm-error": """# Helm Installation Errors

## Symptoms
- Helm install/upgrade fails
- Error messages during deployment

## Diagnosis
1. Check Helm release status: `helm status <release-name>`
2. Review Helm values: `helm get values <release-name>`
3. Check rendered manifests: `helm template <chart>`
4. Review Helm logs and events

## Solutions
- Validate Helm values against schema
- Check for missing required values
- Verify chart dependencies are available
- Review Kubernetes API compatibility
- Check for resource conflicts
- Verify namespace permissions"""
            }
            
            content = troubleshooting_map.get(
                error_type,
                f"""# Troubleshooting Guide: {error_type}

No specific guide found for '{error_type}'. 

## General Troubleshooting Steps
1. Check pod status: `kubectl get pods`
2. Review pod logs: `kubectl logs <pod-name>`
3. Describe resources: `kubectl describe <resource-type> <resource-name>`
4. Check Helm release: `helm status <release-name>`
5. Review events: `kubectl get events --sort-by='.lastTimestamp'`

## Common Error Types
- pod-crashloop: Pod restarting continuously
- pending: Pod stuck in pending state
- connection: Service connectivity issues
- image-pull: Container image pull failures
- helm-error: Helm operation failures

For more specific guidance, try one of the above error types."""
            )
            
            return Prompt(
                name="helm-troubleshooting-guide",
                description="Troubleshooting guide for common Helm issues",
                arguments=[
                    PromptArgument(
                        name="error_type",
                        description="Type of error encountered (e.g., pod-crashloop, pending, connection, image-pull, helm-error)",
                        required=True
                    )
                ],
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(type="text", text=content)
                    )
                ]
            )

