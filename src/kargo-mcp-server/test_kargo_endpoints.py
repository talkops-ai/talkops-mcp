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

    # The .env file has KARGO_BASE_URL="https://127.0.0.1:3187"
    base_url = "https://127.0.0.1:3187"
    
    headers = {
        "Authorization": f"Bearer {token}",
    }

    endpoints = [
        ("POST", "/v1beta1/resources", {"Content-Type": "text/plain"}),
        ("POST", "/v1beta1/projects/{project}/promotions", {"Content-Type": "application/json"}),
        ("POST", "/v1alpha1/namespaces/{project}/promotions", {"Content-Type": "application/json"}),
        ("POST", "/apis/kargo.akuity.io/v1alpha1/namespaces/{project}/promotions", {"Content-Type": "application/json"}),
    ]

    async with AsyncClient(verify=False) as client:
        for method, path, extra_headers in endpoints:
            url = f"{base_url}{path.format(project=project)}"
            req_headers = {**headers, **extra_headers}
            
            if extra_headers["Content-Type"] == "text/plain":
                data = {"content": str(manifest)}
                kwargs = {"content": str(manifest)}
            else:
                kwargs = {"json": manifest}
                
            try:
                resp = await client.request(method, url, headers=req_headers, **kwargs)
                print(f"[{method}] {path}: {resp.status_code}")
                # print(f"Body: {resp.text[:200]}")
            except Exception as e:
                print(f"[{method}] {path}: Error - {e}")

if __name__ == "__main__":
    asyncio.run(test_endpoints())
