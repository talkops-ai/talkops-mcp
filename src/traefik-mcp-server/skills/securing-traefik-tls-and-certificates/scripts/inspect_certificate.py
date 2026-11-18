#!/usr/bin/env python3
"""Offline X.509 PEM certificate parser (never outputs private keys)."""

import argparse
import base64
import datetime
import json
import sys
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.x509.oid import ExtensionOID, NameOID


def parse_cert(pem_text: str) -> dict:
    raw = pem_text.strip()
    if "-----BEGIN CERTIFICATE-----" not in raw:
        raw = base64.b64decode(raw).decode("utf-8", errors="replace")
    cert = x509.load_pem_x509_certificate(raw.encode("utf-8"))
    now = datetime.datetime.now(datetime.timezone.utc)
    not_before = cert.not_valid_before_utc
    not_after = cert.not_valid_after_utc
    days_remaining = int((not_after - now).total_seconds() // 86400)

    sans = []
    try:
        ext = cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
        sans = list(ext.value.get_values_for_type(x509.DNSName))
    except x509.ExtensionNotFound:
        pass

    cn_attrs = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    if not sans and cn_attrs:
        sans = [cn_attrs[0].value]

    subj = cert.subject.rfc4514_string()
    iss = cert.issuer.rfc4514_string()
    is_default = "TRAEFIK DEFAULT CERT" in subj.upper() or "TRAEFIK DEFAULT CERT" in iss.upper()

    return {
        "subject": subj,
        "issuer": iss,
        "sans": sans,
        "not_before": not_before.isoformat(),
        "not_after": not_after.isoformat(),
        "days_remaining": days_remaining,
        "expired": now >= not_after,
        "is_traefik_default_cert": is_default,
        "fingerprint_sha256": cert.fingerprint(hashes.SHA256()).hex(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect an X.509 PEM certificate file or string offline without exposing private keys."
    )
    parser.add_argument("--cert-file", default=None, help="Path to PEM certificate file")
    parser.add_argument("--pem", default=None, help="Inline PEM or base64-encoded certificate string")
    args = parser.parse_args()

    if args.cert_file:
        with open(args.cert_file, "r", encoding="utf-8") as fh:
            out = parse_cert(fh.read())
    elif args.pem:
        out = parse_cert(args.pem)
    else:
        out = {
            "status": "ready",
            "usage": "Pass --cert-file <path> or --pem <pem_or_base64> to inspect X.509 metadata.",
        }
    sys.stdout.write(json.dumps(out, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
