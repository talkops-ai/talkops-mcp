#!/usr/bin/env python3
"""Offline Traefik v3 middleware spec & execution-order linter."""

import argparse
import json
import sys


ORDER_PRIORITY = {
    "ipAllowList": 10,
    "ipDenyList": 10,
    "redirectScheme": 20,
    "redirectRegex": 20,
    "rateLimit": 30,
    "inFlightReq": 30,
    "headers": 40,
    "forwardAuth": 50,
    "basicAuth": 50,
    "digestAuth": 50,
    "stripPrefix": 60,
    "stripPrefixRegex": 60,
    "addPrefix": 60,
    "replacePath": 60,
    "replacePathRegex": 60,
    "compress": 70,
    "retry": 80,
    "circuitBreaker": 85,
    "buffering": 90,
    "errors": 95,
}


def lint_spec(spec: dict, chain_order: list[str]) -> dict:
    errors = []
    warnings = []

    if "ipWhiteList" in spec:
        errors.append("Deprecated v2 'ipWhiteList' detected; use 'ipAllowList' in Traefik v3.")
    if "stripPrefix" in spec and "forceSlash" in (spec.get("stripPrefix") or {}):
        errors.append("Removed v2 field 'stripPrefix.forceSlash' detected; remove 'forceSlash' in Traefik v3.")
    for auth_k in ("basicAuth", "digestAuth"):
        if auth_k in spec and "users" in (spec.get(auth_k) or {}):
            errors.append(f"Inline '{auth_k}.users' plaintext credentials forbidden; use '{auth_k}.secret'.")
    if "retry" in spec and int((spec.get("retry") or {}).get("attempts", 1)) > 4:
        warnings.append("retry.attempts > 4 can trigger retry amplification storms under backend degradation (REL-001).")
    if "ipDenyList" in spec:
        warnings.append("ipDenyList requires Traefik v3.5+ CRDs; verify 'traefik://schema/Middleware' before applying.")

    prev_rank = -1
    prev_type = ""
    for mw_type in chain_order:
        rank = ORDER_PRIORITY.get(mw_type, 55)
        if rank < prev_rank:
            warnings.append(
                f"Middleware ordering warning: '{mw_type}' (stage {rank}) appears after '{prev_type}' (stage {prev_rank})."
            )
        prev_rank = rank
        prev_type = mw_type

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "chain_evaluated": chain_order,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Lint a Traefik v3 Middleware spec JSON and optional middleware chain ordering."
    )
    parser.add_argument(
        "--spec-json",
        default='{"rateLimit": {"average": 100, "burst": 200}}',
        help="Middleware spec JSON object",
    )
    parser.add_argument(
        "--chain",
        default="ipAllowList,rateLimit,headers,forwardAuth,stripPrefix,retry",
        help="Comma-separated list of middleware types in execution order",
    )
    args = parser.parse_args()
    spec = json.loads(args.spec_json)
    chain = [c.strip() for c in args.chain.split(",") if c.strip()]
    sys.stdout.write(json.dumps(lint_spec(spec, chain), indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
