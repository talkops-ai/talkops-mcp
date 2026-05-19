"""Tests for experiment specRef resolution logic in ArgoRolloutsService.

Verifies that create_experiment correctly resolves templates using 
specRef ("stable", "canary", "active", "preview") into full pod templates
by fetching the source Rollout's ReplicaSets.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from types import SimpleNamespace

from argo_rollout_mcp_server.services.argo_rollouts_service import ArgoRolloutsService
from argo_rollout_mcp_server.exceptions.custom import ArgoRolloutError

# --- Mock Data Helpers ---

def mock_rollout(strategy="canary", stable_hash="111", current_hash="222"):
    return {
        "metadata": {"name": "hello-world", "namespace": "default"},
        "spec": {
            "strategy": {strategy: {}},
            "selector": {"matchLabels": {"app": "hello-world"}}
        },
        "status": {
            "stableRS": stable_hash,
            "currentPodHash": current_hash
        }
    }

def mock_replicaset(name, labels=None):
    labels = labels or {"app": "hello-world", "pod-template-hash": name.split("-")[-1]}
    return {
        "metadata": {
            "name": name,
            "namespace": "default",
            "labels": labels
        },
        "spec": {
            "template": {
                "metadata": {"labels": labels},
                "spec": {
                    "containers": [{"name": "app", "image": "nginx:1.19.0"}]
                }
            }
        }
    }

# --- Fixture ---

@pytest.fixture
def argo_service():
    """Create an ArgoRolloutsService instance with mocked clients."""
    svc = ArgoRolloutsService.__new__(ArgoRolloutsService)
    # Bypass initialize() issues during tests
    svc._initialized = True
    svc._k8s_client = MagicMock()
    svc._dyn_client = MagicMock()
    
    # Mock specific APIs
    svc._rollout_api = MagicMock()
    svc._replicaset_api = MagicMock()
    svc._experiment_api = MagicMock()
    
    return svc

# --- Tests ---

class TestSpecRefResolution:
    
    @pytest.mark.asyncio
    async def test_stable_specref_resolved(self, argo_service):
        """specRef: 'stable' should resolve to stableRS template."""
        rollout_data = mock_rollout(stable_hash="stable-123", current_hash="canary-456")
        rs_data = mock_replicaset("hello-world-stable-123")
        
        # Mock get_rollout_manifest and RS get
        with patch.object(argo_service, "get_rollout_manifest", new_callable=AsyncMock) as mock_get_ro:
            mock_get_ro.return_value = rollout_data
            argo_service._replicaset_api.get.return_value = rs_data
            
            templates = [{"name": "baseline", "specRef": "stable"}]
            
            # The function to test
            resolved = await argo_service._resolve_spec_ref_templates(
                rollout_name="hello-world",
                rollout_namespace="default",
                templates=templates
            )
            
            # Assertions
            assert len(resolved) == 1
            t = resolved[0]
            assert "specRef" not in t
            assert t["name"] == "baseline"
            assert t["selector"]["matchLabels"]["app"] == "hello-world"
            assert t["selector"]["matchLabels"]["experiment-variant"] == "baseline"
            
            # Verify the mock calls
            argo_service._replicaset_api.get.assert_called_once_with(
                name="hello-world-stable-123", namespace="default"
            )

    @pytest.mark.asyncio
    async def test_canary_specref_resolved(self, argo_service):
        """specRef: 'canary' should resolve to currentPodHash template."""
        rollout_data = mock_rollout(stable_hash="stable-123", current_hash="canary-456")
        rs_data = mock_replicaset("hello-world-canary-456")
        
        with patch.object(argo_service, "get_rollout_manifest", new_callable=AsyncMock) as mock_get_ro:
            mock_get_ro.return_value = rollout_data
            argo_service._replicaset_api.get.return_value = rs_data
            
            templates = [{"name": "candidate", "specRef": "canary"}]
            
            resolved = await argo_service._resolve_spec_ref_templates(
                rollout_name="hello-world",
                rollout_namespace="default",
                templates=templates
            )
            
            assert len(resolved) == 1
            t = resolved[0]
            assert "specRef" not in t
            assert t["name"] == "candidate"
            
            argo_service._replicaset_api.get.assert_called_once_with(
                name="hello-world-canary-456", namespace="default"
            )

    @pytest.mark.asyncio
    async def test_active_preview_specref_resolved(self, argo_service):
        """specRef: 'active' and 'preview' behave the same for blue-green."""
        rollout_data = mock_rollout(strategy="blueGreen", stable_hash="active-123", current_hash="preview-456")
        
        def mock_rs_get(name, namespace):
            return mock_replicaset(name)
            
        with patch.object(argo_service, "get_rollout_manifest", new_callable=AsyncMock) as mock_get_ro:
            mock_get_ro.return_value = rollout_data
            argo_service._replicaset_api.get.side_effect = mock_rs_get
            
            templates = [
                {"name": "active-ver", "specRef": "active"},
                {"name": "preview-ver", "specRef": "preview"}
            ]
            
            resolved = await argo_service._resolve_spec_ref_templates(
                rollout_name="hello-world",
                rollout_namespace="default",
                templates=templates
            )
            
            assert len(resolved) == 2
            assert resolved[0]["name"] == "active-ver"
            assert resolved[1]["name"] == "preview-ver"
            
            # Active -> stable_hash
            argo_service._replicaset_api.get.assert_any_call(
                name="hello-world-active-123", namespace="default"
            )
            # Preview -> currentPodHash
            argo_service._replicaset_api.get.assert_any_call(
                name="hello-world-preview-456", namespace="default"
            )

    @pytest.mark.asyncio
    async def test_full_template_passthrough(self, argo_service):
        """Templates without specRef are passed through."""
        templates = [
            {
                "name": "custom",
                "selector": {"matchLabels": {"app": "custom"}},
                "template": {"spec": {"containers": [{"image": "custom:1"}]}}
            }
        ]
        
        # _resolve_spec_ref_templates should return it untouched, 
        # but it still fetches rollout to find matching labels for OTHER templates
        rollout_data = mock_rollout()
        with patch.object(argo_service, "get_rollout_manifest", new_callable=AsyncMock) as mock_get_ro:
            mock_get_ro.return_value = rollout_data
            
            resolved = await argo_service._resolve_spec_ref_templates(
                rollout_name="hello-world",
                rollout_namespace="default",
                templates=templates
            )
            
            assert len(resolved) == 1
            assert resolved[0] == templates[0]
            argo_service._replicaset_api.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_mixed_templates(self, argo_service):
        """Mix of specRef and full templates."""
        rollout_data = mock_rollout(stable_hash="stable-123", current_hash="canary-456")
        rs_data = mock_replicaset("hello-world-stable-123")
        
        with patch.object(argo_service, "get_rollout_manifest", new_callable=AsyncMock) as mock_get_ro:
            mock_get_ro.return_value = rollout_data
            argo_service._replicaset_api.get.return_value = rs_data
            
            templates = [
                {"name": "baseline", "specRef": "stable"},
                {"name": "custom", "template": {"spec": {"containers": [{"image": "custom:1"}]}}}
            ]
            
            resolved = await argo_service._resolve_spec_ref_templates(
                rollout_name="hello-world",
                rollout_namespace="default",
                templates=templates
            )
            
            assert len(resolved) == 2
            assert "specRef" not in resolved[0]
            assert "template" in resolved[0]
            assert resolved[1] == templates[1]

    @pytest.mark.asyncio
    async def test_create_experiment_catches_missing_rollout_name(self, argo_service):
        """create_experiment throws error if specRef is used without rollout_name."""
        templates = [{"name": "baseline", "specRef": "stable"}]
        
        with pytest.raises(ArgoRolloutError, match="rollout_name is required"):
            await argo_service.create_experiment(
                name="my-exp",
                templates=templates,
                rollout_name=None
            )

    @pytest.mark.asyncio
    async def test_no_canary_in_progress_error(self, argo_service):
        """If currentPodHash == stableRS, there is no canary in progress -> error."""
        # Both hashes the same
        rollout_data = mock_rollout(stable_hash="hash-123", current_hash="hash-123")
        
        with patch.object(argo_service, "get_rollout_manifest", new_callable=AsyncMock) as mock_get_ro:
            mock_get_ro.return_value = rollout_data
            
            templates = [{"name": "candidate", "specRef": "canary"}]
            
            with pytest.raises(ArgoRolloutError, match="requires a new deployment in progress"):
                await argo_service._resolve_spec_ref_templates(
                    rollout_name="hello-world",
                    rollout_namespace="default",
                    templates=templates
                )
