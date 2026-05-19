import pytest
from unittest.mock import MagicMock, patch, mock_open
from helm_mcp_server.core.tools.helm_handler import HelmHandler
from mcp.server.fastmcp import Context
from mcp.types import TextContent
from helm_mcp_server.models import InstallChartOutput, UpgradeReleaseOutput, ListReleasesOutput, UninstallReleaseOutput, SearchRepositoryOutput

@pytest.fixture
def mock_context():
    ctx = MagicMock(spec=Context)
    ctx.request_id = 'test-request-id'
    return ctx

@pytest.fixture
def mock_mcp():
    return MagicMock()

@pytest.mark.asyncio
async def test_install_chart_success(mock_context, mock_mcp):
    handler = HelmHandler(mock_mcp, allow_write=True)
    # Patch subprocess.run to simulate helm install
    with patch('subprocess.run') as mock_run, \
         patch('tempfile.NamedTemporaryFile', mock_open()):
        mock_run.return_value = MagicMock(stdout='Release deployed', returncode=0)
        result = await handler.install_chart(
            mock_context,
            release_name='test-release',
            chart='bitnami/nginx',
            values={'replicaCount': 2},
        )
        assert isinstance(result, InstallChartOutput)
        assert not result.isError
        assert result.status == 'deployed'
        assert 'deployed' in result.notes
        assert isinstance(result.content[0], TextContent)

@pytest.mark.asyncio
async def test_install_chart_error(mock_context, mock_mcp):
    handler = HelmHandler(mock_mcp, allow_write=True)
    # Patch subprocess.run to simulate helm install failure
    with patch('subprocess.run', side_effect=Exception('Helm error')):
        result = await handler.install_chart(
            mock_context,
            release_name='fail-release',
            chart='bitnami/nginx',
        )
        assert isinstance(result, InstallChartOutput)
        assert result.isError
        assert result.status == 'error'
        assert 'Helm error' in result.notes or 'Failed' in result.notes
        assert isinstance(result.content[0], TextContent)

@pytest.mark.asyncio
async def test_upgrade_release_success(mock_context, mock_mcp):
    handler = HelmHandler(mock_mcp, allow_write=True)
    with patch('subprocess.run') as mock_run, \
         patch('tempfile.NamedTemporaryFile', mock_open()):
        mock_run.return_value = MagicMock(stdout='Release upgraded', returncode=0)
        result = await handler.upgrade_release(
            mock_context,
            release_name='test-release',
            chart='bitnami/nginx',
            values={'replicaCount': 3},
        )
        assert isinstance(result, UpgradeReleaseOutput)
        assert not result.isError
        assert result.status == 'upgraded'
        assert 'upgraded' in result.notes
        assert isinstance(result.content[0], TextContent)

@pytest.mark.asyncio
async def test_upgrade_release_error(mock_context, mock_mcp):
    handler = HelmHandler(mock_mcp, allow_write=True)
    with patch('subprocess.run', side_effect=Exception('Helm upgrade error')):
        result = await handler.upgrade_release(
            mock_context,
            release_name='fail-release',
            chart='bitnami/nginx',
        )
        assert isinstance(result, UpgradeReleaseOutput)
        assert result.isError
        assert result.status == 'error'
        assert 'Helm upgrade error' in result.notes or 'Failed' in result.notes
        assert isinstance(result.content[0], TextContent)

@pytest.mark.asyncio
async def test_list_releases_success(mock_context, mock_mcp):
    handler = HelmHandler(mock_mcp)
    fake_release = {
        "name": "test-release",
        "chart": "nginx-1.0.0",
        "app_version": "1.0.0",
        "namespace": "default",
        "status": "deployed"
    }
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(stdout='[{"name": "test-release", "chart": "nginx-1.0.0", "app_version": "1.0.0", "namespace": "default", "status": "deployed"}]', returncode=0)
        result = await handler.list_releases(mock_context)
        assert isinstance(result, ListReleasesOutput)
        assert not result.isError
        assert result.count == 1
        assert result.releases[0].release_name == 'test-release'
        assert result.releases[0].status == 'deployed'
        assert isinstance(result.content[0], TextContent)

@pytest.mark.asyncio
async def test_list_releases_error(mock_context, mock_mcp):
    handler = HelmHandler(mock_mcp)
    with patch('subprocess.run', side_effect=Exception('Helm list error')):
        result = await handler.list_releases(mock_context)
        assert isinstance(result, ListReleasesOutput)
        assert result.isError
        assert result.count == 0
        assert isinstance(result.content[0], TextContent)
        assert 'Helm list error' in result.content[0].text or 'Failed' in result.content[0].text

@pytest.mark.asyncio
async def test_uninstall_release_success(mock_context, mock_mcp):
    handler = HelmHandler(mock_mcp, allow_write=True)
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(stdout='Release uninstalled', returncode=0)
        result = await handler.uninstall_release(
            mock_context,
            release_name='test-release',
        )
        assert isinstance(result, UninstallReleaseOutput)
        assert not result.isError
        assert result.status == 'uninstalled'
        assert 'uninstalled' in result.content[0].text

@pytest.mark.asyncio
async def test_uninstall_release_error(mock_context, mock_mcp):
    handler = HelmHandler(mock_mcp, allow_write=True)
    with patch('subprocess.run', side_effect=Exception('Helm uninstall error')):
        result = await handler.uninstall_release(
            mock_context,
            release_name='fail-release',
        )
        assert isinstance(result, UninstallReleaseOutput)
        assert result.isError
        assert result.status == 'error'
        assert 'Helm uninstall error' in result.content[0].text or 'Failed' in result.content[0].text

@pytest.mark.asyncio
async def test_search_repository_artifacthub_success(mock_context, mock_mcp):
    handler = HelmHandler(mock_mcp)
    fake_response = {
        "packages": [
            {
                "name": "nginx",
                "description": "Nginx chart",
                "version": "1.0.0",
                "repository": {"url": "https://charts.bitnami.com/bitnami", "name": "bitnami"},
                "home_url": "https://nginx.org",
                "logo_url": "https://logo.png",
                "keywords": ["web", "nginx"],
                "maintainers": [{"name": "Bitnami", "email": "containers@bitnami.com"}],
                "license": "Apache-2.0",
                "sources": ["https://github.com/bitnami/charts"],
                "category": "webserver",
                "app_version": "1.0.0",
                "operator": False,
                "category_prediction": None,
                "screenshots": [],
                "links": [],
                "crds": [],
            }
        ]
    }
    with patch('requests.get') as mock_get:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: fake_response)
        result = await handler.search_repository(
            mock_context,
            query='nginx',
            max_results=1,
        )
        assert isinstance(result, SearchRepositoryOutput)
        assert not result.isError
        assert result.count == 1
        assert result.results[0].name == 'nginx'
        assert result.results[0].repository == 'https://charts.bitnami.com/bitnami'
        assert isinstance(result.content[0], TextContent)

@pytest.mark.asyncio
async def test_search_repository_artifacthub_error(mock_context, mock_mcp):
    handler = HelmHandler(mock_mcp)
    with patch('requests.get', side_effect=Exception('ArtifactHub error')):
        result = await handler.search_repository(
            mock_context,
            query='nginx',
        )
        assert isinstance(result, SearchRepositoryOutput)
        assert result.isError
        assert result.count == 0
        assert isinstance(result.content[0], TextContent)
        assert 'ArtifactHub error' in result.content[0].text or 'Failed' in result.content[0].text 