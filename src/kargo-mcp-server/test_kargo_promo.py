import asyncio
import json
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

    async with httpx.AsyncClient(verify=False) as client:
        # Try native K8s API route via Kargo proxy
        url = f"https://localhost:31443/apis/kargo.akuity.io/v1alpha1/namespaces/{project}/promotions"
        resp = await client.post(
            url,
            json=manifest,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        )
        print(f"K8s API Path Status: {resp.status_code}")
        print(f"K8s API Path Body: {resp.text}")

if __name__ == "__main__":
    asyncio.run(test_kargo())
