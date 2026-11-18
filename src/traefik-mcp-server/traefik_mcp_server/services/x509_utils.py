"""X.509 TLS certificate metadata extraction and SAN coverage checks (never exposes private key material)."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from cryptography import x509
from cryptography.x509.oid import ExtensionOID, NameOID


def parse_pem_certificate(pem_or_b64: str) -> Dict[str, Any]:
    """Parse a PEM certificate (or base64-encoded PEM from a Kubernetes Secret's data['tls.crt']).

    Returns metadata only — never returns private key bytes.
    """
    raw = (pem_or_b64 or "").strip()
    if not raw:
        raise ValueError("Empty certificate data.")

    if "-----BEGIN CERTIFICATE-----" not in raw:
        try:
            decoded = base64.b64decode(raw).decode("utf-8", errors="replace")
            if "-----BEGIN CERTIFICATE-----" in decoded:
                raw = decoded
        except Exception:
            pass

    cert = x509.load_pem_x509_certificate(raw.encode("utf-8"))

    # Subject & Issuer Common Name
    subject_cn = ""
    for attr in cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME):
        subject_cn = str(attr.value)
        break
    issuer_cn = ""
    for attr in cert.issuer.get_attributes_for_oid(NameOID.COMMON_NAME):
        issuer_cn = str(attr.value)
        break

    subject_str = cert.subject.rfc4514_string()
    issuer_str = cert.issuer.rfc4514_string()

    # SANs
    sans: List[str] = []
    try:
        ext = cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
        sans = list(ext.value.get_values_for_type(x509.DNSName))
    except x509.ExtensionNotFound:
        if subject_cn:
            sans = [subject_cn]

    not_before = cert.not_valid_before_utc
    not_after = cert.not_valid_after_utc
    now = datetime.now(timezone.utc)
    delta_seconds = (not_after - now).total_seconds()
    days_remaining = int(delta_seconds // 86400)
    expired = delta_seconds <= 0

    is_default = (
        "traefik default cert" in subject_cn.lower()
        or "traefik default cert" in issuer_cn.lower()
        or any(s.endswith(".traefik.default") for s in sans)
    )

    return {
        "subject": subject_str,
        "subject_cn": subject_cn,
        "issuer": issuer_str,
        "issuer_cn": issuer_cn,
        "sans": sans,
        "not_before": not_before.isoformat(),
        "not_after": not_after.isoformat(),
        "days_remaining": days_remaining,
        "expired": expired,
        "is_traefik_default_cert": is_default,
        "serial_number": hex(cert.serial_number),
    }


def host_matches_san(hostname: str, san_pattern: str) -> bool:
    """RFC 6125 hostname matching against a certificate SAN (single-level wildcard only)."""
    h = hostname.strip().lower().rstrip(".")
    p = san_pattern.strip().lower().rstrip(".")
    if not h or not p:
        return False
    if h == p:
        return True
    if p.startswith("*."):
        suffix = p[2:]
        if "." not in suffix:
            return False
        # *.example.com matches api.example.com, NOT example.com and NOT a.b.example.com
        if h.endswith("." + suffix):
            left_label = h[: -(len(suffix) + 1)]
            return "." not in left_label and len(left_label) > 0
    return False


def check_host_coverage(
    hosts: List[str],
    sans: List[str],
) -> Tuple[bool, List[str], List[str]]:
    """Verify whether all route hostnames are covered by certificate SANs.

    Returns:
        (all_covered, covered_hosts, uncovered_hosts)
    """
    covered: List[str] = []
    uncovered: List[str] = []
    for host in hosts:
        h = host.strip()
        if not h or h == "*":
            continue
        if any(host_matches_san(h, san) for san in sans):
            covered.append(h)
        else:
            uncovered.append(h)
    return len(uncovered) == 0, covered, uncovered


hostname_matches_san = host_matches_san

