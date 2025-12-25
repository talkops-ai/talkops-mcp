"""ArgoCD MCP resources for real-time data streams."""

import datetime
from typing import Dict, Any, Optional

from argocd_mcp_server.resources.base import BaseResource
from argocd_mcp_server.exceptions import ArgoCDOperationError, ApplicationNotFound


class ArgoCDResources(BaseResource):
    """All ArgoCD resources for live data streams."""
    
    def register(self, mcp_instance) -> None:
        """Register resources with FastMCP."""
        
        @mcp_instance.resource("argocd://applications/{cluster_name}")
        async def applications(cluster_name: str) -> str:
            """Real-time list of all applications and their state.
            
            Updated: Every 5 seconds
            Use case: Dashboard, monitoring, status checks
            
            Args:
                cluster_name: Target Kubernetes cluster
            
            Returns:
                JSON string with all applications and their current state
            """
            try:
                result = await self.argocd_service.list_applications(
                    cluster_name=cluster_name,
                    limit=100
                )
                
                # Transform to resource format
                apps_summary = []
                for app in result.get('applications', []):
                    apps_summary.append({
                        'name': app.get('name'),
                        'sync_status': app.get('sync_status'),
                        'health_status': app.get('health_status'),
                        'last_sync': app.get('last_sync_time')
                    })
                
                resource_data = {
                    'cluster_name': cluster_name,
                    'applications': apps_summary,
                    'total_count': result.get('total', 0),
                    'last_updated': datetime.datetime.utcnow().isoformat() + 'Z'
                }
                
                import json
                return json.dumps(resource_data, indent=2)
            except Exception as e:
                raise ArgoCDOperationError(f"Failed to get applications resource: {str(e)}")
        
        @mcp_instance.resource("argocd://application-metrics/{cluster_name}/{app_name}")
        async def application_metrics(cluster_name: str, app_name: str) -> str:
            """Real-time metrics for specific application.
            
            Updated: Every 10 seconds
            Use case: Monitoring, dashboards, auto-scaling triggers
            
            Args:
                cluster_name: Target Kubernetes cluster
                app_name: Application name
            
            Returns:
                JSON string with application metrics
            """
            try:
                app_details = await self.argocd_service.get_application_details(
                    cluster_name=cluster_name,
                    app_name=app_name
                )
                
                # Calculate metrics
                resources = app_details.get('resources', [])
                total_resources = len(resources)
                healthy_resources = len([r for r in resources if r.get('status') in ['Healthy', 'Synced']])
                
                metrics_data = {
                    'cluster_name': cluster_name,
                    'app_name': app_name,
                    'sync_status': app_details.get('sync_status'),
                    'health_status': app_details.get('health_status'),
                    'metrics': {
                        'total_resources': total_resources,
                        'healthy_resources': healthy_resources,
                        'sync_status': app_details.get('sync_status'),
                        'health_percentage': (healthy_resources / total_resources * 100) if total_resources > 0 else 0
                    },
                    'last_updated': datetime.datetime.utcnow().isoformat() + 'Z'
                }
                
                import json
                return json.dumps(metrics_data, indent=2)
            except ApplicationNotFound:
                raise
            except Exception as e:
                raise ArgoCDOperationError(f"Failed to get application metrics: {str(e)}")
        
        @mcp_instance.resource("argocd://sync-operations/{cluster_name}")
        async def sync_operations(cluster_name: str) -> str:
            """Currently running sync operations across all apps.
            
            Updated: Every 2 seconds
            Use case: Real-time operation monitoring
            
            Args:
                cluster_name: Target Kubernetes cluster
            
            Returns:
                JSON string with active sync operations
            """
            try:
                # Get all applications
                apps_result = await self.argocd_service.list_applications(
                    cluster_name=cluster_name,
                    limit=100
                )
                
                # Filter for apps that are currently syncing
                active_syncs = []
                for app in apps_result.get('applications', []):
                    if app.get('sync_status') in ['Syncing', 'OutOfSync']:
                        active_syncs.append({
                            'app_name': app.get('name'),
                            'status': app.get('sync_status'),
                            'health': app.get('health_status'),
                            'last_sync_time': app.get('last_sync_time')
                        })
                
                sync_ops_data = {
                    'cluster_name': cluster_name,
                    'active_operations': active_syncs,
                    'operation_count': len(active_syncs),
                    'last_updated': datetime.datetime.utcnow().isoformat() + 'Z'
                }
                
                import json
                return json.dumps(sync_ops_data, indent=2)
            except Exception as e:
                raise ArgoCDOperationError(f"Failed to get sync operations: {str(e)}")
        

        
        @mcp_instance.resource("argocd://deployment-events/{cluster_name}")
        async def deployment_events(cluster_name: str, app_name: Optional[str] = None) -> str:
            """Stream of deployment events (sync, rollback, etc).
            
            Updated: Real-time as events occur
            Use case: Event logging, audit trail, notifications
            
            Args:
                cluster_name: Target Kubernetes cluster
                app_name: Optional application name filter
            
            Returns:
                JSON string with recent deployment events
            """
            try:
                # If app_name is specified, get events for that app
                if app_name:
                    # Use dedicated events endpoint from new backend
                    raw_events = await self.argocd_service.get_application_events(
                        cluster_name=cluster_name,
                        app_name=app_name
                    )
                    
                    events = []
                    # Map K8s events to resource format
                    for event in raw_events:
                        events.append({
                            'app_name': app_name,
                            'event_type': event.get('type'), # Normal/Warning
                            'reason': event.get('reason'),
                            'message': event.get('message'),
                            'object': event.get('involvedObject', {}).get('kind'),
                            'timestamp': event.get('lastTimestamp') or event.get('firstTimestamp')
                        })
                    # Get events for all apps (simplified - just get app list and their current state)
                    apps_result = await self.argocd_service.list_applications(
                        cluster_name=cluster_name,
                        limit=50
                    )
                    
                    events = []
                    for app in apps_result.get('applications', []):
                        events.append({
                            'app_name': app.get('name'),
                            'event_type': 'status',
                            'sync_status': app.get('sync_status'),
                            'health_status': app.get('health_status'),
                            'timestamp': app.get('last_sync_time')
                        })
                
                events_data = {
                    'cluster_name': cluster_name,
                    'app_name': app_name,
                    'events': events,
                    'event_count': len(events),
                    'last_updated': datetime.datetime.utcnow().isoformat() + 'Z'
                }
                
                import json
                return json.dumps(events_data, indent=2)
            except ApplicationNotFound:
                raise
            except Exception as e:
                raise ArgoCDOperationError(f"Failed to get deployment events: {str(e)}")
        
        @mcp_instance.resource("argocd://cluster-health/{cluster_name}")
        async def cluster_health(cluster_name: str) -> str:
            """Overall cluster and ArgoCD health status.
            
            Updated: Every 30 seconds
            Use case: Health monitoring, readiness checks
            
            Args:
                cluster_name: Target Kubernetes cluster
            
            Returns:
                JSON string with cluster health information
            """
            try:
                # Get all applications to assess overall health
                apps_result = await self.argocd_service.list_applications(
                    cluster_name=cluster_name,
                    limit=100
                )
                
                apps = apps_result.get('applications', [])
                total_apps = len(apps)
                
                # Calculate health metrics
                synced_apps = len([a for a in apps if a.get('sync_status') == 'Synced'])
                healthy_apps = len([a for a in apps if a.get('health_status') == 'Healthy'])
                degraded_apps = len([a for a in apps if a.get('health_status') == 'Degraded'])
                outofsync_apps = len([a for a in apps if a.get('sync_status') == 'OutOfSync'])
                
                # Determine overall cluster health
                if total_apps == 0:
                    overall_health = 'Unknown'
                elif degraded_apps > 0 or outofsync_apps > total_apps * 0.5:
                    overall_health = 'Degraded'
                elif healthy_apps == total_apps and synced_apps == total_apps:
                    overall_health = 'Healthy'
                else:
                    overall_health = 'Warning'
                
                health_data = {
                    'cluster_name': cluster_name,
                    'overall_health': overall_health,
                    'metrics': {
                        'total_applications': total_apps,
                        'synced_applications': synced_apps,
                        'healthy_applications': healthy_apps,
                        'degraded_applications': degraded_apps,
                        'out_of_sync_applications': outofsync_apps,
                        'sync_percentage': (synced_apps / total_apps * 100) if total_apps > 0 else 0,
                        'health_percentage': (healthy_apps / total_apps * 100) if total_apps > 0 else 0
                    },
                    'last_updated': datetime.datetime.utcnow().isoformat() + 'Z'
                }
                
                import json
                return json.dumps(health_data, indent=2)
            except Exception as e:
                raise ArgoCDOperationError(f"Failed to get cluster health: {str(e)}")
