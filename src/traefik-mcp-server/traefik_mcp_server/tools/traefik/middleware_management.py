"""Traefik middleware tools - Middleware management for traffic policies."""

import json
from typing import Dict, Any, Optional, List, Literal, Union
from pydantic import Field
from fastmcp import Context
from mcp.types import ToolAnnotations

from traefik_mcp_server.tools.base import BaseTool
from traefik_mcp_server.exceptions.custom import (
    TraefikOperationError,
    TraefikMiddlewareError,
    TraefikCircuitBreakerError,
    TraefikMirroringError,
    TraefikRouteNotFoundError,
)


class MiddlewareTools(BaseTool):
    """Tools for creating and managing Traefik middleware."""

    def register(self, mcp_instance) -> None:
        """Register tools with FastMCP."""

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Manage Traefik Middleware",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def traefik_manage_middleware(
            action: Literal["create", "delete"] = Field(
                ...,
                description="Action: create (or update if exists) | delete",
            ),
            middleware_name: str = Field(
                ..., min_length=1, description="Middleware name"
            ),
            namespace: str = Field(
                default="default", description="Kubernetes namespace"
            ),
            middleware_type: Optional[Literal[
                "rate_limit",
                "circuit_breaker",
                "strip_prefix",
                "redirect_scheme",
                "inflight_req",
                "headers",
                "ip_allowlist",
                "ip_denylist",
                "forward_auth",
                "buffering",
                "replace_path",
                "replace_path_regex",
                "add_prefix",
            ]] = Field(
                default=None,
                description="Middleware primitive type. Required for action=create.",
            ),
            average: Optional[int] = Field(
                default=None,
                ge=1,
                le=10000,
                description="Average requests per period. Required for rate_limit.",
            ),
            burst: Optional[int] = Field(
                default=None,
                ge=1,
                le=20000,
                description="Maximum burst size. Required for rate_limit.",
            ),
            period: Optional[str] = Field(
                default=None,
                description='Time period (e.g., "1s", "1m"). Required for rate_limit.',
            ),
            trigger_type: Optional[str] = Field(
                default=None,
                description='Trigger: "error-rate", "latency", "network-error". Required for circuit_breaker.',
            ),
            threshold: Optional[float] = Field(
                default=None,
                ge=0.0,
                le=1e9,
                description="circuit_breaker: error-rate/network-error ratio (e.g. 0.3); latency: milliseconds (e.g. 100).",
            ),
            response_code: Optional[int] = Field(
                default=503,
                ge=400,
                le=599,
                description="HTTP status when circuit is open (e.g. 429, 503, 504). Use a different code than backend 503 to verify CB effect.",
            ),
            prefixes: Optional[List[str]] = Field(
                default=None,
                description="Prefixes for stripPrefix. For strip_prefix (use prefixes OR regex_patterns).",
            ),
            regex_patterns: Optional[List[str]] = Field(
                default=None,
                description="Regex for stripPrefixRegex. For strip_prefix (use prefixes OR regex_patterns).",
            ),
            force_slash: bool = Field(
                default=True,
                description="Force trailing slash. For strip_prefix.",
            ),
            traefik_version: str = Field(
                default="v3",
                description="Traefik API version. For strip_prefix.",
            ),
            redirect_permanent: bool = Field(
                default=True,
                description="redirect_scheme: permanent HTTPS redirect.",
            ),
            inflight_amount: Optional[int] = Field(
                default=None,
                ge=1,
                description="inflight_req: max concurrent requests (Traefik inFlightReq.amount).",
            ),
            access_control_allow_origin_list: Optional[List[str]] = Field(
                default=None,
                description="headers (CORS): allowed origins.",
            ),
            access_control_allow_methods: Optional[List[str]] = Field(
                default=None,
                description="headers (CORS): methods (comma-separated strings OK).",
            ),
            access_control_allow_headers: Optional[List[str]] = Field(
                default=None,
                description="headers (CORS): allowed request headers.",
            ),
            access_control_allow_credentials: Optional[bool] = Field(
                default=None,
                description="headers (CORS): allow credentials.",
            ),
            access_control_max_age: Optional[int] = Field(
                default=None,
                ge=0,
                description="headers (CORS): preflight max-age seconds.",
            ),
            access_control_expose_headers: Optional[List[str]] = Field(
                default=None,
                description="headers (CORS): exposed response headers.",
            ),
            headers_custom_request: Optional[Dict[str, str]] = Field(
                default=None,
                description="headers: custom request header map (customRequestHeaders).",
            ),
            headers_custom_response: Optional[Dict[str, str]] = Field(
                default=None,
                description="headers: custom response header map (customResponseHeaders).",
            ),
            source_ranges: Optional[List[str]] = Field(
                default=None,
                description="ip_allowlist / ip_denylist: CIDR list (or use source_ranges_csv).",
            ),
            source_ranges_csv: Optional[str] = Field(
                default=None,
                description="ip_allowlist / ip_denylist: comma-separated CIDRs.",
            ),
            forward_auth_address: Optional[str] = Field(
                default=None,
                description="forward_auth: auth service URL (required for forward_auth).",
            ),
            forward_auth_response_headers: Optional[List[str]] = Field(
                default=None,
                description="forward_auth: headers to copy from auth response.",
            ),
            forward_auth_trust_forward_header: bool = Field(
                default=True,
                description="forward_auth: trust X-Forwarded-* from client.",
            ),
            forward_auth_request_headers: Optional[List[str]] = Field(
                default=None,
                description="forward_auth: headers to forward to auth service.",
            ),
            max_request_body_bytes: Optional[int] = Field(
                default=None,
                ge=1,
                description="buffering: max request body bytes (required for buffering).",
            ),
            mem_request_body_bytes: Optional[int] = Field(
                default=None,
                ge=0,
                description="buffering: optional memRequestBodyBytes.",
            ),
            max_response_body_bytes: Optional[int] = Field(
                default=None,
                ge=0,
                description="buffering: optional maxResponseBodyBytes.",
            ),
            replace_path_value: Optional[str] = Field(
                default=None,
                description="replace_path: target path.",
            ),
            replace_path_regex_pattern: Optional[str] = Field(
                default=None,
                description="replace_path_regex: regex pattern.",
            ),
            replace_path_regex_replacement: Optional[str] = Field(
                default=None,
                description="replace_path_regex: replacement string.",
            ),
            add_prefix_value: Optional[str] = Field(
                default=None,
                description="add_prefix: path prefix to add (e.g. /api).",
            ),
            ctx: Optional[Context] = None,
        ) -> Union[Dict[str, Any], str]:
            """Create, update, or delete Traefik middleware resources.

            Unified CRUD for creating traffic policies (rate limits,
            circuit breakers, header manipulation, auth, etc.).

            **WARNING: May impact traffic access if applied incorrectly.**

            Args:
                middleware_type: Must match one of the literal values.

            Returns:
            - JSON dict with {"status": str, "middleware_name": str, ...}

            When NOT to use:
            - To attach middleware to a route → use traefik_manage_route_middlewares.
            """
            assert self.traefik_service is not None
            assert ctx is not None

            if action == "delete":
                await ctx.info(f"Deleting middleware '{middleware_name}'", extra={"middleware_name": middleware_name, "namespace": namespace})
                try:
                    result = await self.traefik_service.delete_middleware(
                        middleware_name=middleware_name,
                        namespace=namespace,
                    )
                    await ctx.info(result.get("message", "Middleware deleted"))
                    return result
                except TraefikMiddlewareError as e:
                    await ctx.error(str(e))
                    raise
                except Exception as e:
                    await ctx.error(str(e))
                    raise TraefikOperationError(f"Failed to delete middleware: {e}")

            # action=create
            if not middleware_type or not str(middleware_type).strip():
                raise ValueError("middleware_type is required for action=create")
            if middleware_type == "rate_limit":
                missing = []
                if average is None:
                    missing.append("average")
                if burst is None:
                    missing.append("burst")
                if period is None or not str(period).strip():
                    missing.append("period")
                if missing:
                    raise ValueError(
                        f"Missing required arguments for middleware_type='rate_limit': {', '.join(missing)}"
                    )
                avg = average or 100
                bst = burst or 200
                prd = period or "1s"
                await ctx.info(
                    f"Creating rate limiting middleware '{middleware_name}': {avg} req/{prd}, burst {bst}",
                    extra={
                        "middleware_name": middleware_name,
                        "namespace": namespace,
                        "average": avg,
                        "burst": bst,
                        "period": prd,
                    },
                )
                try:
                    result = await self.traefik_service.add_rate_limiting(
                        middleware_name=middleware_name,
                        namespace=namespace,
                        average=avg,
                        burst=bst,
                        period=prd,
                    )
                    await ctx.info(
                        f"Successfully created rate limiting middleware '{middleware_name}'",
                        extra={"middleware_name": middleware_name},
                    )
                    return result
                except TraefikMiddlewareError as e:
                    await ctx.error(f"Failed to create rate limiting: {str(e)}")
                    raise
                except Exception as e:
                    await ctx.error(
                        f"Failed to create rate limiting: {str(e)}",
                        extra={"middleware_name": middleware_name, "error": str(e)},
                    )
                    raise TraefikOperationError(
                        f"Rate limiting creation failed: {str(e)}"
                    )

            elif middleware_type == "circuit_breaker":
                missing = []
                if trigger_type is None or not str(trigger_type).strip():
                    missing.append("trigger_type")
                if threshold is None:
                    missing.append("threshold")
                if missing:
                    raise ValueError(
                        f"Missing required arguments for middleware_type='circuit_breaker': {', '.join(missing)}"
                    )
                trig = trigger_type or "error-rate"
                thresh = threshold if threshold is not None else 0.30
                valid_triggers = ["error-rate", "latency", "network-error"]
                if trig not in valid_triggers:
                    error_msg = f"Invalid trigger type '{trig}'. Must be one of: {', '.join(valid_triggers)}"
                    await ctx.error(error_msg)
                    raise TraefikCircuitBreakerError(error_msg)
                await ctx.info(
                    f"Creating circuit breaker middleware '{middleware_name}': {trig} > {thresh}",
                    extra={
                        "middleware_name": middleware_name,
                        "namespace": namespace,
                        "trigger_type": trig,
                        "threshold": thresh,
                    },
                )
                try:
                    result = await self.traefik_service.add_circuit_breaker(
                        middleware_name=middleware_name,
                        namespace=namespace,
                        trigger_type=trig,
                        threshold=thresh,
                        response_code=response_code if response_code is not None else 503,
                    )
                    await ctx.info(
                        f"Successfully created circuit breaker '{middleware_name}'",
                        extra={"middleware_name": middleware_name},
                    )
                    return result
                except TraefikCircuitBreakerError as e:
                    await ctx.error(f"Circuit breaker creation failed: {str(e)}")
                    raise
                except Exception as e:
                    await ctx.error(
                        f"Failed to create circuit breaker: {str(e)}",
                        extra={"middleware_name": middleware_name, "error": str(e)},
                    )
                    raise TraefikOperationError(
                        f"Circuit breaker creation failed: {str(e)}"
                    )

            elif middleware_type == "strip_prefix":
                has_prefixes = prefixes and len(prefixes) > 0
                has_regex = regex_patterns and len(regex_patterns) > 0
                if not has_prefixes and not has_regex:
                    raise ValueError(
                        "Missing required arguments for middleware_type='strip_prefix': "
                        "provide at least one of 'prefixes' or 'regex_patterns'"
                    )
                await ctx.info(
                    f"Creating strip prefix middleware '{middleware_name}' in cluster",
                    extra={
                        "middleware_name": middleware_name,
                        "namespace": namespace,
                    },
                )
                try:
                    result = await self.traefik_service.add_strip_prefix(
                        middleware_name=middleware_name,
                        namespace=namespace,
                        prefixes=prefixes if has_prefixes else None,
                        regex_patterns=regex_patterns if has_regex else None,
                        force_slash=force_slash,
                    )
                    await ctx.info(
                        f"Successfully created strip prefix middleware '{middleware_name}'",
                        extra={"middleware_name": middleware_name},
                    )
                    return result
                except TraefikMiddlewareError as e:
                    await ctx.error(str(e))
                    raise
                except Exception as e:
                    await ctx.error(f"Failed to create strip prefix middleware: {str(e)}")
                    raise TraefikOperationError(f"Strip prefix middleware creation failed: {e}")

            elif middleware_type == "redirect_scheme":
                await ctx.info(f"Upserting redirect_scheme middleware '{middleware_name}'")
                try:
                    return await self.traefik_service.add_redirect_scheme(
                        middleware_name=middleware_name,
                        namespace=namespace,
                        permanent=redirect_permanent,
                    )
                except TraefikMiddlewareError as e:
                    await ctx.error(str(e))
                    raise
                except Exception as e:
                    raise TraefikOperationError(f"redirect_scheme failed: {e}")

            elif middleware_type == "inflight_req":
                if inflight_amount is None:
                    raise ValueError(
                        "Missing required arguments for middleware_type='inflight_req': inflight_amount"
                    )
                await ctx.info(f"Upserting inflight_req middleware '{middleware_name}'")
                try:
                    return await self.traefik_service.add_inflight_req(
                        middleware_name=middleware_name,
                        namespace=namespace,
                        amount=inflight_amount,
                    )
                except TraefikMiddlewareError as e:
                    await ctx.error(str(e))
                    raise
                except Exception as e:
                    raise TraefikOperationError(f"inflight_req failed: {e}")

            elif middleware_type == "headers":
                has_cors = any(
                    [
                        access_control_allow_origin_list,
                        access_control_allow_methods,
                        access_control_allow_headers,
                        access_control_allow_credentials is not None,
                        access_control_max_age is not None,
                        access_control_expose_headers,
                    ]
                )
                has_custom = bool(headers_custom_request or headers_custom_response)
                if not has_cors and not has_custom:
                    raise ValueError(
                        "middleware_type='headers' requires at least one CORS field "
                        "(e.g. access_control_allow_origin_list) and/or "
                        "headers_custom_request / headers_custom_response"
                    )
                await ctx.info(f"Upserting headers middleware '{middleware_name}'")
                try:
                    return await self.traefik_service.add_headers_middleware(
                        middleware_name=middleware_name,
                        namespace=namespace,
                        access_control_allow_origin_list=access_control_allow_origin_list,
                        access_control_allow_methods=access_control_allow_methods,
                        access_control_allow_headers=access_control_allow_headers,
                        access_control_allow_credentials=access_control_allow_credentials,
                        access_control_max_age=access_control_max_age,
                        access_control_expose_headers=access_control_expose_headers,
                        custom_request_headers=headers_custom_request,
                        custom_response_headers=headers_custom_response,
                    )
                except TraefikMiddlewareError as e:
                    await ctx.error(str(e))
                    raise
                except Exception as e:
                    raise TraefikOperationError(f"headers middleware failed: {e}")

            elif middleware_type == "ip_allowlist":
                if not (source_ranges or (source_ranges_csv and source_ranges_csv.strip())):
                    raise ValueError(
                        "middleware_type='ip_allowlist' requires source_ranges or source_ranges_csv"
                    )
                try:
                    return await self.traefik_service.add_ip_allowlist(
                        middleware_name=middleware_name,
                        namespace=namespace,
                        source_ranges=source_ranges,
                        source_ranges_csv=source_ranges_csv,
                    )
                except TraefikMiddlewareError as e:
                    await ctx.error(str(e))
                    raise
                except Exception as e:
                    raise TraefikOperationError(f"ip_allowlist failed: {e}")

            elif middleware_type == "ip_denylist":
                if not (source_ranges or (source_ranges_csv and source_ranges_csv.strip())):
                    raise ValueError(
                        "middleware_type='ip_denylist' requires source_ranges or source_ranges_csv"
                    )
                try:
                    return await self.traefik_service.add_ip_denylist(
                        middleware_name=middleware_name,
                        namespace=namespace,
                        source_ranges=source_ranges,
                        source_ranges_csv=source_ranges_csv,
                    )
                except TraefikMiddlewareError as e:
                    await ctx.error(str(e))
                    raise
                except Exception as e:
                    raise TraefikOperationError(f"ip_denylist failed: {e}")

            elif middleware_type == "forward_auth":
                if not forward_auth_address or not str(forward_auth_address).strip():
                    raise ValueError(
                        "middleware_type='forward_auth' requires forward_auth_address"
                    )
                try:
                    return await self.traefik_service.add_forward_auth(
                        middleware_name=middleware_name,
                        namespace=namespace,
                        address=forward_auth_address.strip(),
                        auth_response_headers=forward_auth_response_headers,
                        trust_forward_header=forward_auth_trust_forward_header,
                        auth_request_headers=forward_auth_request_headers,
                    )
                except TraefikMiddlewareError as e:
                    await ctx.error(str(e))
                    raise
                except Exception as e:
                    raise TraefikOperationError(f"forward_auth failed: {e}")

            elif middleware_type == "buffering":
                if max_request_body_bytes is None:
                    raise ValueError(
                        "middleware_type='buffering' requires max_request_body_bytes"
                    )
                try:
                    return await self.traefik_service.add_buffering(
                        middleware_name=middleware_name,
                        namespace=namespace,
                        max_request_body_bytes=max_request_body_bytes,
                        mem_request_body_bytes=mem_request_body_bytes,
                        max_response_body_bytes=max_response_body_bytes,
                    )
                except TraefikMiddlewareError as e:
                    await ctx.error(str(e))
                    raise
                except Exception as e:
                    raise TraefikOperationError(f"buffering failed: {e}")

            elif middleware_type == "replace_path":
                if not replace_path_value or not str(replace_path_value).strip():
                    raise ValueError(
                        "middleware_type='replace_path' requires replace_path_value"
                    )
                try:
                    return await self.traefik_service.add_replace_path(
                        middleware_name=middleware_name,
                        namespace=namespace,
                        path=replace_path_value.strip(),
                    )
                except TraefikMiddlewareError as e:
                    await ctx.error(str(e))
                    raise
                except Exception as e:
                    raise TraefikOperationError(f"replace_path failed: {e}")

            elif middleware_type == "replace_path_regex":
                if not replace_path_regex_pattern or not str(
                    replace_path_regex_pattern
                ).strip():
                    raise ValueError(
                        "middleware_type='replace_path_regex' requires "
                        "replace_path_regex_pattern"
                    )
                try:
                    return await self.traefik_service.add_replace_path_regex(
                        middleware_name=middleware_name,
                        namespace=namespace,
                        regex=replace_path_regex_pattern.strip(),
                        replacement=(
                            replace_path_regex_replacement
                            if replace_path_regex_replacement is not None
                            else ""
                        ),
                    )
                except TraefikMiddlewareError as e:
                    await ctx.error(str(e))
                    raise
                except Exception as e:
                    raise TraefikOperationError(f"replace_path_regex failed: {e}")

            elif middleware_type == "add_prefix":
                if not add_prefix_value or not str(add_prefix_value).strip():
                    raise ValueError(
                        "middleware_type='add_prefix' requires add_prefix_value"
                    )
                try:
                    return await self.traefik_service.add_prefix_middleware(
                        middleware_name=middleware_name,
                        namespace=namespace,
                        prefix=add_prefix_value.strip(),
                    )
                except TraefikMiddlewareError as e:
                    await ctx.error(str(e))
                    raise
                except Exception as e:
                    raise TraefikOperationError(f"add_prefix failed: {e}")

            else:
                raise ValueError(f"Unknown middleware_type: {middleware_type!r}")

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Manage Traffic Mirroring",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def traefik_manage_traffic_mirroring(
            action: Literal["enable", "disable", "update"] = Field(
                ...,
                description="enable: create mirror TraefikService | disable: delete mirror | update: change mirror_percent (0-100)",
            ),
            route_name: str = Field(..., min_length=1, description="Route / IngressRoute name"),
            namespace: str = Field(default="default", description="Kubernetes namespace"),
            main_service: Optional[str] = Field(
                default=None,
                description="enable only: main service (default {route_name}-stable)",
            ),
            mirror_service: Optional[str] = Field(
                default=None,
                description="enable only: mirror target (default {route_name}-staging)",
            ),
            mirror_percent: int = Field(
                default=20,
                ge=0,
                le=100,
                description="enable: mirror % (1-100 typical). update: new % (0 disables). Ignored for disable.",
            ),
            attach_to_ingress: bool = Field(
                default=False,
                description="enable only: patch IngressRoute to point at {route_name}-mirror (disables live WRR split)",
            ),
            restore_ingress_to_wrr: bool = Field(
                default=False,
                description="disable only: repoint IngressRoute to {route_name}-wrr before deleting mirror",
            ),
            ctx: Optional[Context] = None,
        ) -> Dict[str, Any]:
            """Enable, update, or disable Traefik traffic mirroring.

            Shadow copy a percentage of traffic to a mirror service for
            testing without affecting real users.

            Actions:
            - enable: creates mirror TraefikService.
            - update: change mirror_percent.
            - disable: deletes mirror.

            **WARNING: Attaching to an IngressRoute replaces live WRR split.**

            Returns:
            - JSON dict with {"status": str, ...}

            When NOT to use:
            - For active canary deployments → use traefik_manage_weighted_routing.
            """
            assert self.traefik_service is not None
            assert ctx is not None

            if action == "enable":
                if mirror_percent < 1:
                    raise ValueError("action=enable requires mirror_percent between 1 and 100")
                await ctx.info(
                    f"Enabling traffic mirroring for route '{route_name}': {mirror_percent}% to mirror",
                    extra={
                        "route_name": route_name,
                        "namespace": namespace,
                        "mirror_percent": mirror_percent,
                        "main_service": main_service,
                        "mirror_service": mirror_service,
                        "attach_to_ingress": attach_to_ingress,
                    },
                )
                try:
                    result = await self.traefik_service.enable_traffic_mirroring(
                        route_name=route_name,
                        namespace=namespace,
                        main_service=main_service,
                        mirror_service=mirror_service,
                        mirror_percent=mirror_percent,
                    )
                    try:
                        ir_info = await self.traefik_service.inspect_route(route_name, namespace)
                        active_backends = ir_info.get("ingress_route", {}).get("active_backends", [])
                        if active_backends:
                            current_backend = active_backends[0].get("name")
                            result["current_ingress_backend"] = current_backend
                            if current_backend != f"{route_name}-mirror":
                                result["status"] = "created_but_inactive"
                    except Exception:
                        pass

                    result["warning"] = (
                        f"Repointing an existing weighted IngressRoute (like '*-wrr') to '{route_name}-mirror' "
                        "REPLACES split routing. Real users will only receive responses from the main service. "
                        "Canary nodes will receive traffic, but their responses to the user are completely DISCARDED."
                    )
                    if attach_to_ingress:
                        try:
                            ir_obj = self.traefik_service._ingressroute_api.get(
                                name=route_name, namespace=namespace
                            )
                            ir_dict = ir_obj.to_dict() if hasattr(ir_obj, "to_dict") else ir_obj
                            routes_spec = ir_dict.get("spec", {}).get("routes", [])

                            changed = False
                            for r in routes_spec:
                                if "services" in r:
                                    r["services"] = [
                                        {"name": f"{route_name}-mirror", "kind": "TraefikService"}
                                    ]
                                    changed = True

                            if changed:
                                self.traefik_service._ingressroute_api.patch(
                                    name=route_name,
                                    namespace=namespace,
                                    body={"spec": {"routes": routes_spec}},
                                    content_type="application/merge-patch+json",
                                )
                                result["status"] = "created_and_active"
                                result["current_ingress_backend"] = f"{route_name}-mirror"
                                result["next_steps"] = (
                                    f"IngressRoute '{route_name}' was automatically updated to point to "
                                    f"'{route_name}-mirror' active sink."
                                )
                                await ctx.info(
                                    f"Automatically attached IngressRoute '{route_name}' to mirror "
                                    f"service '{route_name}-mirror'"
                                )
                        except Exception as e:
                            result["attach_error"] = str(e)
                            result["next_steps"] = (
                                f"Auto-attach failed ({e}). To activate manually, update IngressRoute "
                                f"`services[0].name` to '{route_name}-mirror'."
                            )
                    else:
                        result["next_steps"] = (
                            f"To activate the mirror, update your IngressRoute so its `services[0].name` "
                            f"points strictly to '{route_name}-mirror'."
                        )

                    await ctx.info(
                        f"Successfully enabled traffic mirroring for '{route_name}'",
                        extra={
                            "route_name": route_name,
                            "mirror_percent": mirror_percent,
                            "mirror_service": result.get("mirror_service"),
                        },
                    )
                    return result
                except TraefikMirroringError as e:
                    await ctx.error(f"Failed to enable traffic mirroring: {str(e)}")
                    raise
                except Exception as e:
                    await ctx.error(
                        f"Failed to enable traffic mirroring: {str(e)}",
                        extra={"route_name": route_name, "error": str(e)},
                    )
                    raise TraefikOperationError(f"Traffic mirroring configuration failed: {str(e)}")

            if action == "disable":
                await ctx.info(f"Disabling traffic mirroring for route '{route_name}'")

                restore_status = None
                if restore_ingress_to_wrr:
                    try:
                        ir_obj = self.traefik_service._ingressroute_api.get(
                            name=route_name, namespace=namespace
                        )
                        ir_dict = ir_obj.to_dict() if hasattr(ir_obj, "to_dict") else ir_obj
                        routes_spec = ir_dict.get("spec", {}).get("routes", [])

                        changed = False
                        for r in routes_spec:
                            if "services" in r:
                                r["services"] = [
                                    {"name": f"{route_name}-wrr", "kind": "TraefikService"}
                                ]
                                changed = True

                        if changed:
                            self.traefik_service._ingressroute_api.patch(
                                name=route_name,
                                namespace=namespace,
                                body={"spec": {"routes": routes_spec}},
                                content_type="application/merge-patch+json",
                            )
                            restore_status = (
                                f"IngressRoute '{route_name}' was automatically restored to '{route_name}-wrr'."
                            )
                            await ctx.info(restore_status)
                    except Exception as e:
                        restore_status = f"Failed to auto-restore ingress route to WRR state: {e}"
                        await ctx.error(restore_status)

                try:
                    result = await self.traefik_service.disable_traffic_mirroring(
                        route_name=route_name,
                        namespace=namespace,
                    )
                    if restore_status:
                        result["restore_status"] = restore_status
                    await ctx.info(f"Successfully disabled mirroring for '{route_name}'")
                    return result
                except TraefikMirroringError as e:
                    await ctx.error(str(e))
                    raise
                except Exception as e:
                    await ctx.error(str(e))
                    raise TraefikOperationError(f"Failed to disable mirroring: {str(e)}")

            # update
            await ctx.info(
                f"Updating mirror percent for '{route_name}' to {mirror_percent}%",
                extra={"route_name": route_name, "mirror_percent": mirror_percent},
            )
            try:
                result = await self.traefik_service.update_mirroring_percent(
                    route_name=route_name,
                    namespace=namespace,
                    mirror_percent=mirror_percent,
                )
                await ctx.info(f"Successfully updated mirroring for '{route_name}'")
                return result
            except TraefikMirroringError as e:
                await ctx.error(str(e))
                raise
            except Exception as e:
                await ctx.error(str(e))
                raise TraefikOperationError(f"Failed to update mirroring: {str(e)}")

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Manage Route Middlewares",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def traefik_manage_route_middlewares(
            action: Literal["attach", "detach"] = Field(
                ...,
                description="Action: attach (add middlewares to route) | detach (remove middlewares from route)",
            ),
            route_name: str = Field(..., min_length=1, description="IngressRoute name"),
            middleware_names: List[str] = Field(
                ...,
                description="List of Middleware names to attach or detach (same namespace as route)",
            ),
            namespace: str = Field(default="default", description="Kubernetes namespace"),
            traefik_version: str = Field(default="v3", description="Traefik API version: 'v3' or 'v2'"),
            route_index: Optional[int] = Field(
                default=None,
                description="Apply only to this route rule index (0-based). Omit to apply to all rules.",
            ),
            ctx: Optional[Context] = None,
        ) -> Dict[str, Any]:
            """Attach or detach Middlewares on an IngressRoute.

            Modifies an existing IngressRoute to add or remove references
            to Middleware objects. Idempotent.

            Returns:
            - JSON dict with {"status": str, "message": str, ...}

            When NOT to use:
            - To create the actual middleware → use traefik_manage_middleware.
            """
            assert self.traefik_service is not None
            assert ctx is not None

            if action == "attach":
                await ctx.info(
                    f"Attaching middleware(s) {middleware_names} to IngressRoute '{route_name}'",
                    extra={"route_name": route_name, "middleware_names": middleware_names, "namespace": namespace},
                )
                try:
                    result = await self.traefik_service.attach_middleware_to_route(
                        route_name=route_name,
                        middleware_names=middleware_names,
                        namespace=namespace,
                        traefik_version=traefik_version,
                        route_index=route_index,
                    )
                    if result.get("status") in ("success", "no_change"):
                        await ctx.info(result.get("message", "Done"))
                    return result
                except TraefikRouteNotFoundError as e:
                    await ctx.error(str(e))
                    raise
                except TraefikOperationError as e:
                    await ctx.error(str(e))
                    raise
            else:
                await ctx.info(
                    f"Detaching middleware(s) {middleware_names} from IngressRoute '{route_name}'",
                    extra={"route_name": route_name, "middleware_names": middleware_names, "namespace": namespace},
                )
                try:
                    result = await self.traefik_service.detach_middleware_from_route(
                        route_name=route_name,
                        middleware_names=middleware_names,
                        namespace=namespace,
                        traefik_version=traefik_version,
                        route_index=route_index,
                    )
                    await ctx.info(result.get("message", "Done"))
                    return result
                except TraefikRouteNotFoundError as e:
                    await ctx.error(str(e))
                    raise
                except TraefikOperationError as e:
                    await ctx.error(str(e))
                    raise
                except Exception as e:
                    await ctx.error(str(e))
                    raise TraefikOperationError(f"Failed to detach middleware: {e}")
