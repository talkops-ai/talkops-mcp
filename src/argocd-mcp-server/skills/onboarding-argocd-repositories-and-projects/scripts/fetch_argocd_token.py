#!/usr/bin/env python3
"""Stdlib-only helper to fetch and validate an ArgoCD API token without leaking secrets to stdout.

Writes the fetched token directly to an environment file (--env-file) if requested and outputs
only a redacted validation summary to stdout.
"""

import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional


def _mask_token(token: str) -> str:
    """Return a safe, redacted representation of a JWT/bearer token."""
    if not token or len(token) < 10:
        return "***REDACTED***"
    return f"{token[:4]}...{token[-4:]} (len={len(token)})"


def _make_ssl_context(verify_tls: bool) -> ssl.SSLContext:
    if verify_tls:
        return ssl.create_default_context()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def fetch_token(
    server_url: str,
    username: str,
    password: str,
    verify_tls: bool = True,
    timeout: int = 20,
) -> str:
    """Authenticate against POST /api/v1/session and return the token string."""
    url = f"{server_url.rstrip('/')}/api/v1/session"
    payload = json.dumps({"username": username, "password": password}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    ctx = _make_ssl_context(verify_tls)
    with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        token = data.get("token")
        if not token:
            raise ValueError("ArgoCD session response did not contain a token.")
        return str(token)


def validate_token(
    server_url: str,
    token: str,
    verify_tls: bool = True,
    timeout: int = 20,
) -> Dict[str, Any]:
    """Verify the token against GET /api/v1/applications?limit=1."""
    url = f"{server_url.rstrip('/')}/api/v1/applications?limit=1"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="GET",
    )
    ctx = _make_ssl_context(verify_tls)
    with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
        return {"http_status": resp.status, "authenticated": resp.status == 200}


def write_token_to_env_file(env_file: Path, server_url: str, token: str) -> None:
    """Write or update ARGOCD_SERVER_URL and ARGOCD_AUTH_TOKEN in an .env file with 0600 permissions."""
    existing_lines: List[str] = []
    if env_file.exists():
        existing_lines = env_file.read_text(encoding="utf-8").splitlines()

    filtered = [
        line
        for line in existing_lines
        if not line.startswith("ARGOCD_AUTH_TOKEN=")
        and not line.startswith("ARGOCD_SERVER_URL=")
    ]
    filtered.append(f"ARGOCD_SERVER_URL={server_url.rstrip('/')}")
    filtered.append(f"ARGOCD_AUTH_TOKEN={token}")
    env_file.write_text("\n".join(filtered) + "\n", encoding="utf-8")
    try:
        os.chmod(env_file, 0o600)
    except OSError:
        pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fetch_argocd_token.py",
        description="Fetch and validate an ArgoCD authentication token without printing raw secrets to stdout.",
    )
    parser.add_argument(
        "--server",
        default=os.environ.get("ARGOCD_SERVER_URL") or os.environ.get("ARGOCD_SERVER"),
        help="ArgoCD server URL (or set ARGOCD_SERVER_URL).",
    )
    parser.add_argument(
        "--username",
        default=os.environ.get("ARGOCD_USERNAME"),
        help="ArgoCD username for session token creation (or set ARGOCD_USERNAME).",
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("ARGOCD_PASSWORD"),
        help="ArgoCD password for session token creation (or set ARGOCD_PASSWORD).",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        default=os.environ.get("ARGOCD_INSECURE", "false").lower() == "true",
        help="Skip TLS certificate verification.",
    )
    parser.add_argument(
        "--env-file",
        default=None,
        help="Optional path to .env file where ARGOCD_AUTH_TOKEN will be saved (mode 0600).",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.server:
        sys.stderr.write("Error: --server (or ARGOCD_SERVER_URL) is required.\n")
        return 1

    verify_tls = not args.insecure
    existing_token = os.environ.get("ARGOCD_AUTH_TOKEN")

    try:
        if args.username and args.password:
            token = fetch_token(
                server_url=args.server,
                username=args.username,
                password=args.password,
                verify_tls=verify_tls,
            )
            source = "session_login"
        elif existing_token:
            token = existing_token
            source = "environment"
        else:
            sys.stderr.write(
                "Error: Provide --username and --password (or ARGOCD_AUTH_TOKEN in env) to validate.\n"
            )
            return 1

        check = validate_token(server_url=args.server, token=token, verify_tls=verify_tls)
        saved_to: Optional[str] = None
        if args.env_file:
            env_path = Path(args.env_file)
            write_token_to_env_file(env_path, args.server, token)
            saved_to = str(env_path)

        summary = {
            "server_url": args.server.rstrip("/"),
            "token_source": source,
            "token_preview": _mask_token(token),
            "valid": check["authenticated"],
            "saved_to_env_file": saved_to,
        }
        sys.stdout.write(json.dumps(summary, indent=2) + "\n")
        return 0 if check["authenticated"] else 1
    except urllib.error.HTTPError as exc:
        sys.stderr.write(f"HTTP error ({exc.code}) communicating with ArgoCD: {exc.reason}\n")
        return 1
    except Exception as exc:
        sys.stderr.write(f"Failed to fetch or validate ArgoCD token: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
