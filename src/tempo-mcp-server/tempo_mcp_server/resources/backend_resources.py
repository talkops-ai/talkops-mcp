"""Backend resources — dynamic backend listing."""

import json
from tempo_mcp_server.exceptions import TempoResourceError
from tempo_mcp_server.resources.base import BaseResource


class BackendResources(BaseResource):
    """Dynamic backend status resources."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        tempo_service = self.tempo_service

        @mcp_instance.resource(
            "tempo://system/backends",
            name="tempo_backends",
            description="All configured Tempo backends with health status",
            mime_type="application/json",
        )
        async def tempo_system_backends() -> str:
            try:
                backends = await tempo_service.list_backends()
                return json.dumps(backends, indent=2)
            except Exception as e:
                raise TempoResourceError(
                    f"Failed to list backends: {e}"
                ) from e

        @mcp_instance.resource(
            "tempo://system/backends/{backend_id}",
            name="tempo_backend_detail",
            description="Detailed profile for a specific Tempo backend",
            mime_type="application/json",
        )
        async def tempo_system_backend(backend_id: str) -> str:
            try:
                result = await tempo_service.get_backend_capabilities(backend_id)
                return json.dumps(result, indent=2)
            except Exception as e:
                raise TempoResourceError(
                    f"Failed to get backend '{backend_id}': {e}"
                ) from e

