"""Shared utility functions for testing /metrics endpoints.

Extracted from OnboardingTools to avoid cross-tool tight coupling.
"""

import httpx
from typing import List


async def test_metrics_endpoint(url: str) -> dict:
    """Test a /metrics endpoint for Prometheus compatibility.

    Args:
        url: The URL of the metrics endpoint to test

    Returns:
        Dictionary with ok, status_code, metrics_found, format, errors
    """
    errors: List[str] = []
    metrics: List[str] = []
    fmt = "unknown"

    try:
        async with httpx.AsyncClient(timeout=10, verify=False) as client:
            resp = await client.get(url)
            status = resp.status_code
            text = resp.text
            ctype = resp.headers.get("content-type", "")

            if "application/openmetrics-text" in ctype:
                fmt = "openmetrics"
            elif "text/plain" in ctype:
                fmt = "prometheus"
            else:
                errors.append(f"Unexpected Content-Type: {ctype}")

            for line in text.splitlines():
                if not line or line.startswith("#"):
                    continue
                name = line.split("{", 1)[0].split(" ", 1)[0]
                if name and name not in metrics:
                    metrics.append(name)

            ok = status == 200 and bool(metrics)
    except Exception as e:
        status = 0
        ok = False
        errors.append(str(e))

    return {
        "ok": ok,
        "status_code": status,
        "metrics_found": metrics[:50],  # Cap to avoid context overflow
        "format": fmt,
        "errors": errors,
    }
