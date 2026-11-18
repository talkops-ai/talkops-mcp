"""Trace comparison tool."""

import re
from typing import Any, Dict, Optional

from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from tempo_mcp_server.exceptions.custom import (
    TempoOperationError,
    TempoValidationError,
)
from tempo_mcp_server.tools.base import BaseTool
from tempo_mcp_server.utils.trace_differ import diff_traces

_TRACE_ID_RE = re.compile(r"^[0-9a-fA-F]{16,32}$")


def _validate_trace_id(trace_id: str) -> str:
    """Validate and normalize a 16-32 char hex trace ID."""
    tid = trace_id.strip().lower()
    if not _TRACE_ID_RE.match(tid):
        raise TempoValidationError(
            f"Invalid trace ID: '{trace_id}'. Expected 16–32 character hex string."
        )
    return tid


class ComparisonTools(BaseTool):
    """Trace structural and timing comparison tools."""

    def register(self, mcp_instance: Any) -> None:
        if not self.should_register_tool("search", is_write=False):
            return

        tempo_service = self.tempo_service

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Compare Two Traces",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        async def tempo_compare_traces(
            backend_id: str = Field(..., min_length=1, description="Tempo backend ID"),
            trace_id_a: str = Field(
                ...,
                min_length=16,
                max_length=32,
                description="Baseline trace ID (16–32 hex chars)",
            ),
            trace_id_b: str = Field(
                ...,
                min_length=16,
                max_length=32,
                description="Comparison trace ID (16–32 hex chars)",
            ),
            max_spans: int = Field(
                default=500,
                ge=10,
                le=5000,
                description="Max spans per trace to compare",
            ),
            tenant: Optional[str] = Field(
                default=None,
                description="Tenant ID for multi-tenant backends",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Compute a 5-axis structural, span-count, timing, error, and attribute diff between two traces.

            Returns: {"trace_a": {...}, "trace_b": {...}, "structural_diff": {...}, "duration_diff": {...}, "error_diff": {...}}.
            When NOT to use: For single-trace inspection, call tempo_summarize_trace.
            """
            try:
                tid_a = _validate_trace_id(trace_id_a)
                tid_b = _validate_trace_id(trace_id_b)

                if tid_a == tid_b:
                    raise TempoValidationError(
                        "trace_id_a and trace_id_b must be different traces."
                    )

                if ctx:
                    await ctx.info(
                        f"Comparing traces {tid_a[:12]}... vs {tid_b[:12]}..."
                    )
                trace_a_data = await tempo_service.get_trace(
                    backend_id=backend_id,
                    trace_id=tid_a,
                    tenant=tenant,
                    max_spans=max_spans,
                    llm_format=False,
                )
                trace_b_data = await tempo_service.get_trace(
                    backend_id=backend_id,
                    trace_id=tid_b,
                    tenant=tenant,
                    max_spans=max_spans,
                    llm_format=False,
                )

                return diff_traces(
                    trace_a=trace_a_data.get("trace", {}),
                    trace_b=trace_b_data.get("trace", {}),
                    trace_id_a=tid_a,
                    trace_id_b=tid_b,
                )

            except (TempoValidationError, TempoOperationError):
                raise
            except Exception as e:
                self.handle_error(e, "tempo_compare_traces", backend_id=backend_id)
                raise
