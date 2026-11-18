#!/usr/bin/env python3
"""Offline Traefik v3 IngressRoute & TraefikService YAML manifest generator."""

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


def _safe_dump_all_yaml(docs: list[dict]) -> str:
    if yaml is not None:
        return yaml.safe_dump_all(docs, sort_keys=False)
    rendered = ["\n".join(_dump_yaml_lines(d)) for d in docs]
    return "\n---\n".join(rendered) + "\n"


def build_manifest(args: argparse.Namespace) -> str:
    match_parts = [f"Host(`{args.host}`)"]
    if args.path_prefix:
        match_parts.append(f"PathPrefix(`{args.path_prefix}`)")
    for hdr in args.header or []:
        if "=" in hdr:
            k, v = hdr.split("=", 1)
            match_parts.append(f"Header(`{k.strip()}`, `{v.strip()}`)")
    match_rule = " && ".join(match_parts)

    docs = []
    if args.canary_service:
        wrr_name = args.traefik_service or f"{args.name}-wrr"
        stable_w = 100 - args.canary_weight
        ts_doc = {
            "apiVersion": "traefik.io/v1alpha1",
            "kind": "TraefikService",
            "metadata": {
                "name": wrr_name,
                "namespace": args.namespace,
                "labels": {"app.kubernetes.io/managed-by": "talkops-traefik-mcp"},
            },
            "spec": {
                "weighted": {
                    "services": [
                        {"name": args.service, "port": args.port, "weight": stable_w},
                        {"name": args.canary_service, "port": args.port, "weight": args.canary_weight},
                    ]
                }
            },
        }
        docs.append(ts_doc)
        route_services = [{"name": wrr_name, "kind": "TraefikService"}]
    else:
        route_services = [{"name": args.service, "port": args.port}]

    route_rule = {
        "kind": "Rule",
        "match": match_rule,
        "services": route_services,
    }
    if args.priority is not None:
        route_rule["priority"] = args.priority
    if args.middleware:
        route_rule["middlewares"] = [{"name": m} for m in args.middleware]

    ir_spec = {
        "entryPoints": [e.strip() for e in args.entry_points.split(",") if e.strip()],
        "routes": [route_rule],
    }
    if args.tls_secret or args.cert_resolver:
        tls_block = {}
        if args.tls_secret:
            tls_block["secretName"] = args.tls_secret
        if args.cert_resolver:
            tls_block["certResolver"] = args.cert_resolver
        ir_spec["tls"] = tls_block

    ir_doc = {
        "apiVersion": "traefik.io/v1alpha1",
        "kind": "IngressRoute",
        "metadata": {
            "name": args.name,
            "namespace": args.namespace,
            "labels": {"app.kubernetes.io/managed-by": "talkops-traefik-mcp"},
        },
        "spec": ir_spec,
    }
    docs.append(ir_doc)
    return _safe_dump_all_yaml(docs)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render Traefik v3 IngressRoute and optional weighted TraefikService YAML manifests offline."
    )
    parser.add_argument("--name", default="app-route", help="IngressRoute name")
    parser.add_argument("--traefik-service", default=None, help="Optional weighted TraefikService name override")
    parser.add_argument("--namespace", default="default", help="Kubernetes namespace")
    parser.add_argument("--host", default="app.example.com", help="Hostname to match")
    parser.add_argument("--path-prefix", default="/", help="PathPrefix to match")
    parser.add_argument("--header", action="append", help="Header match in KEY=VALUE format")
    parser.add_argument("--service", default="app-svc", help="Primary Kubernetes Service name")
    parser.add_argument("--port", type=int, default=80, help="Backend Service port")
    parser.add_argument("--canary-service", default=None, help="Optional canary Service name")
    parser.add_argument("--canary-weight", type=int, default=10, help="Canary traffic weight (0-100)")
    parser.add_argument("--entry-points", default="websecure", help="Comma-separated entryPoints")
    parser.add_argument("--middleware", action="append", help="Middleware name to attach")
    parser.add_argument("--priority", type=int, default=None, help="Explicit rule priority")
    parser.add_argument("--tls-secret", default=None, help="TLS Kubernetes Secret name")
    parser.add_argument("--cert-resolver", default=None, help="Traefik ACME certResolver name")
    args = parser.parse_args()
    sys.stdout.write(build_manifest(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
