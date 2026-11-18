"""Dynamic X.509 PEM test certificate generator fixtures."""

import base64
import datetime
from typing import Sequence
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def generate_pem_cert(
    common_name: str = "api.example.com",
    sans: Sequence[str] = ("api.example.com", "*.example.com", "example.com"),
    days_valid: int = 90,
    days_offset: int = -1,
    issuer_cn: str = "Let's Encrypt Authority X3",
) -> str:
    """Return a PEM-encoded X.509 certificate string."""
    now = datetime.datetime.now(datetime.timezone.utc)
    not_before = now + datetime.timedelta(days=days_offset)
    not_after = now + datetime.timedelta(days=days_valid)

    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer_cn)])

    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(_KEY.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
    )
    if sans:
        builder = builder.add_extension(
            x509.SubjectAlternativeName([x509.DNSName(s) for s in sans]),
            critical=False,
        )
    cert = builder.sign(private_key=_KEY, algorithm=hashes.SHA256())
    return cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")


def generate_b64_cert(**kwargs) -> str:
    """Return a base64-encoded PEM certificate suitable for K8s Secret data['tls.crt']."""
    pem = generate_pem_cert(**kwargs)
    return base64.b64encode(pem.encode("utf-8")).decode("utf-8")


VALID_WILDCARD_CERT_PEM = generate_pem_cert(
    common_name="example.com",
    sans=("*.example.com", "example.com", "api.example.com"),
    days_valid=120,
)
VALID_WILDCARD_CERT_B64 = base64.b64encode(VALID_WILDCARD_CERT_PEM.encode("utf-8")).decode("utf-8")

EXPIRING_SOON_CERT_B64 = generate_b64_cert(
    common_name="expiring.example.com",
    sans=("expiring.example.com",),
    days_valid=5,
)

EXPIRED_CERT_B64 = generate_b64_cert(
    common_name="expired.example.com",
    sans=("expired.example.com",),
    days_offset=-60,
    days_valid=-2,
)

TRAEFIK_DEFAULT_CERT_PEM = generate_pem_cert(
    common_name="TRAEFIK DEFAULT CERT",
    sans=("*.traefik.default",),
    days_valid=365,
    issuer_cn="TRAEFIK DEFAULT CERT",
)
TRAEFIK_DEFAULT_CERT_B64 = base64.b64encode(TRAEFIK_DEFAULT_CERT_PEM.encode("utf-8")).decode("utf-8")
