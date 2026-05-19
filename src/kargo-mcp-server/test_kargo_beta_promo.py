import asyncio
import os
import httpx

async def test_kargo():
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

    url = f"https://localhost:3187/v1beta1/projects/{project}/promotions"
    
    async with httpx.AsyncClient(verify=False) as client:
        resp = await client.post(
            url,
            json=manifest,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        )
        print(f"Status: {resp.status_code}")
        print(f"Body: {resp.text}")

if __name__ == "__main__":
    asyncio.run(test_kargo())
