#!/usr/bin/env python3
"""Offline RFC 6125 wildcard & exact SAN hostname coverage checker."""

import argparse
import json
import sys


def hostname_matches_san(hostname: str, san: str) -> bool:
    host = hostname.strip().lower().rstrip(".")
    pattern = san.strip().lower().rstrip(".")
    if not host or not pattern:
        return False
    if pattern == host:
        return True
    if pattern.startswith("*."):
        suffix = pattern[2:]
        if not suffix or "." not in suffix:
            return False
        if not host.endswith("." + suffix):
            return False
        prefix = host[: -(len(suffix) + 1)]
        return bool(prefix) and "." not in prefix
    return False


def check_coverage(hosts: list[str], sans: list[str]) -> dict:
    covered = []
    uncovered = []
    for h in hosts:
        if any(hostname_matches_san(h, s) for s in sans):
            covered.append(h)
        else:
            uncovered.append(h)
    return {
        "all_covered": len(uncovered) == 0,
        "hosts": hosts,
        "sans": sans,
        "covered": covered,
        "uncovered": uncovered,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify RFC 6125 wildcard and exact SAN coverage for route hostnames."
    )
    parser.add_argument(
        "--hosts",
        default="api.example.com,app.example.com",
        help="Comma-separated route hostnames",
    )
    parser.add_argument(
        "--sans",
        default="*.example.com,example.com",
        help="Comma-separated certificate SANs",
    )
    args = parser.parse_args()
    hosts = [h.strip() for h in args.hosts.split(",") if h.strip()]
    sans = [s.strip() for s in args.sans.split(",") if s.strip()]
    sys.stdout.write(json.dumps(check_coverage(hosts, sans), indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
