#!/usr/bin/env python3
"""Offline Traefik v3 Middleware, MiddlewareTCP & ServersTransport YAML generator."""

import argparse
import json
import re
import sys

try:
    import yaml  # type: ignore[import-untyped]
except ImportError:
    yaml = None


def _yaml_scalar(val: object) -> str:
    if val is None:
        return "null"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return str(val)
    s = str(val)
    if s == "" or any(c in s for c in (":", "#", "`", "{", "}", "[", "]", ",", "&", "*", "?", "|", ">", "'", '"', "%", "@")) or s.lower() in ("true", "false", "null", "yes", "no", "on", "off") or re.match(r"^\s|\s$", s):
        return json.dumps(s)
    return s


def _dump_yaml_lines(obj: object, indent: int = 0) -> list[str]:
    pad = " " * indent
    if isinstance(obj, dict):
        if not obj:
            return [f"{pad}{{}}"]
        out: list[str] = []
        for k, v in obj.items():
            if isinstance(v, dict) and v:
                out.append(f"{pad}{k}:")
                out.extend(_dump_yaml_lines(v, indent + 2))
            elif isinstance(v, list) and v:
                out.append(f"{pad}{k}:")
                out.extend(_dump_yaml_lines(v, indent + 2))
            elif isinstance(v, dict):
                out.append(f"{pad}{k}: {{}}")
            elif isinstance(v, list):
                out.append(f"{pad}{k}: []")
            else:
                out.append(f"{pad}{k}: {_yaml_scalar(v)}")
        return out
    if isinstance(obj, list):
        if not obj:
            return [f"{pad}[]"]
        out = []
        for item in obj:
            if isinstance(item, dict) and item:
                items_iter = list(item.items())
                fk, fv = items_iter[0]
                if isinstance(fv, (dict, list)) and fv:
                    out.append(f"{pad}- {fk}:")
                    out.extend(_dump_yaml_lines(fv, indent + 4))
                else:
                    out.append(f"{pad}- {fk}: {_yaml_scalar(fv) if not isinstance(fv, (dict, list)) else ('{}' if isinstance(fv, dict) else '[]')}")
                for rk, rv in items_iter[1:]:
                    if isinstance(rv, (dict, list)) and rv:
                        out.append(f"{pad}  {rk}:")
                        out.extend(_dump_yaml_lines(rv, indent + 4))
                    else:
                        out.append(f"{pad}  {rk}: {_yaml_scalar(rv) if not isinstance(rv, (dict, list)) else ('{}' if isinstance(rv, dict) else '[]')}")
            else:
                out.append(f"{pad}- {_yaml_scalar(item)}")
        return out
    return [f"{pad}{_yaml_scalar(obj)}"]


def _safe_dump_yaml(doc: dict) -> str:
    if yaml is not None:
        return yaml.safe_dump(doc, sort_keys=False)
    return "\n".join(_dump_yaml_lines(doc)) + "\n"


TYPE_TO_KEY = {
    "rate_limit": "rateLimit",
    "in_flight_req": "inFlightReq",
    "in_flight_conn": "inFlightConn",
    "circuit_breaker": "circuitBreaker",
    "retry": "retry",
    "strip_prefix": "stripPrefix",
    "strip_prefix_regex": "stripPrefixRegex",
    "add_prefix": "addPrefix",
    "replace_path": "replacePath",
    "replace_path_regex": "replacePathRegex",
    "redirect_scheme": "redirectScheme",
    "redirect_regex": "redirectRegex",
    "headers": "headers",
    "ip_allow_list": "ipAllowList",
    "ip_deny_list": "ipDenyList",
    "basic_auth": "basicAuth",
    "digest_auth": "digestAuth",
    "forward_auth": "forwardAuth",
    "compress": "compress",
    "buffering": "buffering",
    "errors": "errors",
    "chain": "chain",
    "plugin": "plugin",
    "grpc_web": "grpcWeb",
    "pass_tls_client_cert": "passTLSClientCert",
    "content_type": "contentType",
}


def render(args: argparse.Namespace) -> str:
    spec_payload = json.loads(args.spec_json)
    if args.kind in ("ServersTransport", "ServersTransportTCP"):
        doc = {
            "apiVersion": "traefik.io/v1alpha1",
            "kind": args.kind,
            "metadata": {
                "name": args.name,
                "namespace": args.namespace,
                "labels": {"app.kubernetes.io/managed-by": "talkops-traefik-mcp"},
            },
            "spec": spec_payload,
        }
        return _safe_dump_yaml(doc)

    crd_kind = "MiddlewareTCP" if (args.protocol == "tcp" or args.kind == "MiddlewareTCP") else "Middleware"
    spec_key = TYPE_TO_KEY.get(args.type, args.type)
    doc = {
        "apiVersion": "traefik.io/v1alpha1",
        "kind": crd_kind,
        "metadata": {
            "name": args.name,
            "namespace": args.namespace,
            "labels": {"app.kubernetes.io/managed-by": "talkops-traefik-mcp"},
        },
        "spec": {spec_key: spec_payload},
    }
    return _safe_dump_yaml(doc)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render a Traefik v3 Middleware, MiddlewareTCP, or ServersTransport YAML manifest offline."
    )
    parser.add_argument("--name", default="api-ratelimit", help="Resource name")
    parser.add_argument("--namespace", default="default", help="Kubernetes namespace")
    parser.add_argument("--protocol", choices=("http", "tcp"), default="http", help="Protocol (http or tcp)")
    parser.add_argument(
        "--kind",
        choices=("Middleware", "MiddlewareTCP", "ServersTransport", "ServersTransportTCP"),
        default="Middleware",
        help="CRD kind",
    )
    parser.add_argument("--type", default="rate_limit", help="Middleware type snake_case name")
    parser.add_argument(
        "--spec-json",
        default='{"average": 100, "burst": 200, "period": "1s"}',
        help="JSON string for the middleware or transport spec",
    )
    args = parser.parse_args()
    sys.stdout.write(render(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
