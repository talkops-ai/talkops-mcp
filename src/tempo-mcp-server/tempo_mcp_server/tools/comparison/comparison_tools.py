"""Trace comparison tool.

Provides ``tempo_compare_traces`` — fetches two traces by ID and produces
a 5-dimensional structural diff (services, span counts, timing, errors,
attributes).
"""

from typing import Any, Dict, Optional

from mcp.types import ToolAnnotations
from fastmcp import Context
from pydantic import Field

from tempo_mcp_server.exceptions.custom import (
    TempoOperationError,
    TempoValidationError,
)
from tempo_mcp_server.tools.base import BaseTool
from tempo_mcp_server.utils.trace_differ import diff_traces

# Trace ID validation (32 hex chars)
_TRACE_ID_LEN = 32


def _validate_trace_id(trace_id: str) -> str:
    """Validate and normalize a trace ID."""
    tid = trace_id.strip().lower()
    if len(tid) != _TRACE_ID_LEN or not all(c in "0123456789abcdef" for c in tid):
        raise TempoValidationError(
            f"Invalid trace ID: '{trace_id}'. "
            f"Expected {_TRACE_ID_LEN}-character hex string."
        )
    return tid


class ComparisonTools(BaseTool):
    """Trace comparison tools."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

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
            backend_id: str = Field(
                ..., min_length=1, description="Tempo backend ID"
            ),
            trace_id_a: str = Field(
                ...,
                min_length=32,
                max_length=32,
                description=(
                    "Baseline trace ID (32-char hex). "
                    "This is the 'known good' trace."
                ),
            ),
            trace_id_b: str = Field(
                ...,
                min_length=32,
                max_length=32,
                description=(
                    "Comparison trace ID (32-char hex). "
                    "This is the 'problematic' trace."
                ),
            ),
            max_spans: int = Field(
                default=500,
                ge=10,
                le=5000,
                description=(
                    "Max spans per trace to compare. "
                    "Prevents OOM on very large traces."
                ),
            ),
            tenant: Optional[str] = Field(
                default=None,
                description="Tenant ID for multi-tenant backends",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Compare two traces and report structural + timing differences.

            Fetches both traces, builds span trees, and produces a
            multi-dimensional diff across 5 axes: structure (which
            services appear), span counts, timing, errors, and
            attributes. Read-only.

            Use this to understand regression between a known-good
            baseline trace and a problematic trace, or to compare
            request patterns across deployments.

            Returns:
            - {"trace_a": {...}, "trace_b": {...},
               "structural_diff": {...}, "span_count_diff": {...},
               "duration_diff": {...}, "error_diff": {...},
               "attribute_diff": {...}}

            When NOT to use: For analyzing a single trace, use
            tempo_summarize_trace.

            Common errors:
            - Trace not found: One or both traces may have expired
              beyond Tempo's retention window.
            - Large traces: Reduce max_spans if you get timeouts.
            """
            try:
                tid_a = _validate_trace_id(trace_id_a)
                tid_b = _validate_trace_id(trace_id_b)

                if tid_a == tid_b:
                    raise TempoValidationError(
                        "trace_id_a and trace_id_b must be different traces."
                    )

                # Fetch both traces
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

                # Compute diff
                result = diff_traces(
                    trace_a=trace_a_data.get("trace", {}),
                    trace_b=trace_b_data.get("trace", {}),
                    trace_id_a=tid_a,
                    trace_id_b=tid_b,
                )

                return result

            except (TempoValidationError, TempoOperationError):
                raise
            except Exception as e:
                raise TempoOperationError(
                    f"Failed to compare traces: {e}"
                )
