"""Helm chart installation and management tools."""

import re
from typing import Dict, Any, Optional, List
from pydantic import Field
from fastmcp import Context
from helm_mcp_server.exceptions import HelmOperationError
from helm_mcp_server.tools.base import BaseTool


class ChartManagementTools(BaseTool):
    """Tools for installing and managing Helm charts."""
    
    def register(self, mcp_instance) -> None:
        """Register tools with FastMCP."""
        
        @mcp_instance.tool()
        async def helm_install_chart(
            chart_name: str = Field(..., min_length=1, description='Chart name (e.g., bitnami/postgresql)'),
            release_name: str = Field(..., min_length=1, description='Release name'),
            namespace: str = Field(default='default', description='Kubernetes namespace'),
            values: dict = Field(default_factory=dict, description='Chart values dictionary (will be written to temp file)'),
            dry_run: bool = Field(default=False, description='Perform dry-run without installing'),
            skip_crds: bool = Field(default=False, description='Skip CRD installation (useful when CRDs already exist)'),
            extra_args: Optional[List[str]] = Field(default=None, description='Extra CLI flags to pass to helm install (e.g., --set-string)'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Install a Helm chart to Kubernetes cluster.
            
            Args:
                chart_name: Chart name (e.g., 'bitnami/postgresql')
                release_name: Release name
                namespace: Kubernetes namespace
                values: Chart values dictionary (will be written to temp file and passed as -f)
                dry_run: Perform dry-run without installing
                skip_crds: Skip CRD installation (useful when CRDs already exist)
                extra_args: Extra CLI flags to pass to helm install (e.g., --set-string)
            
            Returns:
                Installation result with status and details
            
            Raises:
                HelmOperationError: If installation fails
            """
            await ctx.info(
                f"Starting installation of chart '{chart_name}' as release '{release_name}'",
                extra={
                    'chart_name': chart_name,
                    'release_name': release_name,
                    'namespace': namespace,
                    'dry_run': dry_run
                }
            )
            
            if dry_run:
                await ctx.debug( 'Performing dry-run installation (no resources will be created)')
            else:
                await ctx.debug( f'Installing to namespace: {namespace}')
            
            try:
                # Check if release already exists (skip check for dry-run)
                if not dry_run:
                    await ctx.debug( f'Checking if release "{release_name}" already exists in namespace "{namespace}"')
                    release_exists = await self.helm_service.release_exists(
                        release_name=release_name,
                        namespace=namespace
                    )
                    
                    if release_exists:
                        error_msg = (
                            f"Release '{release_name}' already exists in namespace '{namespace}'. "
                            f"Cannot install a new release with the same name. "
                            f"Please use 'helm_upgrade_release' to upgrade the existing release, "
                            f"or 'helm_uninstall_release' to remove it first."
                        )
                        await ctx.error(
                            error_msg,
                            extra={
                                'release_name': release_name,
                                'namespace': namespace,
                                'suggestion': 'use_upgrade_or_uninstall'
                            }
                        )
                        raise HelmOperationError(error_msg)
                    
                    # Check for other releases in the namespace that might conflict
                    # (e.g., same chart installed with different release name)
                    await ctx.debug(f'Checking for other releases in namespace "{namespace}"')
                    existing_releases = await self.helm_service.list_releases_in_namespace(namespace=namespace)
                    if existing_releases:
                        # Extract chart name from chart_name (handle repo/chart format)
                        chart_base_name = chart_name.split('/')[-1] if '/' in chart_name else chart_name
                        
                        # Check if any existing release uses a similar chart
                        conflicting_releases = []
                        for release in existing_releases:
                            release_chart = release.get('chart', '')
                            # Check if chart names match (e.g., "argo-cd" vs "argo-cd-9.1.7")
                            if chart_base_name.lower() in release_chart.lower() or release_chart.lower().startswith(chart_base_name.lower()):
                                conflicting_releases.append({
                                    'name': release.get('name', 'unknown'),
                                    'chart': release_chart,
                                    'status': release.get('status', 'unknown')
                                })
                        
                        if conflicting_releases:
                            release_names = [r['name'] for r in conflicting_releases]
                            error_msg = (
                                f"Found existing release(s) in namespace '{namespace}' that may conflict: {', '.join(release_names)}. "
                                f"These releases may have installed CRDs that conflict with installing '{chart_name}' as '{release_name}'. "
                                f"If you want to install this chart, you should either:\n"
                                f"1. Use 'skip_crds=True' to skip CRD installation (if CRDs are already installed), or\n"
                                f"2. Uninstall the existing release(s) first using 'helm_uninstall_release', or\n"
                                f"3. Use 'helm_upgrade_release' to upgrade the existing release instead of installing a new one."
                            )
                            await ctx.warning(
                                error_msg,
                                extra={
                                    'release_name': release_name,
                                    'namespace': namespace,
                                    'conflicting_releases': release_names,
                                    'suggestion': 'check_existing_releases'
                                }
                            )
                            # Don't raise error here - let Helm try and provide better error if it fails
                
                # Call service with parameters matching documentation
                result = await self.helm_service.install_chart(
                    chart_name=chart_name,
                    release_name=release_name,
                    namespace=namespace,
                    values=values,
                    dry_run=dry_run,
                    skip_crds=skip_crds,
                    extra_args=extra_args,
                )
                
                if dry_run:
                    await ctx.info(
                        f"Dry-run completed successfully for '{release_name}'",
                        extra={'release_name': release_name}
                    )
                else:
                    await ctx.info(
                        f"Successfully installed '{release_name}'",
                        extra={
                            'release_name': release_name,
                            'namespace': namespace
                        }
                    )
                
                return result
            
            except Exception as e:
                error_str = str(e)
                
                # Check for CRD ownership/conflict errors
                is_crd_error = (
                    'conflict' in error_str.lower() and ('crd' in error_str.lower() or 'customresourcedefinition' in error_str.lower())
                ) or (
                    'invalid ownership' in error_str.lower() or 'meta.helm.sh/release-name' in error_str.lower()
                )
                
                if is_crd_error:
                    # Extract existing release name from error if present
                    existing_release_name = None
                    if 'current value is' in error_str.lower():
                        # Try to extract release name from error like: "current value is \"argocd\""
                        match = re.search(r'current value is ["\']([^"\']+)["\']', error_str, re.IGNORECASE)
                        if match:
                            existing_release_name = match.group(1)
                    
                    # Check if release exists (might have been created between check and install)
                    try:
                        release_exists = await self.helm_service.release_exists(
                            release_name=release_name,
                            namespace=namespace
                        )
                        
                        if release_exists:
                            error_msg = (
                                f"Installation failed: Release '{release_name}' already exists in namespace '{namespace}'. "
                                f"CRD conflict occurred because the release is already installed. "
                                f"Please use 'helm_upgrade_release' to upgrade the existing release, "
                                f"or 'helm_uninstall_release' to remove it first."
                            )
                        elif existing_release_name:
                            error_msg = (
                                f"Installation failed: CRD ownership conflict detected. "
                                f"The CustomResourceDefinitions required by this chart are already owned by release '{existing_release_name}' "
                                f"in namespace '{namespace}'. You cannot install '{chart_name}' as '{release_name}' because the CRDs "
                                f"are managed by a different release.\n\n"
                                f"To resolve this, you have the following options:\n"
                                f"1. Use 'skip_crds=True' to skip CRD installation (if CRDs are already installed and compatible), or\n"
                                f"2. Uninstall the existing release '{existing_release_name}' first using 'helm_uninstall_release', or\n"
                                f"3. Use 'helm_upgrade_release' to upgrade the existing release '{existing_release_name}' instead of installing a new one."
                            )
                        else:
                            # Try to find conflicting releases
                            existing_releases = await self.helm_service.list_releases_in_namespace(namespace=namespace)
                            if existing_releases:
                                release_names = [r.get('name', 'unknown') for r in existing_releases]
                                error_msg = (
                                    f"Installation failed: CRD conflict detected. "
                                    f"The CustomResourceDefinitions required by this chart already exist and are owned by "
                                    f"another release in namespace '{namespace}'. Found existing release(s): {', '.join(release_names)}.\n\n"
                                    f"To resolve this, you have the following options:\n"
                                    f"1. Use 'skip_crds=True' to skip CRD installation (if CRDs are already installed and compatible), or\n"
                                    f"2. Uninstall the existing release(s) first using 'helm_uninstall_release', or\n"
                                    f"3. Use 'helm_upgrade_release' to upgrade an existing release instead of installing a new one."
                                )
                            else:
                                error_msg = (
                                    f"Installation failed: CRD conflict detected. "
                                    f"The CustomResourceDefinitions required by this chart already exist in the cluster "
                                    f"and are owned by a different release. "
                                    f"Consider using 'skip_crds=True' if CRDs are already installed, "
                                    f"or check for existing releases that might be managing these CRDs."
                                )
                    except Exception:
                        # If we can't check, provide generic CRD conflict message
                        error_msg = (
                            f"Installation failed: CRD conflict detected. "
                            f"The CustomResourceDefinitions required by this chart may already exist and be owned by another release. "
                            f"Consider using 'skip_crds=True' or checking if a release already exists in the namespace."
                        )
                    
                    await ctx.error(
                        error_msg,
                        extra={
                            'chart_name': chart_name,
                            'release_name': release_name,
                            'error': error_str,
                            'error_type': 'crd_conflict'
                        }
                    )
                    raise HelmOperationError(error_msg)
                
                # Generic error handling
                await ctx.error(
                    f"Installation failed: {error_str}",
                    extra={
                        'chart_name': chart_name,
                        'release_name': release_name,
                        'error': error_str
                    }
                )
                raise HelmOperationError(f'Installation failed: {error_str}')
        
        @mcp_instance.tool()
        async def helm_upgrade_release(
            release_name: str = Field(..., min_length=1, description='Release name to upgrade'),
            chart_name: str = Field(..., min_length=1, description='Chart name (can include version)'),
            namespace: str = Field(default='default', description='Kubernetes namespace'),
            values: dict = Field(default_factory=dict, description='Chart values dictionary (will be written to temp file)'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Upgrade an existing Helm release.
            
            Args:
                release_name: Release name to upgrade
                chart_name: Chart name (can include version)
                namespace: Kubernetes namespace
                values: Chart values dictionary (will be written to temp file and passed as -f)
            
            Returns:
                Upgrade result with status and details
            
            Raises:
                HelmOperationError: If upgrade fails
            """
            await ctx.info(
                f"Starting upgrade of release '{release_name}'",
                extra={
                    'release_name': release_name,
                    'chart_name': chart_name,
                    'namespace': namespace
                }
            )
            
            try:
                # Call service with parameters matching documentation
                result = await self.helm_service.upgrade_release(
                    release_name=release_name,
                    chart_name=chart_name,
                    namespace=namespace,
                    values=values,
                )
                
                await ctx.info(
                    f"Successfully upgraded release '{release_name}'",
                    extra={
                        'release_name': release_name,
                        'namespace': namespace
                    }
                )
                
                return result
            
            except Exception as e:
                await ctx.error(
                    f"Upgrade failed: {str(e)}",
                    extra={
                        'release_name': release_name,
                        'error': str(e)
                    }
                )
                raise HelmOperationError(f'Upgrade failed: {str(e)}')
        
        @mcp_instance.tool()
        async def helm_rollback_release(
            release_name: str = Field(..., min_length=1, description='Release name to rollback'),
            namespace: str = Field(default='default', description='Kubernetes namespace'),
            revision: Optional[int] = Field(default=None, description='Specific revision number (if None, rolls back to previous)'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Rollback a Helm release to a previous revision.
            
            Args:
                release_name: Release name to rollback
                namespace: Kubernetes namespace
                revision: Specific revision number (if None, rolls back to previous)
            
            Returns:
                Rollback result with status and details
            
            Raises:
                HelmOperationError: If rollback fails
            """
            await ctx.info(
                f"Starting rollback of release '{release_name}'",
                extra={
                    'release_name': release_name,
                    'namespace': namespace,
                    'revision': revision
                }
            )
            
            if revision:
                await ctx.debug( f"Rolling back to revision: {revision}")
            else:
                await ctx.debug( 'Rolling back to previous revision')
            
            try:
                result = await self.helm_service.rollback_release(
                    release_name=release_name,
                    namespace=namespace,
                    revision=revision,
                )
                
                await ctx.info(
                    f"Successfully rolled back release '{release_name}'",
                    extra={
                        'release_name': release_name,
                        'revision': revision
                    }
                )
                
                return result
            
            except Exception as e:
                await ctx.error(
                    f"Rollback failed: {str(e)}",
                    extra={
                        'release_name': release_name,
                        'error': str(e)
                    }
                )
                raise HelmOperationError(f'Rollback failed: {str(e)}')
        
        @mcp_instance.tool()
        async def helm_uninstall_release(
            release_name: str = Field(..., min_length=1, description='Release name to uninstall'),
            namespace: str = Field(default='default', description='Kubernetes namespace'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Uninstall a Helm release.
            
            Args:
                release_name: Release name to uninstall
                namespace: Kubernetes namespace
            
            Returns:
                Uninstall result with status
            
            Raises:
                HelmOperationError: If uninstall fails
            """
            await ctx.warning(
                f"Uninstalling release '{release_name}' from namespace '{namespace}'",
                extra={
                    'release_name': release_name,
                    'namespace': namespace
                }
            )
            
            await ctx.debug( 'This will delete all resources associated with the release')
            
            try:
                result = await self.helm_service.uninstall_release(
                    release_name=release_name,
                    namespace=namespace,
                )
                
                await ctx.info(
                    f"Successfully uninstalled release '{release_name}'",
                    extra={
                        'release_name': release_name,
                        'namespace': namespace
                    }
                )
                
                return result
            
            except Exception as e:
                await ctx.error(
                    f"Uninstall failed: {str(e)}",
                    extra={
                        'release_name': release_name,
                        'error': str(e)
                    }
                )
                raise HelmOperationError(f'Uninstall failed: {str(e)}')
        
        @mcp_instance.tool()
        async def helm_dry_run_install(
            chart_name: str = Field(..., min_length=1, description='Chart name (e.g., bitnami/postgresql)'),
            release_name: str = Field(..., min_length=1, description='Release name'),
            namespace: str = Field(default='default', description='Kubernetes namespace'),
            values: dict = Field(default_factory=dict, description='Chart values dictionary (will be written to temp file)'),
            skip_crds: bool = Field(default=False, description='Skip CRD installation (useful when CRDs already exist)'),
            extra_args: Optional[List[str]] = Field(default=None, description='Extra CLI flags to pass to helm install (e.g., --set-string)'),
            include_full: bool = Field(default=False, description='Include full Helm output (default: False to save tokens, only summary included)'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Perform a dry-run of Helm installation (preview without installing).
            
            By default, returns a summary to minimize token usage. Set include_full=True
            to get the complete Helm output with all chart templates.
            
            Args:
                chart_name: Chart name (e.g., 'bitnami/postgresql')
                release_name: Release name
                namespace: Kubernetes namespace
                values: Chart values dictionary (will be written to temp file and passed as -f)
                skip_crds: Skip CRD installation (useful when CRDs already exist)
                extra_args: Extra CLI flags to pass to helm install (e.g., --set-string)
                include_full: Include full Helm output (default: False to save tokens)
            
            Returns:
                Dictionary with:
                - summary: Key information about the dry-run (release info, chart metadata, notes)
                - full_output: Complete Helm output (only if include_full=True)
            
            Raises:
                HelmOperationError: If dry-run fails
            """
            await ctx.info(
                f"Performing dry-run installation of '{chart_name}'",
                extra={
                    'chart_name': chart_name,
                    'release_name': release_name,
                    'namespace': namespace
                }
            )
            
            await ctx.debug( 'Dry-run mode: No resources will be created')
            
            try:
                # Call service with parameters matching documentation, forcing dry_run=True
                result = await self.helm_service.install_chart(
                    chart_name=chart_name,
                    release_name=release_name,
                    namespace=namespace,
                    values=values,
                    dry_run=True,  # Force dry_run to True
                    skip_crds=skip_crds,
                    extra_args=extra_args,
                )
                
                # Extract essential information from the full output
                full_output = result.get('output', {})
                
                # Build summary with key information only
                chart_metadata = full_output.get('chart', {}).get('metadata', {}) if full_output.get('chart') else {}
                release_info = full_output.get('info', {}) if full_output.get('info') else {}
                notes = release_info.get('notes', '') if release_info else ''
                
                # Extract template count (without including template data)
                templates = full_output.get('chart', {}).get('templates', []) if full_output.get('chart') else []
                template_count = len(templates)
                template_names = [t.get('name', 'unknown') for t in templates[:10]]  # First 10 template names
                
                # Extract dependencies info
                dependencies = full_output.get('chart', {}).get('lock', {}).get('dependencies', []) if full_output.get('chart', {}).get('lock') else []
                
                summary = {
                    'release_name': release_name,
                    'namespace': namespace,
                    'chart_name': chart_metadata.get('name', chart_name),
                    'chart_version': chart_metadata.get('version', 'unknown'),
                    'app_version': chart_metadata.get('appVersion', 'unknown'),
                    'description': chart_metadata.get('description', ''),
                    'status': release_info.get('status', 'pending-install'),
                    'notes': notes[:500] + ('...' if len(notes) > 500 else ''),  # Truncate notes
                    'template_count': template_count,
                    'template_names': template_names + (['...'] if template_count > 10 else []),
                    'dependency_count': len(dependencies),
                    'dependencies': [
                        {'name': d.get('name'), 'version': d.get('version'), 'repository': d.get('repository')}
                        for d in dependencies[:5]  # First 5 dependencies
                    ] + (['...'] if len(dependencies) > 5 else []),
                    'dry_run': True
                }
                
                # Build response
                response = {
                    'status': 'success',
                    'summary': summary
                }
                
                # Include full output only if requested
                if include_full:
                    response['full_output'] = full_output
                else:
                    response['note'] = 'Full Helm output not included to save tokens. Set include_full=True to retrieve it.'
                
                await ctx.info(
                    f"Dry-run completed successfully for '{release_name}'",
                    extra={
                        'release_name': release_name,
                        'namespace': namespace,
                        'template_count': template_count,
                        'include_full': include_full
                    }
                )
                
                return response
            
            except Exception as e:
                await ctx.error(
                    f"Dry-run failed: {str(e)}",
                    extra={
                        'chart_name': chart_name,
                        'release_name': release_name,
                        'error': str(e)
                    }
                )
                raise HelmOperationError(f'Dry-run failed: {str(e)}')

