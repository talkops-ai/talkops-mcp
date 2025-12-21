"""Helm chart validation and analysis tools."""

import yaml
from typing import Dict, Any, Optional, List
from pydantic import Field
from fastmcp import Context
from helm_mcp_server.exceptions import HelmOperationError, HelmValidationError
from helm_mcp_server.tools.base import BaseTool


class ValidationTools(BaseTool):
    """Tools for validating and analyzing Helm charts."""
    
    def register(self, mcp_instance) -> None:
        """Register tools with FastMCP."""
        
        @mcp_instance.tool()
        async def helm_validate_values(
            chart_name: str = Field(..., description='Chart name'),
            values: dict = Field(default_factory=dict, description='Chart values to validate (defaults to empty dict for default chart values)'),
            json_schema: Optional[dict] = Field(default=None, description='Optional JSON schema for validation'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Validate Helm chart values against schema.
            
            Args:
                chart_name: Chart name
                values: Values to validate
                json_schema: Optional JSON schema for validation
            
            Returns:
                Validation result with status and any errors
            
            Raises:
                HelmValidationError: If validation fails
            """
            await ctx.info(
                f"Validating values for chart '{chart_name}'",
                extra={
                    'chart_name': chart_name,
                    'has_schema': json_schema is not None
                }
            )
            
            await ctx.debug( 'Checking values against chart requirements')
            
            try:
                # Call service with individual parameters (no serialization needed)
                result = self.validation_service.validate_values(
                    chart_name=chart_name,
                    values=values,
                    schema=json_schema,
                )
                
                if result.get('warnings'):
                    for warning in result['warnings']:
                        await ctx.warning(
                            warning,
                            extra={'chart_name': chart_name}
                        )
                
                await ctx.info(
                    f"Validation successful for '{chart_name}'",
                    extra={
                        'chart_name': chart_name,
                        'warnings_count': len(result.get('warnings', []))
                    }
                )
                
                return result
            
            except HelmValidationError as e:
                await ctx.error(
                    f"Validation failed: {str(e)}",
                    extra={
                        'chart_name': chart_name,
                        'error': str(e)
                    }
                )
                raise
            except Exception as e:
                await ctx.error(
                    f"Validation error: {str(e)}",
                    extra={
                        'chart_name': chart_name,
                        'error': str(e)
                    }
                )
                raise HelmOperationError(f'Validation failed: {str(e)}')
        
        @mcp_instance.tool()
        async def helm_render_manifests(
            chart_name: str = Field(..., description='Chart name (e.g., bitnami/postgresql)'),
            values: Optional[dict] = Field(default=None, description='Chart values dictionary (will be written to temp file)'),
            values_files: Optional[List[str]] = Field(default=None, description='List of values YAML files (paths or URLs) to use with -f'),
            values_file_content: Optional[str] = Field(default=None, description='Raw YAML content to use as a values file'),
            version: Optional[str] = Field(default=None, description='Specific chart version'),
            namespace: str = Field(default='default', description='Kubernetes namespace'),
            kubeconfig_path: Optional[str] = Field(default=None, description='Path to kubeconfig file for multi-cluster support'),
            context_name: Optional[str] = Field(default=None, description='Kubeconfig context name for multi-cluster support'),
            eks_cluster_name: Optional[str] = Field(default=None, description='AWS EKS cluster name for multi-cluster support'),
            include_full: bool = Field(default=False, description='Include full manifests in response (default: False to save tokens, only summary and preview included)'),
            preview_lines: int = Field(default=100, description='Number of lines to include in preview (default: 100)'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Render Kubernetes manifests from Helm chart and values.
            
            This tool renders Kubernetes manifests from a Helm chart without installing it.
            Useful for previewing what resources would be created or for CI/CD validation.
            
            By default, returns a summary and preview to minimize token usage. Set include_full=True
            to get the complete manifests.
            
            Args:
                chart_name: Chart name (e.g., 'bitnami/postgresql')
                values: Chart values dictionary (will be written to temp file and passed as -f)
                values_files: List of values YAML files (paths or URLs) to use with -f
                values_file_content: Raw YAML content to use as a values file
                version: Specific chart version
                namespace: Kubernetes namespace
                kubeconfig_path: Path to kubeconfig file for multi-cluster support
                context_name: Kubeconfig context name for multi-cluster support
                eks_cluster_name: AWS EKS cluster name for multi-cluster support
                include_full: Include full manifests in response (default: False to save tokens)
                preview_lines: Number of lines to include in preview (default: 100)
            
            Returns:
                Dictionary with:
                - summary: Metadata about resources (count, types, sizes)
                - preview: Truncated preview of manifests (first N lines)
                - full_manifests: Full YAML manifests (only if include_full=True)
            
            Raises:
                HelmOperationError: If rendering fails
            """
            await ctx.info(
                f"Rendering manifests for chart '{chart_name}'",
                extra={
                    'chart_name': chart_name,
                    'namespace': namespace,
                    'version': version
                }
            )
            
            await ctx.debug( 'Generating Kubernetes manifests from chart templates')
            
            try:
                # Call service with individual parameters (no serialization needed)
                manifests = await self.helm_service.render_manifests(
                    chart_name=chart_name,
                    values=values,
                    values_files=values_files,
                    values_file_content=values_file_content,
                    version=version,
                    namespace=namespace,
                    kubeconfig_path=kubeconfig_path,
                    context_name=context_name,
                    eks_cluster_name=eks_cluster_name,
                )
                
                manifest_lines = manifests.split('\n')
                total_lines = len(manifest_lines)
                
                # Parse resources to extract metadata
                resources = []
                resource_types = {}
                
                # Split by document separator and parse each document
                documents = manifests.split('---')
                for doc in documents:
                    if not doc.strip():
                        continue
                    try:
                        # Parse YAML document
                        parsed = yaml.safe_load(doc)
                        if parsed and isinstance(parsed, dict):
                            kind = parsed.get('kind', 'Unknown')
                            metadata = parsed.get('metadata', {})
                            name = metadata.get('name', 'unnamed')
                            
                            resource_types[kind] = resource_types.get(kind, 0) + 1
                            resources.append({
                                'kind': kind,
                                'name': name,
                                'namespace': metadata.get('namespace', namespace)
                            })
                    except yaml.YAMLError:
                        # Skip invalid YAML documents
                        continue
                
                resource_count = len(resources)
                
                # Generate preview (first N lines)
                preview_lines_list = manifest_lines[:preview_lines]
                preview = '\n'.join(preview_lines_list)
                if total_lines > preview_lines:
                    preview += f'\n... ({total_lines - preview_lines} more lines, set include_full=True to see all)'
                
                # Build summary
                summary = {
                    'chart_name': chart_name,
                    'namespace': namespace,
                    'version': version,
                    'total_resources': resource_count,
                    'total_lines': total_lines,
                    'manifest_size_bytes': len(manifests),
                    'resource_types': resource_types,
                    'resource_list': resources[:20] if resource_count <= 20 else resources[:20] + [{'note': f'... and {resource_count - 20} more resources'}]
                }
                
                # Build response
                response = {
                    'summary': summary,
                    'preview': preview
                }
                
                # Include full manifests only if requested or if small (< 5000 chars)
                if include_full or len(manifests) < 5000:
                    response['full_manifests'] = manifests
                else:
                    response['note'] = 'Full manifests not included to save tokens. Set include_full=True to retrieve them.'
                
                await ctx.info(
                    f"Successfully rendered manifests for '{chart_name}'",
                    extra={
                        'chart_name': chart_name,
                        'resource_count': resource_count,
                        'manifest_length': len(manifests),
                        'include_full': include_full
                    }
                )
                
                return response
            
            except Exception as e:
                await ctx.error(
                    f"Manifest rendering failed: {str(e)}",
                    extra={
                        'chart_name': chart_name,
                        'error': str(e)
                    }
                )
                raise HelmOperationError(f'Manifest rendering failed: {str(e)}')
        
        @mcp_instance.tool()
        async def helm_validate_manifests(
            manifests: str = Field(..., description='Kubernetes manifests as YAML string'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Validate Kubernetes manifests (basic YAML and structure validation).
            
            Args:
                manifests: Kubernetes manifests as YAML string
            
            Returns:
                Validation result with status and any errors
            
            Raises:
                HelmValidationError: If validation fails
            """
            await ctx.info(
                'Validating Kubernetes manifests',
                extra={'manifest_length': len(manifests)}
            )
            
            await ctx.debug( 'Checking YAML syntax and resource structure')
            
            try:
                # Call service with individual parameters (no serialization needed)
                result = self.validation_service.validate_manifests(
                    manifests=manifests
                )
                
                if result.get('warnings'):
                    for warning in result['warnings']:
                        await ctx.warning( warning)
                
                await ctx.info(
                    f"Manifest validation successful ({result.get('resource_count', 0)} resources)",
                    extra={
                        'resource_count': result.get('resource_count', 0),
                        'resource_types': result.get('resource_types', {})
                    }
                )
                
                return result
            
            except HelmValidationError as e:
                await ctx.error(
                    f"Manifest validation failed: {str(e)}",
                    extra={'error': str(e)}
                )
                raise
            except Exception as e:
                await ctx.error(
                    f"Validation error: {str(e)}",
                    extra={'error': str(e)}
                )
                raise HelmOperationError(f'Manifest validation failed: {str(e)}')
        
        @mcp_instance.tool()
        async def helm_check_dependencies(
            chart_name: str = Field(..., description='Chart name'),
            repository: str = Field(default='bitnami', description='Helm repository'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Check if chart dependencies are available.
            
            Args:
                chart_name: Chart name
                repository: Helm repository name
            
            Returns:
                Dependency check result with status
            
            Raises:
                HelmOperationError: If check fails
            """
            await ctx.info(
                f"Checking dependencies for chart '{chart_name}'",
                extra={
                    'chart_name': chart_name,
                    'repository': repository
                }
            )
            
            await ctx.debug( 'Analyzing chart dependencies')
            
            try:
                result = await self.helm_service.check_dependencies(
                    chart_name=chart_name,
                    repository=repository,
                )
                
                dep_count = result.get('dependency_count', 0)
                await ctx.info(
                    f"Dependency check completed for '{chart_name}' ({dep_count} dependencies)",
                    extra={
                        'chart_name': chart_name,
                        'dependency_count': dep_count,
                        'all_available': result.get('all_available', False)
                    }
                )
                
                if dep_count == 0:
                    await ctx.debug( 'No dependencies found')
                
                return result
            
            except Exception as e:
                await ctx.error(
                    f"Dependency check failed: {str(e)}",
                    extra={
                        'chart_name': chart_name,
                        'error': str(e)
                    }
                )
                raise HelmOperationError(f'Dependency check failed: {str(e)}')
        
        @mcp_instance.tool()
        async def helm_get_installation_plan(
            chart_name: str = Field(..., description='Chart name'),
            values: dict = Field(default_factory=dict, description='Chart values'),
            namespace: str = Field(default='default', description='Kubernetes namespace'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Generate a detailed installation plan with resource estimates.
            
            Args:
                chart_name: Chart name
                values: Chart values dictionary
                namespace: Kubernetes namespace
            
            Returns:
                Installation plan with resource estimates
            
            Raises:
                HelmOperationError: If plan generation fails
            """
            await ctx.info(
                f"Generating installation plan for '{chart_name}'",
                extra={
                    'chart_name': chart_name,
                    'namespace': namespace
                }
            )
            
            await ctx.debug( 'Analyzing chart resources and dependencies')
            
            try:
                plan = await self.helm_service.get_installation_plan(
                    chart_name=chart_name,
                    values=values,
                    namespace=namespace,
                )
                
                resource_count = plan.get('estimated_resources', 0)
                await ctx.info(
                    f"Installation plan generated for '{chart_name}'",
                    extra={
                        'chart_name': chart_name,
                        'estimated_resources': resource_count,
                        'namespace': namespace
                    }
                )
                
                await ctx.debug( f'Estimated {resource_count} Kubernetes resources')
                
                return plan
            
            except Exception as e:
                await ctx.error(
                    f"Installation plan generation failed: {str(e)}",
                    extra={
                        'chart_name': chart_name,
                        'error': str(e)
                    }
                )
                raise HelmOperationError(f'Installation plan generation failed: {str(e)}')

