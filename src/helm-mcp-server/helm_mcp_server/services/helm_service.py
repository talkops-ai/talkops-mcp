"""Helm operations service - business logic layer."""

import asyncio
import subprocess
import json
import tempfile
import os
import yaml
from typing import Optional, List, Dict, Any
from helm_mcp_server.config import ServerConfig
from helm_mcp_server.exceptions import HelmOperationError
from helm_mcp_server.utils.helm_helper import is_helm_installed, check_for_dangerous_patterns


class HelmService:
    """Service for Helm operations.
    
    Encapsulates all Helm CLI interactions and business logic.
    Can be used by multiple tools without duplication.
    """
    
    def __init__(self, config: ServerConfig):
        """Initialize with configuration."""
        self.config = config
    
    def _get_repository_url(self, repo_name: str) -> Optional[str]:
        """Get repository URL for common repositories.
        
        Args:
            repo_name: Repository name
        
        Returns:
            Repository URL if known, None otherwise
        """
        # Common Helm repository URLs
        known_repos = {
            'bitnami': 'https://charts.bitnami.com/bitnami',
            'argo': 'https://argoproj.github.io/argo-helm',
            'argoproj': 'https://argoproj.github.io/argo-helm',
            'prometheus-community': 'https://prometheus-community.github.io/helm-charts',
            'prometheus': 'https://prometheus-community.github.io/helm-charts',
            'stable': 'https://charts.helm.sh/stable',  # Deprecated but still common
            'grafana': 'https://grafana.github.io/helm-charts',
            'ingress-nginx': 'https://kubernetes.github.io/ingress-nginx',
            'nginx': 'https://kubernetes.github.io/ingress-nginx',
            'jetstack': 'https://charts.jetstack.io',  # cert-manager
            'cert-manager': 'https://charts.jetstack.io',
        }
        
        return known_repos.get(repo_name.lower())
    
    async def repository_exists(self, repo_name: str) -> bool:
        """Check if a Helm repository exists.
        
        Args:
            repo_name: Repository name
        
        Returns:
            True if repository exists, False otherwise
        """
        try:
            cmd = ['helm', 'repo', 'list', '-o', 'json']
            result = await self._run_helm_command(cmd)
            repos = json.loads(result) if result else []
            
            # Check if repository exists in the list
            for repo in repos:
                if repo.get('name', '').lower() == repo_name.lower():
                    return True
            
            return False
        except Exception:
            # If we can't list repos, assume it doesn't exist
            return False
    
    async def ensure_repository(self, repo_name: str, repo_url: Optional[str] = None) -> str:
        """Ensure a Helm repository exists, adding it if necessary.
        
        Args:
            repo_name: Repository name
            repo_url: Repository URL (if None, will try to get from known repos)
        
        Returns:
            Repository name that was used
        
        Raises:
            HelmOperationError: If repository cannot be added
        """
        # Check if repository already exists
        if await self.repository_exists(repo_name):
            return repo_name
        
        # Get repository URL if not provided
        if not repo_url:
            repo_url = self._get_repository_url(repo_name)
            if not repo_url:
                raise HelmOperationError(
                    f"Repository '{repo_name}' not found and no URL provided. "
                    f"Please provide a repository URL or use one of the known repositories: "
                    f"bitnami, argo, prometheus-community, grafana, ingress-nginx, jetstack"
                )
        
        # Add the repository
        return await self._add_repository(repo_url, repo_name)
    
    async def search_charts(
        self, 
        query: str, 
        repository: str = 'bitnami',
        limit: int = 10
    ) -> List[Dict[str, Any]] | str:
        """Search for Helm charts.
        
        Args:
            query: Chart name or keyword
            repository: Helm repository name
            limit: Maximum results
        
        Returns:
            List of chart metadata, or a message string if no charts found
        
        Raises:
            HelmOperationError: If search fails
        """
        try:
            # Ensure repository exists before searching
            await self.ensure_repository(repository)
            
            # Search without repository prefix to allow Helm's natural search behavior
            cmd = [
                'helm', 'search', 'repo',
                query,
                '--max-col-width', '80',
                '-o', 'json'
            ]
            
            result = await self._run_helm_command(cmd)
            charts = json.loads(result)
            
            # Filter by repository if specified
            if repository:
                charts = [
                    chart for chart in charts 
                    if chart.get('name', '').startswith(f'{repository}/')
                ]
            
            filtered_charts = charts[:limit]
            
            # Return message if no charts found
            if len(filtered_charts) == 0:
                return f"No charts found matching '{query}' in repository '{repository}'. Try running 'helm repo update' to refresh repository indexes or search without specifying a repository."
            
            return filtered_charts
        
        except HelmOperationError:
            # Re-raise HelmOperationError without wrapping
            raise
        except json.JSONDecodeError as e:
            raise HelmOperationError(f'Invalid Helm output: {str(e)}')
        except Exception as e:
            raise HelmOperationError(f'Search failed: {str(e)}')
    
    async def get_chart_readme(
        self,
        chart_name: str,
        repository: str = 'bitnami'
    ) -> str:
        """Get the README for a Helm chart.
        
        Args:
            chart_name: Chart name (can be in 'repo/chart' format or just 'chart')
            repository: Helm repository name (ignored if chart_name already includes repository)
        
        Returns:
            Chart README as markdown string
        
        Raises:
            HelmOperationError: If readme cannot be retrieved
        """
        try:
            # Ensure repository exists before getting readme
            await self.ensure_repository(repository)
            
            # If chart_name already contains repository (repo/chart format), use it directly
            # Otherwise, prepend the repository
            if '/' in chart_name:
                chart_ref = chart_name  # Already in repo/chart format
            else:
                chart_ref = f'{repository}/{chart_name}'
            
            cmd = [
                'helm', 'show', 'readme',
                chart_ref
            ]
            
            result = await self._run_helm_command(cmd)
            return result
        
        except HelmOperationError as e:
            # Check if it's a "chart not found" error and provide helpful context
            error_msg = str(e)
            if 'not found' in error_msg.lower() or 'no chart name found' in error_msg.lower():
                suggestions = []
                if 'try \'helm repo update\'' in error_msg.lower():
                    suggestions.append("Try running 'helm repo update' to refresh repository indexes")
                
                # Determine actual repository used
                if '/' in chart_name:
                    actual_repo = chart_name.split('/')[0]
                    suggestions.append(f"Chart '{chart_name}' may not exist in repository '{actual_repo}'")
                    suggestions.append(f"Try searching for the chart: helm search repo {chart_name}")
                else:
                    suggestions.append(f"Chart '{chart_name}' may not exist in repository '{repository}'")
                    suggestions.append(f"Try searching for the chart: helm search repo {repository}/{chart_name}")
                
                enhanced_msg = f"Chart README not found for '{chart_name}'. {'. '.join(suggestions)}"
                # Raise without chaining to avoid showing full stack trace
                raise HelmOperationError(enhanced_msg)
            # Re-raise other HelmOperationErrors without wrapping
            raise
        except Exception as e:
            raise HelmOperationError(f'Failed to get chart README: {str(e)}')
    
    async def get_chart_info(
        self, 
        chart_name: str,
        repository: str = 'bitnami'
    ) -> Dict[str, Any]:
        """Get detailed chart information."""
        try:
            # Ensure repository exists before getting chart info
            await self.ensure_repository(repository)
            
            # If chart_name already contains repository (repo/chart format), use it directly
            # Otherwise, prepend the repository
            if '/' in chart_name:
                chart_ref = chart_name  # Already in repo/chart format
            else:
                chart_ref = f'{repository}/{chart_name}'
            
            cmd = [
                'helm', 'show', 'chart',
                chart_ref
            ]
            
            result = await self._run_helm_command(cmd)
            # helm show chart outputs YAML, not JSON
            info = yaml.safe_load(result)
            return info
        
        except HelmOperationError as e:
            # Check if it's a "chart not found" error and provide helpful context
            error_msg = str(e)
            if 'not found' in error_msg.lower() or 'no chart name found' in error_msg.lower():
                suggestions = []
                if 'try \'helm repo update\'' in error_msg.lower():
                    suggestions.append("Try running 'helm repo update' to refresh repository indexes")
                
                # Determine actual repository used
                if '/' in chart_name:
                    actual_repo = chart_name.split('/')[0]
                    suggestions.append(f"Chart '{chart_name}' may not exist in repository '{actual_repo}'")
                    suggestions.append(f"Try searching for the chart: helm search repo {chart_name}")
                else:
                    suggestions.append(f"Chart '{chart_name}' may not exist in repository '{repository}'")
                    suggestions.append(f"Try searching for the chart: helm search repo {repository}/{chart_name}")
                
                enhanced_msg = f"Chart '{chart_name}' not found. {'. '.join(suggestions)}"
                # Raise without chaining to avoid showing full stack trace
                raise HelmOperationError(enhanced_msg)
            # Re-raise other HelmOperationErrors without wrapping
            raise
        except Exception as e:
            raise HelmOperationError(f'Failed to get chart info: {str(e)}')
            
    async def get_chart_values(
        self,
        chart_name: str,
        repository: str = 'bitnami',
        version: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get chart default values (schema)."""
        try:
            cmd = [
                'helm', 'show', 'values',
                f'{repository}/{chart_name}'
            ]
            
            if version:
                cmd.extend(['--version', version])
            
            result = await self._run_helm_command(cmd)
            values = yaml.safe_load(result)
            return values if values else {}
        
        except HelmOperationError as e:
            # Check if it's a "chart not found" error
            error_msg = str(e)
            if 'not found' in error_msg.lower() or 'no chart name found' in error_msg.lower():
                suggestions = []
                if 'try \'helm repo update\'' in error_msg.lower():
                    suggestions.append("Try running 'helm repo update' to refresh repository indexes")
                suggestions.append(f"Chart '{chart_name}' (version: {version or 'latest'}) may not exist in repository '{repository}'")
                
                enhanced_msg = f"Chart '{chart_name}' not found in repository '{repository}'. {'. '.join(suggestions)}"
                raise HelmOperationError(enhanced_msg)
            raise
        except Exception as e:
            raise HelmOperationError(f'Failed to get chart values: {str(e)}')
    
    def _check_helm_installed(self) -> None:
        """Check if Helm is installed.
        
        Raises:
            HelmOperationError: If Helm is not installed
        """
        if not is_helm_installed():
            raise HelmOperationError('Helm binary is not installed or not found in PATH.')
    
    def _check_dangerous_patterns(self, cmd: List[str], operation: str) -> None:
        """Check command for dangerous patterns.
        
        Args:
            cmd: Command and arguments to check
            operation: Operation name for logging (e.g., 'install_chart')
        
        Raises:
            HelmOperationError: If dangerous pattern detected
        """
        pattern = check_for_dangerous_patterns(cmd, log_prefix=f"[{operation}] ")
        if pattern:
            raise HelmOperationError(
                f"Dangerous pattern detected in command arguments: '{pattern}'. "
                f"Aborting {operation} for safety."
            )
    
    def _check_write_access(self, operation: str, allow_dry_run: bool = False, dry_run: bool = False) -> None:
        """Check if write operations are allowed.
        
        Args:
            operation: Operation name for error message
            allow_dry_run: Whether dry-run operations are allowed without write access
            dry_run: Whether this is a dry-run operation
        
        Raises:
            HelmOperationError: If write access is not allowed
        """
        if allow_dry_run and dry_run:
            # Dry-run operations don't need write access
            return
        
        if not self.config.allow_write:
            raise HelmOperationError(
                f"Helm {operation} is not allowed without write access. "
                f"Set MCP_ALLOW_WRITE=true or use dry_run=True."
            )
    
    def _normalize_chart_name(self, chart_name: str) -> str:
        """Normalize chart name to repo/chart format.
        
        Args:
            chart_name: Chart name (may be in format 'chart' or 'repo/chart')
        
        Returns:
            Normalized chart name in 'repo/chart' format
        
        Raises:
            HelmOperationError: If chart name cannot be normalized
        """
        # If already in repo/chart format, return as-is
        if '/' in chart_name:
            return chart_name
        
        # Common chart name patterns: try to infer repository
        # Map common chart names to their repository/chart format
        common_charts = {
            'argo-cd': 'argo/argo-cd',
            'argocd': 'argo/argo-cd',
            'postgresql': 'bitnami/postgresql',
            'postgres': 'bitnami/postgresql',
            'mysql': 'bitnami/mysql',
            'redis': 'bitnami/redis',
            'nginx': 'bitnami/nginx',
            'mongodb': 'bitnami/mongodb',
        }
        
        # Check if we have a mapping
        normalized = common_charts.get(chart_name.lower())
        if normalized:
            return normalized
        
        # If no mapping found, raise error with helpful message
        raise HelmOperationError(
            f"Chart name '{chart_name}' must be in format 'repo/chart' (e.g., 'argo/argo-cd', 'bitnami/postgresql'). "
            f"Common formats: 'argo/argo-cd', 'bitnami/postgresql', etc."
        )
    
    def _add_kubeconfig_flags(
        self,
        cmd: List[str],
        kubeconfig_path: Optional[str] = None,
        context_name: Optional[str] = None,
    ) -> None:
        """Add kubeconfig flags to command.
        
        Args:
            cmd: Command list to modify
            kubeconfig_path: Path to kubeconfig file
            context_name: Kubernetes context name
        """
        if kubeconfig_path:
            cmd.extend(['--kubeconfig', kubeconfig_path])
        if context_name:
            cmd.extend(['--kube-context', context_name])
    
    async def _add_repository(
        self,
        repo_url: str,
        repo_name: Optional[str] = None,
    ) -> str:
        """Add a Helm repository.
        
        Args:
            repo_url: Repository URL
            repo_name: Repository name (if None, extracted from URL or chart name)
        
        Returns:
            Repository name used
        
        Raises:
            HelmOperationError: If repository addition fails
        """
        if not repo_name:
            # Extract repo name from URL or use a default
            repo_name = repo_url.split('/')[-1].replace('.git', '').replace('https://', '').replace('http://', '')
            if not repo_name or repo_name == repo_url:
                repo_name = 'customrepo'
        
        try:
            # Add repository
            add_cmd = ['helm', 'repo', 'add', repo_name, repo_url]
            self._check_dangerous_patterns(add_cmd, 'add_repository')
            await self._run_helm_command(add_cmd)
            
            # Update repositories
            update_cmd = ['helm', 'repo', 'update']
            await self._run_helm_command(update_cmd)
            
            return repo_name
        except Exception as e:
            raise HelmOperationError(f'Failed to add/update repository: {str(e)}')
    
    def _add_values_files_to_cmd(
        self,
        cmd: List[str],
        values: Optional[Dict[str, Any]] = None,
        values_files: Optional[List[str]] = None,
        values_file_content: Optional[str] = None,
        temp_files: Optional[List[str]] = None,
    ) -> List[str]:
        """Add values files to command and return list of temp files created.
        
        Args:
            cmd: Command list to modify
            values: Values dictionary (will be written to temp file)
            values_files: List of values file paths/URLs
            values_file_content: Raw YAML content (will be written to temp file)
            temp_files: List to append temp file paths to
        
        Returns:
            List of temp files created (for cleanup)
        """
        if temp_files is None:
            temp_files = []
        
        # Handle raw YAML content as a temp file
        if values_file_content:
            with tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.yaml') as f:
                f.write(values_file_content)
                temp_files.append(f.name)
                cmd.extend(['-f', f.name])
        
        # Handle values dict as a temp YAML file
        if values:
            with tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.yaml') as f:
                yaml.dump(values, f)
                temp_files.append(f.name)
                cmd.extend(['-f', f.name])
        
        # Add any values files (paths or URLs)
        if values_files:
            for vf in values_files:
                cmd.extend(['-f', vf])
        
        return temp_files
    
    async def _run_helm_command(
        self,
        cmd: List[str],
        env: Optional[Dict[str, str]] = None,
    ) -> str:
        """Run Helm command with timeout.
        
        Args:
            cmd: Command and arguments
            env: Optional environment variables to set
        
        Returns:
            Command output
        
        Raises:
            HelmOperationError: If command fails
        """
        # Check if Helm is installed before running any command
        self._check_helm_installed()
        
        try:
            # Prepare environment
            process_env = os.environ.copy()
            if env:
                process_env.update(env)
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=process_env
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.config.helm.timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                raise HelmOperationError(
                    f'Helm command timeout ({self.config.helm.timeout}s)'
                )
            
            if process.returncode != 0:
                error_msg = stderr.decode().strip()
                raise HelmOperationError(error_msg)
            
            return stdout.decode().strip()
        
        except HelmOperationError:
            # Re-raise HelmOperationError without wrapping
            raise
        except Exception as e:
            raise HelmOperationError(f'Command execution failed: {str(e)}')
    
    async def install_chart(
        self,
        chart_name: str,
        release_name: str,
        namespace: str = 'default',
        values: Optional[Dict[str, Any]] = None,
        dry_run: bool = False,
        skip_crds: bool = False,
        extra_args: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Install a Helm chart.
        
        Args:
            chart_name: Chart name (e.g., 'bitnami/postgresql')
            release_name: Release name
            namespace: Kubernetes namespace
            values: Chart values dictionary (will be written to temp file)
            dry_run: Perform dry-run without installing
            skip_crds: Skip CRD installation (useful when CRDs already exist)
            extra_args: Extra CLI flags to pass to helm install (e.g., --set-string)
        
        Returns:
            Installation result with status and details
        
        Raises:
            HelmOperationError: If installation fails
        """
        # Safety check 1: Check if write operations are allowed (dry-run is allowed)
        self._check_write_access('install', allow_dry_run=True, dry_run=dry_run)
        
        temp_files = []
        try:
            # Normalize chart name to repo/chart format
            normalized_chart_name = self._normalize_chart_name(chart_name)
            cmd = ['helm', 'install', release_name, normalized_chart_name, '-n', namespace, '-o', 'json']
            
            if dry_run:
                cmd.append('--dry-run')
            
            if skip_crds:
                cmd.append('--skip-crds')
            
            # Add values files
            if values:
                temp_files = self._add_values_files_to_cmd(
                    cmd,
                    values=values,
                    values_files=None,
                    values_file_content=None,
                    temp_files=temp_files
                )
            
            # Add extra CLI args
            if extra_args:
                cmd.extend(extra_args)
            
            # Safety check 2: Check for dangerous patterns in command
            self._check_dangerous_patterns(cmd, f'install_chart[{release_name}]')
            
            result = await self._run_helm_command(cmd)
            full_output = json.loads(result) if result else {}
            
            # Extract essential information only to avoid context pollution
            # Similar to get_release_status, filter out large fields like manifest
            info = full_output.get('info', {})
            chart = full_output.get('chart', {})
            chart_metadata = chart.get('metadata', {}) if chart else {}
            
            # Create resource summary from manifest (if available)
            manifest = full_output.get('manifest', '')
            resource_summary = {}
            total_resources = 0
            if manifest:
                # Count resources by kind from manifest YAML
                try:
                    resources = yaml.safe_load_all(manifest)
                    for resource in resources:
                        if resource and isinstance(resource, dict):
                            kind = resource.get('kind', 'Unknown')
                            resource_summary[kind] = resource_summary.get(kind, 0) + 1
                            total_resources += 1
                except Exception:
                    # If parsing fails, just count approximate resources by "kind:" occurrences
                    total_resources = manifest.count('kind:')
            
            # Create hook summary
            hooks = full_output.get('hooks', [])
            hook_summary = {}
            if hooks:
                for hook in hooks:
                    hook_kind = hook.get('kind', 'Unknown')
                    hook_summary[hook_kind] = hook_summary.get(hook_kind, 0) + 1
            
            # Extract notes (limit length to avoid huge outputs)
            notes = info.get('notes', '')
            if notes and len(notes) > 500:
                notes = notes[:500] + '... (truncated)'
            
            # Extract template count (without including full template data)
            templates = chart.get('templates', []) if chart else []
            template_count = len(templates)
            # Keep only name field from templates to reduce size
            template_summary = [{'name': t.get('name', 'unknown')} for t in templates[:10]]  # First 10 templates
            
            # Extract dependencies info (limited)
            dependencies = chart.get('lock', {}).get('dependencies', []) if chart.get('lock') else []
            
            # Build filtered response with only essential fields
            # Maintain nested structure for compatibility with existing tools
            filtered_output = {
                'name': full_output.get('name'),
                'namespace': full_output.get('namespace'),
                'revision': full_output.get('revision'),
                'app_version': chart_metadata.get('appVersion') or full_output.get('app_version'),
                'first_deployed': full_output.get('first_deployed'),
                'last_deployed': full_output.get('last_deployed'),
                # Maintain nested 'info' structure for compatibility
                'info': {
                    'status': info.get('status', 'unknown'),
                    'description': info.get('description', ''),
                    'notes': notes if notes else None,
                },
                # Maintain nested 'chart' structure but filter out large fields
                'chart': {
                    'metadata': {
                        'name': chart_metadata.get('name'),
                        'version': chart_metadata.get('version'),
                        'appVersion': chart_metadata.get('appVersion') or full_output.get('app_version'),
                        'description': chart_metadata.get('description', ''),
                    },
                    # Include template names (limited) but not full template data
                    'templates': template_summary + (['...'] if template_count > 10 else []),
                    # Include limited dependencies info
                    'lock': {
                        'dependencies': [
                            {'name': d.get('name'), 'version': d.get('version'), 'repository': d.get('repository')}
                            for d in dependencies[:5]
                        ] + (['...'] if len(dependencies) > 5 else [])
                    } if dependencies else None,
                } if chart else None,
                # Add summary fields for easy access
                'resource_summary': resource_summary,
                'total_resources': total_resources,
                'hook_summary': hook_summary if hook_summary else None,
                'total_hooks': len(hooks) if hooks else 0,
                'template_count': template_count,
                'dependency_count': len(dependencies),
                # Explicitly exclude large fields
                # 'manifest' - excluded (use resource_summary instead)
                # 'hooks' - excluded (use hook_summary instead)
            }
            
            return {
                'status': 'success',
                'release_name': release_name,
                'namespace': namespace,
                'dry_run': dry_run,
                'output': filtered_output
            }
        
        except Exception as e:
            raise HelmOperationError(f'Chart installation failed: {str(e)}')
        finally:
            # Clean up temp files
            for tf in temp_files:
                try:
                    if os.path.exists(tf):
                        os.unlink(tf)
                except Exception:
                    pass
    
    async def upgrade_release(
        self,
        release_name: str,
        chart_name: str,
        namespace: str = 'default',
        values: Optional[Dict[str, Any]] = None,
        extra_args: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Upgrade a Helm release.
        
        Args:
            release_name: Release name to upgrade
            chart_name: Chart name (can include version)
            namespace: Kubernetes namespace
            values: Chart values dictionary (will be written to temp file)
            extra_args: Extra CLI flags to pass to helm upgrade (e.g., --version, --set-string)
        
        Returns:
            Upgrade result with status and details
        
        Raises:
            HelmOperationError: If upgrade fails
        """
        # Safety check 1: Check if write operations are allowed
        self._check_write_access('upgrade')
        
        temp_files = []
        try:
            # Normalize chart name to repo/chart format
            normalized_chart_name = self._normalize_chart_name(chart_name)
            cmd = ['helm', 'upgrade', release_name, normalized_chart_name, '-n', namespace, '-o', 'json']
            
            # Add values files
            if values:
                temp_files = self._add_values_files_to_cmd(
                    cmd,
                    values=values,
                    values_files=None,
                    values_file_content=None,
                    temp_files=temp_files
                )
            
            # Add extra CLI args
            if extra_args:
                cmd.extend(extra_args)
            
            # Safety check 2: Check for dangerous patterns in command
            self._check_dangerous_patterns(cmd, f'upgrade_release[{release_name}]')
            
            result = await self._run_helm_command(cmd)
            full_output = json.loads(result) if result else {}
            
            # Extract essential information only to avoid context pollution
            # Similar to install_chart, filter out large fields like manifest
            info = full_output.get('info', {})
            chart = full_output.get('chart', {})
            chart_metadata = chart.get('metadata', {}) if chart else {}
            
            # Create resource summary from manifest (if available)
            manifest = full_output.get('manifest', '')
            resource_summary = {}
            total_resources = 0
            if manifest:
                # Count resources by kind from manifest YAML
                try:
                    resources = yaml.safe_load_all(manifest)
                    for resource in resources:
                        if resource and isinstance(resource, dict):
                            kind = resource.get('kind', 'Unknown')
                            resource_summary[kind] = resource_summary.get(kind, 0) + 1
                            total_resources += 1
                except Exception:
                    # If parsing fails, just count approximate resources by "kind:" occurrences
                    total_resources = manifest.count('kind:')
            
            # Create hook summary
            hooks = full_output.get('hooks', [])
            hook_summary = {}
            if hooks:
                for hook in hooks:
                    hook_kind = hook.get('kind', 'Unknown')
                    hook_summary[hook_kind] = hook_summary.get(hook_kind, 0) + 1
            
            # Extract notes (limit length to avoid huge outputs)
            notes = info.get('notes', '')
            if notes and len(notes) > 500:
                notes = notes[:500] + '... (truncated)'
            
            # Extract template count (without including full template data)
            templates = chart.get('templates', []) if chart else []
            template_count = len(templates)
            # Keep only name field from templates to reduce size
            template_summary = [{'name': t.get('name', 'unknown')} for t in templates[:10]]  # First 10 templates
            
            # Extract dependencies info (limited)
            dependencies = chart.get('lock', {}).get('dependencies', []) if chart.get('lock') else []
            
            # Build filtered response with only essential fields
            # Maintain nested structure for compatibility with existing tools
            filtered_output = {
                'name': full_output.get('name'),
                'namespace': full_output.get('namespace'),
                'revision': full_output.get('revision'),
                'app_version': chart_metadata.get('appVersion') or full_output.get('app_version'),
                'first_deployed': full_output.get('first_deployed'),
                'last_deployed': full_output.get('last_deployed'),
                # Maintain nested 'info' structure for compatibility
                'info': {
                    'status': info.get('status', 'unknown'),
                    'description': info.get('description', ''),
                    'notes': notes if notes else None,
                },
                # Maintain nested 'chart' structure but filter out large fields
                'chart': {
                    'metadata': {
                        'name': chart_metadata.get('name'),
                        'version': chart_metadata.get('version'),
                        'appVersion': chart_metadata.get('appVersion') or full_output.get('app_version'),
                        'description': chart_metadata.get('description', ''),
                    },
                    # Include template names (limited) but not full template data
                    'templates': template_summary + (['...'] if template_count > 10 else []),
                    # Include limited dependencies info
                    'lock': {
                        'dependencies': [
                            {'name': d.get('name'), 'version': d.get('version'), 'repository': d.get('repository')}
                            for d in dependencies[:5]
                        ] + (['...'] if len(dependencies) > 5 else [])
                    } if dependencies else None,
                } if chart else None,
                # Add summary fields for easy access
                'resource_summary': resource_summary,
                'total_resources': total_resources,
                'hook_summary': hook_summary if hook_summary else None,
                'total_hooks': len(hooks) if hooks else 0,
                'template_count': template_count,
                'dependency_count': len(dependencies),
                # Explicitly exclude large fields
                # 'manifest' - excluded (use resource_summary instead)
                # 'hooks' - excluded (use hook_summary instead)
            }
            
            return {
                'status': 'success',
                'release_name': release_name,
                'namespace': namespace,
                'output': filtered_output
            }
        
        except Exception as e:
            raise HelmOperationError(f'Release upgrade failed: {str(e)}')
        finally:
            # Clean up temp files
            for tf in temp_files:
                try:
                    if os.path.exists(tf):
                        os.unlink(tf)
                except Exception:
                    pass
    
    async def rollback_release(
        self,
        release_name: str,
        namespace: str = 'default',
        revision: Optional[int] = None,
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
        # Safety check 1: Check if write operations are allowed
        self._check_write_access('rollback')
        
        try:
            cmd = ['helm', 'rollback', release_name, '-n', namespace]
            
            if revision:
                cmd.append(str(revision))
            
            # Safety check 2: Check for dangerous patterns in command
            self._check_dangerous_patterns(cmd, f'rollback_release[{release_name}]')
            
            result = await self._run_helm_command(cmd)
            # helm rollback outputs plain text, not JSON
            output = result.strip() if result else ''
            
            return {
                'status': 'success',
                'release_name': release_name,
                'namespace': namespace,
                'revision': revision,
                'message': output
            }
        
        except Exception as e:
            raise HelmOperationError(f'Release rollback failed: {str(e)}')
    
    async def uninstall_release(
        self,
        release_name: str,
        namespace: str = 'default',
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
        # Safety check 1: Check if write operations are allowed
        self._check_write_access('uninstall')
        
        try:
            cmd = ['helm', 'uninstall', release_name, '-n', namespace]
            
            # Safety check 2: Check for dangerous patterns in command
            self._check_dangerous_patterns(cmd, f'uninstall_release[{release_name}]')
            
            result = await self._run_helm_command(cmd)
            # helm uninstall outputs plain text, not JSON
            output = result.strip() if result else ''
            
            return {
                'status': 'success',
                'release_name': release_name,
                'namespace': namespace,
                'message': output
            }
        
        except Exception as e:
            raise HelmOperationError(f'Release uninstall failed: {str(e)}')
    
    async def render_manifests(
        self,
        chart_name: str,
        values: Optional[Dict[str, Any]] = None,
        values_files: Optional[List[str]] = None,
        values_file_content: Optional[str] = None,
        version: Optional[str] = None,
        namespace: str = 'default',
        kubeconfig_path: Optional[str] = None,
        context_name: Optional[str] = None,
        eks_cluster_name: Optional[str] = None,
    ) -> str:
        """Render Kubernetes manifests from Helm chart and values.
        
        Args:
            chart_name: Chart name (e.g., 'bitnami/postgresql')
            values: Chart values dictionary (will be written to temp file)
            values_files: List of values YAML files (paths or URLs) to use with -f
            values_file_content: Raw YAML content to use as a values file
            version: Specific chart version
            namespace: Kubernetes namespace
            kubeconfig_path: Path to kubeconfig file for multi-cluster support
            context_name: Kubeconfig context name for multi-cluster support
            eks_cluster_name: AWS EKS cluster name for multi-cluster support
        
        Returns:
            Rendered Kubernetes manifests as YAML string
        
        Raises:
            HelmOperationError: If rendering fails
        """
        temp_files = []
        try:
            # Normalize chart name to repo/chart format
            normalized_chart_name = self._normalize_chart_name(chart_name)
            cmd = ['helm', 'template', normalized_chart_name, '-n', namespace]
            
            if version:
                cmd.extend(['--version', version])
            
            # Add values files
            temp_files = self._add_values_files_to_cmd(
                cmd,
                values=values,
                values_files=values_files,
                values_file_content=values_file_content,
                temp_files=temp_files
            )
            
            # Add multi-cluster support flags
            self._add_kubeconfig_flags(cmd, kubeconfig_path, context_name)
            
            # Handle EKS cluster (set environment variable)
            env = None
            if eks_cluster_name:
                env = {'AWS_EKS_CLUSTER_NAME': eks_cluster_name}
            
            # Safety check: Check for dangerous patterns (read-only operation, no write check needed)
            self._check_dangerous_patterns(cmd, 'render_manifests')
            
            result = await self._run_helm_command(cmd, env=env)
            return result
        
        except Exception as e:
            raise HelmOperationError(f'Manifest rendering failed: {str(e)}')
        finally:
            # Clean up temp files
            for tf in temp_files:
                try:
                    if os.path.exists(tf):
                        os.unlink(tf)
                except Exception:
                    pass
    
    async def check_dependencies(
        self,
        chart_name: str,
        repository: str = 'bitnami',
    ) -> Dict[str, Any]:
        """Check if chart dependencies are available.
        
        Args:
            chart_name: Chart name (can be in 'repo/chart' format or just 'chart')
            repository: Helm repository name (ignored if chart_name already includes repository)
        
        Returns:
            Dependency check result with status
        
        Raises:
            HelmOperationError: If check fails
        """
        try:
            # Extract repository from chart_name if it's in repo/chart format
            # Otherwise use the provided repository parameter
            if '/' in chart_name:
                # Chart name already includes repository, extract it
                repo, chart = chart_name.split('/', 1)
                actual_repo = repo
            else:
                actual_repo = repository
            
            # Get chart info to check dependencies
            # get_chart_info will handle the repo/chart format correctly
            chart_info = await self.get_chart_info(chart_name, repository)
            
            dependencies = chart_info.get('dependencies', [])
            
            return {
                'status': 'success',
                'chart_name': chart_name,
                'repository': actual_repo,
                'dependencies': dependencies,
                'dependency_count': len(dependencies),
                'all_available': True  # Simplified - could check actual availability
            }
        
        except Exception as e:
            raise HelmOperationError(f'Dependency check failed: {str(e)}')
    
    async def get_installation_plan(
        self,
        chart_name: str,
        values: Optional[Dict[str, Any]] = None,
        namespace: str = 'default',
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
        try:
            # Normalize chart name to repo/chart format
            normalized_chart_name = self._normalize_chart_name(chart_name)
            # Render manifests to analyze resources
            manifests = await self.render_manifests(normalized_chart_name, values, namespace=namespace)
            
            # Parse manifests to extract resource information
            # This is a simplified version - could be enhanced with actual K8s resource parsing
            manifest_lines = manifests.split('\n')
            resource_count = sum(1 for line in manifest_lines if line.strip().startswith('kind:'))
            
            return {
                'status': 'success',
                'chart_name': chart_name,
                'namespace': namespace,
                'estimated_resources': resource_count,
                'manifests_preview': manifests[:500] if len(manifests) > 500 else manifests,
                'manifest_length': len(manifests)
            }
        
        except Exception as e:
            raise HelmOperationError(f'Installation plan generation failed: {str(e)}')
    
    async def release_exists(
        self,
        release_name: str,
        namespace: str = 'default',
    ) -> bool:
        """Check if a Helm release exists.
        
        Args:
            release_name: Release name
            namespace: Kubernetes namespace
        
        Returns:
            True if release exists, False otherwise
        """
        try:
            cmd = [
                'helm', 'status', release_name,
                '-n', namespace,
                '-o', 'json'
            ]
            
            await self._run_helm_command(cmd)
            return True
        
        except Exception:
            # Release doesn't exist or command failed
            return False
    
    async def list_releases_in_namespace(
        self,
        namespace: str = 'default',
    ) -> List[Dict[str, Any]]:
        """List all Helm releases in a namespace.
        
        Args:
            namespace: Kubernetes namespace
        
        Returns:
            List of release information dictionaries
        """
        try:
            cmd = ['helm', 'list', '-n', namespace, '-o', 'json', '--max', '10000']
            result = await self._run_helm_command(cmd)
            releases = json.loads(result) if result else []
            return releases
        except Exception:
            # If listing fails, return empty list
            return []
    
    async def get_release_status(
        self,
        release_name: str,
        namespace: str = 'default',
    ) -> Dict[str, Any]:
        """Get current status of a Helm release.
        
        Returns only essential information to avoid context pollution.
        Excludes large fields like manifest and full resource details.
        
        Args:
            release_name: Release name
            namespace: Kubernetes namespace
        
        Returns:
            Release status information with essential fields only
        
        Raises:
            HelmOperationError: If status retrieval fails
        """
        try:
            cmd = [
                'helm', 'status', release_name,
                '-n', namespace,
                '-o', 'json'
            ]
            
            result = await self._run_helm_command(cmd)
            full_status = json.loads(result) if result else {}
            
            # Extract essential information only
            info = full_status.get('info', {})
            
            # Resources are in info.resources as a dict: {"v1/ClusterRole": [resources...], ...}
            resources_dict = info.get('resources', {})
            resource_summary = {}
            resource_details = {}  # Store resource names grouped by kind
            max_resources_per_kind = 20  # Limit to avoid token bloat
            
            # Extract chart info from resource labels (they contain helm.sh/chart)
            chart_name = None
            chart_version = None
            app_version = None
            
            # Process resources - they're grouped by API version/kind
            total_resources = 0
            for resource_key, resource_list in resources_dict.items():
                if not isinstance(resource_list, list):
                    continue
                
                # Extract kind from key (e.g., "v1/ClusterRole" -> "ClusterRole")
                kind = resource_key.split('/')[-1] if '/' in resource_key else resource_key
                
                for resource in resource_list:
                    total_resources += 1
                    if not isinstance(resource, dict):
                        continue
                    
                    metadata = resource.get('metadata', {})
                    name = metadata.get('name', 'unknown')
                    resource_namespace = metadata.get('namespace', '')
                    labels = metadata.get('labels', {})
                    
                    # Extract chart info from first resource's labels
                    if not chart_name and labels:
                        chart_label = labels.get('helm.sh/chart', '')
                        if chart_label:
                            # Chart label format: "chart-name-version" (e.g., "argo-cd-9.2.4")
                            parts = chart_label.rsplit('-', 1)
                            if len(parts) == 2:
                                chart_name = parts[0]
                                chart_version = parts[1]
                        app_version = labels.get('app.kubernetes.io/version') or app_version
                    
                    # Count by kind
                    resource_summary[kind] = resource_summary.get(kind, 0) + 1
                    
                    # Store resource names (limited per kind)
                    if kind not in resource_details:
                        resource_details[kind] = []
                    
                    if len(resource_details[kind]) < max_resources_per_kind:
                        resource_info = {'name': name}
                        if resource_namespace and resource_namespace != full_status.get('namespace'):
                            resource_info['namespace'] = resource_namespace
                        resource_details[kind].append(resource_info)
            
            # Add truncation indicator if resources were limited
            for kind, count in resource_summary.items():
                if count > max_resources_per_kind and kind in resource_details:
                    resource_details[kind].append(f'... and {count - max_resources_per_kind} more')
            
            # Create hook summary with names
            hooks = full_status.get('hooks', [])
            hook_summary = {}
            hook_details = {}  # Store hook names grouped by kind
            max_hooks_per_kind = 10  # Limit hooks per kind
            
            if hooks:
                for hook in hooks:
                    hook_kind = hook.get('kind', 'Unknown')
                    hook_name = hook.get('name', 'unknown')
                    
                    # Count by kind
                    hook_summary[hook_kind] = hook_summary.get(hook_kind, 0) + 1
                    
                    # Store hook names (limited per kind)
                    if hook_kind not in hook_details:
                        hook_details[hook_kind] = []
                    
                    if len(hook_details[hook_kind]) < max_hooks_per_kind:
                        hook_details[hook_kind].append({'name': hook_name})
            
            # Add truncation indicator if hooks were limited
            for hook_kind, count in hook_summary.items():
                if count > max_hooks_per_kind and hook_kind in hook_details:
                    hook_details[hook_kind].append(f'... and {count - max_hooks_per_kind} more')
            
            # If chart info not found in resources, try to get it from helm list
            if not chart_name:
                try:
                    list_cmd = ['helm', 'list', '-n', namespace, '-o', 'json', '--max', '1', '--filter', release_name]
                    list_result = await self._run_helm_command(list_cmd)
                    list_data = json.loads(list_result) if list_result else []
                    releases = list_data if isinstance(list_data, list) else [list_data]
                    if releases and len(releases) > 0:
                        release_info = releases[0]
                        chart_full = release_info.get('chart', '')
                        if chart_full:
                            # Chart format: "chart-name-version" (e.g., "argo-cd-9.2.4")
                            parts = chart_full.rsplit('-', 1)
                            if len(parts) == 2:
                                chart_name = parts[0]
                                chart_version = parts[1]
                        app_version = release_info.get('app_version') or app_version
                except Exception:
                    # If helm list fails, continue without chart info
                    pass
            
            # Get revision history
            revision_history = []
            try:
                history_cmd = ['helm', 'history', release_name, '-n', namespace, '-o', 'json', '--max', '50']
                history_result = await self._run_helm_command(history_cmd)
                history_data = json.loads(history_result) if history_result else []
                revisions = history_data if isinstance(history_data, list) else [history_data]
                
                # Format revision history (limit to essential info)
                for rev in revisions:
                    revision_history.append({
                        'revision': rev.get('revision'),
                        'status': rev.get('status'),
                        'updated': rev.get('updated'),
                        'description': rev.get('description', ''),
                        'chart': rev.get('chart'),
                        'app_version': rev.get('app_version'),
                    })
            except Exception:
                # If history fails, continue without revision history
                pass
            
            # Extract notes (limit length to avoid huge outputs)
            notes = info.get('notes', '')
            if notes and len(notes) > 500:
                notes = notes[:500] + '... (truncated)'
            
            # Build filtered response with only essential fields
            filtered_status = {
                'name': full_status.get('name'),
                'namespace': full_status.get('namespace'),
                'revision': full_status.get('version'),  # 'version' is the revision number
                'status': info.get('status', 'unknown'),
                'chart': chart_name,
                'chart_version': chart_version,
                'app_version': app_version,
                'description': info.get('description', ''),
                'first_deployed': info.get('first_deployed'),
                'last_deployed': info.get('last_deployed'),
                'resource_summary': resource_summary,
                'resources': resource_details if resource_details else None,
                'total_resources': total_resources,
                'hook_summary': hook_summary if hook_summary else None,
                'hooks': hook_details if hook_details else None,
                'total_hooks': len(hooks) if hooks else 0,
                'notes': notes if notes else None,
                'revision_history': revision_history if revision_history else None,
                'total_revisions': len(revision_history) if revision_history else 0,
            }
            
            return {
                'status': 'success',
                'release_name': release_name,
                'namespace': namespace,
                'release_info': filtered_status
            }
        
        except Exception as e:
            raise HelmOperationError(f'Failed to get release status: {str(e)}')
    
    async def monitor_deployment_health(
        self,
        release_name: str,
        namespace: str = 'default',
        max_wait_seconds: int = 180,
        check_interval: int = 5,
    ) -> Dict[str, Any]:
        """Monitor deployment health asynchronously.
        
        Polls pod status until ready or timeout.
        
        Args:
            release_name: Release name to monitor
            namespace: Kubernetes namespace
            max_wait_seconds: Maximum time to wait for deployment to be ready
            check_interval: Interval between checks in seconds
        
        Returns:
            Monitoring result with deployment status
        
        Raises:
            HelmOperationError: If monitoring fails or timeout
        """
        try:
            import time
            from kubernetes import client, config as k8s_config
            
            # Load Kubernetes config
            def load_k8s_config():
                try:
                    k8s_config.load_incluster_config()
                except Exception:
                    k8s_config.load_kube_config()
                return client.CoreV1Api()
            
            # Run config loading in executor
            loop = asyncio.get_event_loop()
            v1 = await loop.run_in_executor(None, load_k8s_config)
            
            start_time = time.time()
            
            while time.time() - start_time < max_wait_seconds:
                # Get pods for this release - run in executor
                def get_pods(selector):
                    return v1.list_namespaced_pod(namespace, label_selector=selector)
                
                pods = await loop.run_in_executor(
                    None,
                    get_pods,
                    f'app.kubernetes.io/instance={release_name}'
                )
                
                if len(pods.items) == 0:
                    # Try alternative label selector
                    pods = await loop.run_in_executor(
                        None,
                        get_pods,
                        f'release={release_name}'
                    )
                
                if len(pods.items) > 0:
                    # Check if all pods are ready
                    ready_pods = sum(
                        1 for pod in pods.items
                        if pod.status.phase == 'Running' and
                        all(condition.status == 'True' and condition.type == 'Ready'
                            for condition in pod.status.conditions or [])
                    )
                    
                    all_ready = ready_pods == len(pods.items)
                    
                    if all_ready:
                        duration = int(time.time() - start_time)
                        return {
                            'status': 'ready',
                            'release_name': release_name,
                            'namespace': namespace,
                            'pod_count': len(pods.items),
                            'ready_pods': ready_pods,
                            'duration_seconds': duration
                        }
                
                # Wait before next check
                await asyncio.sleep(check_interval)
            
            # Timeout
            raise HelmOperationError(
                f'Deployment not ready after {max_wait_seconds}s'
            )
        
        except HelmOperationError:
            raise
        except Exception as e:
            raise HelmOperationError(f'Deployment monitoring failed: {str(e)}')

