"""Tests for KargoService HTTP client."""

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from kargo_mcp_server.config import AuthMode, KargoConfig, ServerConfig
from kargo_mcp_server.services.kargo_service import ApiError, KargoService


@pytest.fixture
def service() -> KargoService:
    """Create a KargoService with test config."""
    config = ServerConfig(
        kargo=KargoConfig(
            base_url="http://kargo-test:8080",
            auth_mode=AuthMode.ADMIN,
            admin_password="secret",
            timeout=5,
        )
    )
    return KargoService(config)


@pytest.fixture
def static_service() -> KargoService:
    """Create a KargoService with static token auth."""
    config = ServerConfig(
        kargo=KargoConfig(
            base_url="http://kargo-test:8080",
            auth_mode=AuthMode.STATIC,
            static_bearer_token="my-static-token",
            timeout=5,
        )
    )
    return KargoService(config)


class TestAdminLogin:
    @respx.mock
    @pytest.mark.asyncio
    async def test_admin_login_success(self, service: KargoService):
        """Admin login should cache the token."""
        respx.post("http://kargo-test:8080/v1beta1/login").respond(
            200, json={"idToken": "jwt-token-123"}
        )
        await service.ensure_admin_login()
        assert service._token == "jwt-token-123"

    @respx.mock
    @pytest.mark.asyncio
    async def test_admin_login_failure(self, service: KargoService):
        """Admin login failure should raise ApiError."""
        respx.post("http://kargo-test:8080/v1beta1/login").respond(401, text="Unauthorized")
        with pytest.raises(ApiError, match="401"):
            await service.ensure_admin_login()

    @pytest.mark.asyncio
    async def test_admin_login_missing_password(self):
        """Missing admin password should raise RuntimeError."""
        config = ServerConfig(
            kargo=KargoConfig(auth_mode=AuthMode.ADMIN, admin_password=None)
        )
        svc = KargoService(config)
        with pytest.raises(RuntimeError, match="KARGO_ADMIN_PASSWORD"):
            await svc.ensure_admin_login()


class TestHeaders:
    def test_admin_headers_with_token(self, service: KargoService):
        """Headers should include Bearer token when set."""
        service._token = "my-jwt"
        headers = service._headers()
        assert headers["Authorization"] == "Bearer my-jwt"

    def test_static_headers(self, static_service: KargoService):
        """Static mode should use the configured bearer token."""
        headers = static_service._headers()
        assert headers["Authorization"] == "Bearer my-static-token"

    def test_passthrough_override(self, service: KargoService):
        """Bearer override should take precedence."""
        service._token = "default-jwt"
        headers = service._headers(bearer_override="caller-token")
        assert headers["Authorization"] == "Bearer caller-token"


class TestParseJson:
    def test_parse_json_valid(self, service: KargoService):
        """_parse_json should return parsed dict for valid JSON."""
        resp = httpx.Response(200, json={"key": "value"})
        result = service._parse_json(resp, "test")
        assert result == {"key": "value"}

    def test_parse_json_empty_body(self, service: KargoService):
        """_parse_json should return empty dict for empty body."""
        resp = httpx.Response(200, content=b"")
        result = service._parse_json(resp, "test")
        assert result == {}

    def test_parse_json_invalid_body(self, service: KargoService):
        """_parse_json should raise ApiError with raw text for non-JSON body."""
        resp = httpx.Response(200, text="Not JSON at all")
        with pytest.raises(ApiError, match="Non-JSON response.*test"):
            service._parse_json(resp, "test")

    def test_parse_json_html_error_body(self, service: KargoService):
        """_parse_json should handle HTML error pages gracefully."""
        resp = httpx.Response(200, text="<html><body>502 Bad Gateway</body></html>")
        with pytest.raises(ApiError, match="Non-JSON response"):
            service._parse_json(resp, "create promotion")


class TestListProjects:
    @respx.mock
    @pytest.mark.asyncio
    async def test_list_projects(self, service: KargoService):
        """list_projects should return ProjectSummary list."""
        service._token = "jwt"
        respx.get("http://kargo-test:8080/v1beta1/projects").respond(
            200,
            json={
                "items": [
                    {
                        "apiVersion": "kargo.akuity.io/v1alpha1",
                        "kind": "Project",
                        "metadata": {"name": "demo"},
                        "spec": {},
                    }
                ]
            },
        )
        projects = await service.list_projects()
        assert len(projects) == 1
        assert projects[0].name == "demo"

    @respx.mock
    @pytest.mark.asyncio
    async def test_create_project(self, service: KargoService):
        service._token = "jwt"
        respx.post("http://kargo-test:8080/v1beta1/resources").respond(
            200,
            json={
                "results": [
                    {
                        "createdResourceManifest": {
                            "apiVersion": "kargo.akuity.io/v1alpha1",
                            "kind": "Project",
                            "metadata": {"name": "new-project"}
                        }
                    }
                ]
            }
        )
        proj = await service.create_project("new-project")
        assert proj.metadata.name == "new-project"

    @respx.mock
    @pytest.mark.asyncio
    async def test_delete_project(self, service: KargoService):
        service._token = "jwt"
        respx.delete("http://kargo-test:8080/v1beta1/projects/demo").respond(200)
        res = await service.delete_project("demo")
        assert "deleted successfully" in res["message"]


class TestListStages:
    @respx.mock
    @pytest.mark.asyncio
    async def test_list_stages_with_dag(self, service: KargoService):
        """list_stages should return StageSummary with topology."""
        service._token = "jwt"
        respx.get("http://kargo-test:8080/v1beta1/projects/demo/stages").respond(
            200,
            json={
                "items": [
                    {
                        "apiVersion": "kargo.akuity.io/v1alpha1",
                        "kind": "Stage",
                        "metadata": {"name": "dev", "namespace": "demo"},
                        "spec": {
                            "requestedFreight": [
                                {
                                    "origin": {"kind": "Warehouse", "name": "wh1"},
                                    "sources": {"direct": True}
                                }
                            ]
                        },
                    },
                    {
                        "apiVersion": "kargo.akuity.io/v1alpha1",
                        "kind": "Stage",
                        "metadata": {"name": "staging", "namespace": "demo"},
                        "spec": {
                            "requestedFreight": [
                                {
                                    "origin": {"kind": "Warehouse", "name": "wh1"},
                                    "sources": {"stages": ["dev"]}
                                }
                            ]
                        },
                    },
                ]
            },
        )
        stages = await service.list_stages("demo")
        assert len(stages) == 2
        staging = next(s for s in stages if s.name == "staging")
        assert "dev" in staging.upstream_stages


class TestApiError:
    @respx.mock
    @pytest.mark.asyncio
    async def test_404_raises_api_error(self, service: KargoService):
        """Non-2xx responses should raise ApiError."""
        service._token = "jwt"
        respx.get("http://kargo-test:8080/v1beta1/projects/missing").respond(
            404, text="Not Found"
        )
        with pytest.raises(ApiError, match="404"):
            await service.get_project("missing")


class TestPromotionService:
    @respx.mock
    @pytest.mark.asyncio
    async def test_create_promotion_with_inline_steps(self, service: KargoService):
        """create_promotion should work for stages with inline steps."""
        service._token = "jwt"

        # 1. Mock GET stage — returns inline steps (uses: git-clone, etc.)
        respx.get("http://kargo-test:8080/v1beta1/projects/demo/stages/dev").respond(
            200,
            json={
                "apiVersion": "kargo.akuity.io/v1alpha1",
                "kind": "Stage",
                "metadata": {"name": "dev", "namespace": "demo"},
                "spec": {
                    "promotionTemplate": {
                        "spec": {
                            "steps": [
                                {"uses": "git-clone", "config": {"repoURL": "https://github.com/org/repo.git"}},
                                {"uses": "git-push", "config": {"path": "./out"}},
                            ]
                        }
                    }
                },
            },
        )

        # 2. Mock POST /v1beta1/resources — returns the created Promotion CRD
        respx.post("http://kargo-test:8080/v1beta1/resources").respond(
            200,
            json={
                "results": [
                    {
                        "createdResourceManifest": {
                            "apiVersion": "kargo.akuity.io/v1alpha1",
                            "kind": "Promotion",
                            "metadata": {"name": "dev-freight", "namespace": "demo"},
                            "spec": {"stage": "dev", "freight": "freight-abc"},
                            "status": {"state": "Pending"},
                        }
                    }
                ]
            },
        )

        promotion = await service.create_promotion("demo", "dev", "freight-abc")
        assert promotion.metadata.name == "dev-freight"
        assert promotion.spec.stage == "dev"
        assert promotion.spec.freight == "freight-abc"

    @respx.mock
    @pytest.mark.asyncio
    async def test_create_promotion_api_error(self, service: KargoService):
        """create_promotion should raise ApiError when stage fetch fails."""
        service._token = "jwt"

        # Stage fetch returns 404
        respx.get("http://kargo-test:8080/v1beta1/projects/demo/stages/dev").respond(
            404, text="Not Found"
        )
        with pytest.raises(ApiError, match="404"):
            await service.create_promotion("demo", "dev", "bad-freight")

    @respx.mock
    @pytest.mark.asyncio
    async def test_create_promotion_with_task_inflation(self, service: KargoService):
        """create_promotion should inflate PromotionTask references into concrete steps."""
        service._token = "jwt"

        # 1. Mock GET stage — returns a PromotionTask reference (not inline steps)
        respx.get("http://kargo-test:8080/v1beta1/projects/demo/stages/dev").respond(
            200,
            json={
                "apiVersion": "kargo.akuity.io/v1alpha1",
                "kind": "Stage",
                "metadata": {"name": "dev", "namespace": "demo"},
                "spec": {
                    "promotionTemplate": {
                        "spec": {
                            "steps": [
                                {"task": {"name": "promote"}}
                            ]
                        }
                    }
                },
            },
        )

        # 2. Mock GET promotion task — returns the task with concrete steps
        respx.get("http://kargo-test:8080/v1beta1/projects/demo/promotiontasks/promote").respond(
            200,
            json={
                "apiVersion": "kargo.akuity.io/v1alpha1",
                "kind": "PromotionTask",
                "metadata": {"name": "promote", "namespace": "demo"},
                "spec": {
                    "steps": [
                        {"uses": "git-clone", "config": {"repoURL": "https://github.com/org/repo.git"}},
                        {"uses": "yaml-update", "as": "update-image", "config": {"path": "./out/values.yaml"}},
                        {"uses": "git-commit", "config": {"path": "./out"}},
                        {"uses": "git-push", "config": {"path": "./out"}},
                    ],
                    "vars": [{"name": "repoURL", "value": "https://github.com/org/repo.git"}],
                },
            },
        )

        # 3. Mock POST /v1beta1/resources — capture and return the Promotion
        respx.post("http://kargo-test:8080/v1beta1/resources").respond(
            200,
            json={
                "results": [
                    {
                        "createdResourceManifest": {
                            "apiVersion": "kargo.akuity.io/v1alpha1",
                            "kind": "Promotion",
                            "metadata": {"name": "dev-freight", "namespace": "demo"},
                            "spec": {"stage": "dev", "freight": "freight-abc"},
                            "status": {"state": "Pending"},
                        }
                    }
                ]
            },
        )

        promotion = await service.create_promotion("demo", "dev", "freight-abc")
        assert promotion.metadata.name == "dev-freight"
        assert promotion.spec.freight == "freight-abc"

        # Verify that the POST body contained the inflated steps (not the task ref)
        post_call = respx.calls[-1]
        import json as _json
        posted_body = _json.loads(post_call.request.content)
        posted_steps = posted_body["spec"]["steps"]
        assert len(posted_steps) == 4
        assert posted_steps[0]["uses"] == "git-clone"
        assert posted_steps[1]["uses"] == "yaml-update"
        assert posted_steps[2]["uses"] == "git-commit"
        assert posted_steps[3]["uses"] == "git-push"
        # Confirm the task reference was NOT passed through
        assert all("task" not in s for s in posted_steps)

    @respx.mock
    @pytest.mark.asyncio
    async def test_create_promotion_task_not_found(self, service: KargoService):
        """create_promotion should raise ApiError when a referenced PromotionTask doesn't exist."""
        service._token = "jwt"

        # 1. Mock GET stage — returns a PromotionTask reference
        respx.get("http://kargo-test:8080/v1beta1/projects/demo/stages/dev").respond(
            200,
            json={
                "apiVersion": "kargo.akuity.io/v1alpha1",
                "kind": "Stage",
                "metadata": {"name": "dev", "namespace": "demo"},
                "spec": {
                    "promotionTemplate": {
                        "spec": {
                            "steps": [
                                {"task": {"name": "nonexistent-task"}}
                            ]
                        }
                    }
                },
            },
        )

        # 2. Mock GET promotion task — returns 404
        respx.get("http://kargo-test:8080/v1beta1/projects/demo/promotiontasks/nonexistent-task").respond(
            404, text="Not Found"
        )

        with pytest.raises(ApiError, match="Cannot inflate PromotionTask 'nonexistent-task'"):
            await service.create_promotion("demo", "dev", "freight-abc")

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_promotions(self, service: KargoService):
        """list_promotions should extract Promotion objects from items array."""
        service._token = "jwt"
        respx.get("http://kargo-test:8080/v1beta1/projects/demo/promotions").respond(
            200,
            json={
                "items": [
                    {
                        "apiVersion": "kargo.akuity.io/v1alpha1",
                        "kind": "Promotion",
                        "metadata": {"name": "promo-001", "namespace": "demo"},
                        "spec": {"stage": "dev", "freight": "freight-abc"},
                        "status": {"state": "Succeeded"},
                    }
                ]
            },
        )
        promos = await service.list_promotions("demo")
        assert len(promos) == 1
        assert promos[0].name == "promo-001"
        assert promos[0].freight == "freight-abc"

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_promotions_without_kind(self, service: KargoService):
        """list_promotions should handle items that lack a 'kind' field."""
        service._token = "jwt"
        respx.get("http://kargo-test:8080/v1beta1/projects/demo/promotions").respond(
            200,
            json={
                "items": [
                    {
                        "metadata": {"name": "promo-002", "namespace": "demo"},
                        "spec": {"stage": "staging", "freight": "freight-xyz"},
                        "status": {"state": "Running"},
                    }
                ]
            },
        )
        promos = await service.list_promotions("demo")
        assert len(promos) == 1
        assert promos[0].name == "promo-002"
        assert promos[0].freight == "freight-xyz"
        assert promos[0].state == "Running"


class TestWarehouseService:
    @respx.mock
    @pytest.mark.asyncio
    async def test_upsert_warehouse(self, service: KargoService):
        service._token = "jwt"
        respx.put("http://kargo-test:8080/v1beta1/resources").respond(
            200,
            json={
                "results": [
                    {
                        "updatedResourceManifest": {
                            "apiVersion": "kargo.akuity.io/v1alpha1",
                            "kind": "Warehouse",
                            "metadata": {"name": "wh-test", "namespace": "demo"},
                            "spec": {"subscriptions": []}
                        }
                    }
                ]
            }
        )
        wh = await service.upsert_warehouse("demo", "wh-test", {"subscriptions": []})
        assert wh.metadata.name == "wh-test"
        assert wh.metadata.namespace == "demo"

class TestPromotionTaskService:
    @respx.mock
    @pytest.mark.asyncio
    async def test_list_promotion_tasks(self, service: KargoService):
        service._token = "jwt"
        respx.get("http://kargo-test:8080/v1beta1/projects/demo/promotiontasks").respond(
            200,
            json={
                "items": [
                    {
                        "apiVersion": "kargo.akuity.io/v1alpha1",
                        "kind": "PromotionTask",
                        "metadata": {"name": "promo-task-1"}
                    }
                ]
            }
        )
        tasks = await service.list_promotion_tasks("demo")
        assert len(tasks) == 1
        assert tasks[0]["metadata"]["name"] == "promo-task-1"

    @respx.mock
    @pytest.mark.asyncio
    async def test_upsert_promotion_task(self, service: KargoService):
        service._token = "jwt"
        respx.put("http://kargo-test:8080/v1beta1/resources").respond(
            200,
            json={
                "results": [
                    {
                        "createdResourceManifest": {
                            "apiVersion": "kargo.akuity.io/v1alpha1",
                            "kind": "PromotionTask",
                            "metadata": {"name": "task-test", "namespace": "demo"},
                            "spec": {"steps": []}
                        }
                    }
                ]
            }
        )
        task = await service.upsert_promotion_task("demo", "task-test", {"steps": []})
        assert task.metadata.name == "task-test"
        assert task.metadata.namespace == "demo"

class TestCredentialsService:
    @respx.mock
    @pytest.mark.asyncio
    async def test_list_repo_credentials(self, service: KargoService):
        service._token = "jwt"
        respx.get("http://kargo-test:8080/v1beta1/projects/demo/repo-credentials").respond(
            200,
            json={
                "items": [
                    {"metadata": {"name": "git-creds"}}
                ]
            }
        )
        creds = await service.list_repo_credentials("demo")
        assert len(creds) == 1
        assert creds[0]["metadata"]["name"] == "git-creds"

    @respx.mock
    @pytest.mark.asyncio
    async def test_create_repo_credentials(self, service: KargoService):
        from kargo_mcp_server.models.credentials import CreateRepoCredentialsRequest
        service._token = "jwt"
        respx.post("http://kargo-test:8080/v1beta1/projects/demo/repo-credentials").respond(
            200, json={"metadata": {"name": "new-creds"}}
        )
        req = CreateRepoCredentialsRequest(name="new-creds", repoUrl="https://github.com", type="git")
        cred = await service.create_repo_credentials("demo", req)
        assert cred["metadata"]["name"] == "new-creds"

    @respx.mock
    @pytest.mark.asyncio
    async def test_delete_repo_credentials(self, service: KargoService):
        service._token = "jwt"
        respx.delete("http://kargo-test:8080/v1beta1/projects/demo/repo-credentials/git-creds").respond(200)
        res = await service.delete_repo_credentials("demo", "git-creds")
        assert "deleted successfully" in res["message"]
