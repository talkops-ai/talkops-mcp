"""Unit tests for model-directed ToolError translation (T-U9)."""

from fastmcp.exceptions import ToolError
from kubernetes.client.rest import ApiException

from argo_rollout_mcp_server.exceptions.custom import (
    AnalysisTemplateError,
    RolloutNotFoundError,
    RolloutPromotionError,
    RolloutStrategyError,
)
from argo_rollout_mcp_server.tools.base import translate_error


def test_translates_not_found_with_discovery_guidance():
    err = translate_error(
        RolloutNotFoundError("Rollout 'missing' not found"),
        tool_name="argo_set_rollout_image",
        namespace="production",
        resource_name="missing",
    )
    assert isinstance(err, ToolError)
    assert "argorollout://rollouts/list" in str(err)


def test_translates_k8s_403_rbac_error():
    api_exc = ApiException(status=403, reason="Forbidden:rollouts.argoproj.io")
    err = translate_error(
        api_exc,
        tool_name="argo_create_rollout",
        namespace="production",
        resource_name="payments",
    )
    assert isinstance(err, ToolError)
    assert "RBAC permission denied" in str(err)


def test_translates_strategy_and_promotion_and_analysis_errors():
    s_err = translate_error(
        RolloutStrategyError("Both canary and blueGreen present"),
        tool_name="argo_configure_rollout_strategy",
        namespace="default",
        resource_name="demo",
    )
    assert "argo_diagnose_rollout" in str(s_err)

    p_err = translate_error(
        RolloutPromotionError("Cannot promote degraded rollout"),
        tool_name="argo_manage_rollout_lifecycle",
        namespace="default",
        resource_name="demo",
    )
    assert "argo_diagnose_rollout" in str(p_err)

    a_err = translate_error(
        AnalysisTemplateError("Missing metrics"),
        tool_name="argo_configure_analysis_template",
        namespace="default",
        resource_name="demo",
    )
    assert "argorollout://analysistemplates/default" in str(a_err)
