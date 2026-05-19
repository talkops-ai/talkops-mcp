import asyncio
import os
import httpx
from httpx import AsyncClient

async def test_endpoints():
    token = os.environ.get("KARGO_STATIC_BEARER_TOKEN")
    project = "kargo-helm"
    stage = "dev"
    freight = "4e6cce658d9e327d1ca86493cb9ecd3eed3ac7b8"

    manifest = {
        "apiVersion": "kargo.akuity.io/v1alpha1",
        "kind": "Promotion",
        "metadata": {
            "name": f"{stage}-{freight[:7]}",
            "namespace": project,
        },
        "spec": {
            "stage": stage,
            "freight": freight,
        },
    }

    base_url = "https://127.0.0.1:31443"  # Try default kargo port
    if os.environ.get("KARGO_BASE_URL"):
        base_url = os.environ.get("KARGO_BASE_URL").replace("localhost", "127.0.0.1")
        
    # the server is actually running because the MCP is hitting it.
    # What URL is the MCP hitting?
    import sys
    sys.path.append(os.getcwd())
    from kargo_mcp_server.config import settings
    base_url = settings.kargo_api_url.replace("localhost", "127.0.0.1")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "text/plain",
    }

    path = f"/v1beta1/projects/{project}/resources"
    url = f"{base_url}{path}"
    
    async with AsyncClient(verify=False) as client:
        try:
            resp = await client.post(url, headers=headers, content=str(manifest))
            print(f"[POST] {path}: {resp.status_code}")
            print(f"Body: {resp.text[:200]}")
        except Exception as e:
            print(f"[POST] {path}: Error - {e}")

if __name__ == "__main__":
    asyncio.run(test_endpoints())
