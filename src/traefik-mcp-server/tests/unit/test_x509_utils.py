"""Unit tests for X.509 PEM certificate parsing, expiry, Traefik default cert detection, and RFC 6125 wildcard coverage."""

from traefik_mcp_server.services.x509_utils import (
    check_host_coverage,
    hostname_matches_san,
    parse_pem_certificate,
)
from tests.fixtures.sample_certs import (
    EXPIRED_CERT_B64,
    EXPIRING_SOON_CERT_B64,
    TRAEFIK_DEFAULT_CERT_B64,
    VALID_WILDCARD_CERT_B64,
)


def test_parse_valid_expired_and_default_certificates():
    valid_meta = parse_pem_certificate(VALID_WILDCARD_CERT_B64)
    assert valid_meta["expired"] is False
    assert valid_meta["days_remaining"] > 60
    assert "*.example.com" in valid_meta["sans"]
    assert valid_meta["is_traefik_default_cert"] is False

    expiring_meta = parse_pem_certificate(EXPIRING_SOON_CERT_B64)
    assert 0 <= expiring_meta["days_remaining"] <= 10

    expired_meta = parse_pem_certificate(EXPIRED_CERT_B64)
    assert expired_meta["expired"] is True

    default_meta = parse_pem_certificate(TRAEFIK_DEFAULT_CERT_B64)
    assert default_meta["is_traefik_default_cert"] is True


def test_rfc6125_wildcard_san_matching():
    assert hostname_matches_san("api.example.com", "*.example.com") is True
    assert hostname_matches_san("example.com", "*.example.com") is False
    assert hostname_matches_san("deep.sub.example.com", "*.example.com") is False

    all_ok, covered, uncovered = check_host_coverage(
        ["api.example.com", "example.com", "deep.sub.example.com"],
        ["*.example.com", "example.com"],
    )
    assert all_ok is False
    assert "api.example.com" in covered
    assert "example.com" in covered
    assert uncovered == ["deep.sub.example.com"]
