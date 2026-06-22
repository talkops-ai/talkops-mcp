"""SRE workflow prompt packs.

Provides guided multi-step prompts for common OpenTelemetry operations.
"""

from typing import Any, Dict

from fastmcp.prompts import Message

from opentelemetry_mcp_server.prompts.base import BasePrompt


class OnboardingPrompts(BasePrompt):
    """Service onboarding prompt pack."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.prompt(
            name="otel_onboard_service",
            description=(
                "Guided workflow for onboarding a new service to OpenTelemetry. "
                "Covers language detection, Instrumentation CR setup, annotation "
                "application, and verification."
            ),
        )
        async def otel_onboard_service(
            service_name: str,
            namespace: str,
            language: str,
        ) -> list[Message]:
            return [
                Message(
                    role="user",
                    content=(
                        f"I need to onboard the service '{service_name}' in namespace "
                        f"'{namespace}' to OpenTelemetry. It is written in {language}.\n\n"
                        "Please follow this workflow:\n"
                        f"1. Check instrumentation support: call otel_lookup_instrumentation "
                        f"with language='{language}'\n"
                        f"2. Check if an Instrumentation CR exists: read resource "
                        f"otel://instrumentation/{namespace}/default\n"
                        f"3. If no CR exists, create one: call otel_patch_instrumentation "
                        f"with namespace='{namespace}', name='default', dry_run=True\n"
                        f"4. After I approve, annotate the deployment: call "
                        f"otel_annotate_deployment "
                        f"with namespace='{namespace}', name='{service_name}', "
                        f"language='{language}', dry_run=True\n"
                        f"5. After I approve, verify: call otel_list_instrumented_services "
                        f"with namespace='{namespace}'\n\n"
                        "Show me the results at each step and wait for approval before mutating."
                    ),
                )
            ]


class InvestigationPrompts(BasePrompt):
    """Observability investigation prompt pack."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.prompt(
            name="otel_investigate_pipeline",
            description=(
                "Guided workflow for investigating an OTel pipeline. "
                "Validates processor ordering, filelog safety, sampling "
                "config, and enrichment profile."
            ),
        )
        async def otel_investigate_pipeline(
            collector_name: str,
            namespace: str,
        ) -> list[Message]:
            return [
                Message(
                    role="user",
                    content=(
                        f"I need to investigate the OTel collector '{collector_name}' "
                        f"in namespace '{namespace}'.\n\n"
                        "Please run this investigation workflow:\n"
                        f"1. Get collector details: call otel_get_collector with "
                        f"namespace='{namespace}', name='{collector_name}', detail_level='full'\n"
                        f"2. Validate processor ordering: call otel_validate_k8sattributes_order "
                        f"with namespace='{namespace}', name='{collector_name}'\n"
                        f"3. Check filelog safety: call otel_check_filelog_safety "
                        f"with namespace='{namespace}', name='{collector_name}'\n"
                        f"4. Inspect enrichment: read otel://k8s-enrichment/{namespace}/{collector_name}\n"
                        f"5. Inspect sampling: call otel_inspect_sampling_configuration "
                        f"with namespace='{namespace}', collector_name='{collector_name}'\n"
                        f"6. Check spanmetrics: read otel://spanmetrics/{namespace}/{collector_name}\n\n"
                        "Summarize all findings with a prioritized list of issues and recommendations."
                    ),
                )
            ]


class GovernancePrompts(BasePrompt):
    """Metric governance prompt pack."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.prompt(
            name="otel_cardinality_audit",
            description=(
                "Guided workflow for auditing metric cardinality. "
                "Detects high-cardinality dimensions and generates "
                "transform processor remediation YAML."
            ),
        )
        async def otel_cardinality_audit(
            collector_name: str,
            namespace: str,
        ) -> list[Message]:
            return [
                Message(
                    role="user",
                    content=(
                        f"I need to audit metric cardinality for collector '{collector_name}' "
                        f"in namespace '{namespace}'.\n\n"
                        "Please follow this workflow:\n"
                        f"1. Detect cardinality issues: call otel_detect_cardinality "
                        f"with namespace='{namespace}', name='{collector_name}'\n"
                        "2. For each issue found, explain the impact and severity\n"
                        "3. Generate remediation: call otel_gen_drop_attribute_rules "
                        "with the high-cardinality attributes\n"
                        f"4. Inspect spanmetrics: call otel_inspect_spanmetrics_config "
                        f"with namespace='{namespace}', name='{collector_name}'\n"
                        "5. Provide a complete remediation plan with the YAML patches to apply"
                    ),
                )
            ]


class SamplingPrompts(BasePrompt):
    """Sampling strategy prompt pack."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.prompt(
            name="otel_sampling_review",
            description=(
                "Guided workflow for reviewing and optimizing sampling "
                "strategy across Instrumentation CRDs and collector config."
            ),
        )
        async def otel_sampling_review(
            collector_name: str,
            namespace: str,
        ) -> list[Message]:
            return [
                Message(
                    role="user",
                    content=(
                        f"I need to review sampling for collector '{collector_name}' "
                        f"in namespace '{namespace}'.\n\n"
                        "Please follow this workflow:\n"
                        f"1. Inspect current sampling: call otel_inspect_sampling_configuration "
                        f"with namespace='{namespace}', collector_name='{collector_name}'\n"
                        f"2. Get collector details to understand pipeline topology: "
                        f"call otel_get_collector with namespace='{namespace}', name='{collector_name}'\n"
                        "3. Analyze and recommend:\n"
                        "   - If no sampling: recommend adding head sampling for cost optimization\n"
                        "   - If head only: check if tail sampling would better preserve important traces\n"
                        "   - If both head+tail: flag the conflict and recommend resolution\n"
                        "4. Generate config patches using otel_toggle_sampling_strategy with dry_run=True\n"
                        "5. Wait for my approval before suggesting to apply"
                    ),
                )
            ]


class SecurityPrompts(BasePrompt):
    """Security audit prompt pack."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.prompt(
            name="otel_security_audit",
            description=(
                "Guided workflow for auditing OTel security posture. "
                "Covers eBPF privileges, init containers, RBAC, and "
                "sensitive attribute exposure."
            ),
        )
        async def otel_security_audit(
            namespace: str,
        ) -> list[Message]:
            return [
                Message(
                    role="user",
                    content=(
                        f"I need to audit the OTel security posture in namespace '{namespace}'.\n\n"
                        "Please follow this workflow:\n"
                        f"1. Audit eBPF agents: call otel_analyze_ebpf_footprint "
                        f"with namespace='{namespace}'\n"
                        f"2. List all instrumented services: call otel_list_instrumented_services "
                        f"with namespace='{namespace}'\n"
                        f"3. List all collectors: call otel_list_collectors with namespace='{namespace}'\n"
                        "4. For each collector, check:\n"
                        "   - Pipeline config for sensitive attribute leaks\n"
                        "   - Enrichment profile for RBAC requirements\n"
                        "   - Target Allocator for scrape security\n"
                        "5. Provide a security report with:\n"
                        "   - Risk assessment (low/medium/high/critical)\n"
                        "   - Findings with evidence\n"
                        "   - Prioritized remediation steps"
                    ),
                )
            ]
