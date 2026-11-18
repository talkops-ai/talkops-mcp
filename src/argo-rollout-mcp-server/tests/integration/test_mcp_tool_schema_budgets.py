"""In-memory MCP integration test verifying <= 8 parameters per tool and ToolAnnotations (T-I2)."""

import pytest
from fastmcp import Client
from tests.conftest import make_test_server


@pytest.mark.asyncio
async def test_every_tool_respects_eight_parameter_schema_budget(fake_argo_service, fake_generator_service):
    mcp = make_test_server(
        allow_write=True,
        toolsets=["all"],
        argo_service=fake_argo_service,
        generator_service=fake_generator_service,
    )
    async with Client(mcp) as client:
        tools = await client.list_tools()
        assert len(tools) == 15

        for tool in tools:
            schema = tool.inputSchema or {}
            props = schema.get("properties", {})
            assert len(props) <= 8, (
                f"Tool '{tool.name}' has {len(props)} parameters ({list(props.keys())}), exceeding the <= 8 budget"
            )
            assert tool.description and len(tool.description.strip()) > 10
            assert tool.annotations is not None
            assert tool.annotations.readOnlyHint is not None
            assert tool.annotations.destructiveHint is not None
