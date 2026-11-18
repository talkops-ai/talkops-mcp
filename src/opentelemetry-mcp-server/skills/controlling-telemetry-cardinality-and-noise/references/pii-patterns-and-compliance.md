# PII Scrubbing Patterns & Compliance Reference (`SEC_PII_REDACTION_MISSING`)

## Table of Contents

1. [Regulatory Requirements (GDPR, PCI-DSS, HIPAA, SOC 2)](#1-regulatory-requirements-gdpr-pci-dss-hipaa-soc-2)
2. [Configuring Automatic PII Scrubbing](#2-configuring-automatic-pii-scrubbing)
3. [Standard PII & Credential Regex Patterns](#3-standard-pii--credential-regex-patterns)
4. [Header & Query Parameter Scrubbing](#4-header--query-parameter-scrubbing)
5. [Verifying Redaction Posture](#5-verifying-redaction-posture)

---

## 1. Regulatory Requirements (GDPR, PCI-DSS, HIPAA, SOC 2)

Application logs and exception stack traces frequently capture:
- Email addresses, phone numbers, and government IDs (GDPR / CCPA).
- Primary Account Numbers (PAN / credit card numbers) and CVVs (PCI-DSS).
- Bearer tokens, OAuth JWTs, API keys, and database connection strings (SOC 2).

Scrubbing at the OpenTelemetry Collector boundary ensures sensitive values are masked (`***REDACTED***`) before leaving the Kubernetes cluster.

---

## 2. Configuring Automatic PII Scrubbing

Calling `otel_configure_processing(namespace=..., collector_name=..., rules={"mask_pii": ["email", "credit_card", "ssn", "jwt", "bearer_token"]})` wires OTTL `replace_pattern` statements into the collector's `transform` processor across traces and logs to mask emails, credit card numbers, SSNs, and bearer tokens before export.

---

## 3. Standard PII & Credential Regex Patterns

| Category | OTTL Regex Pattern | Replacement |
|---|---|---|
| **Email Address** | `[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}` | `[REDACTED_EMAIL]` |
| **US SSN** | `\\b\\d{3}-\\d{2}-\\d{4}\\b` | `[REDACTED_SSN]` |
| **Credit Card (PAN)** | `\\b(?:\\d[ -]*?){13,16}\\b` | `[REDACTED_PAN]` |
| **Bearer / JWT Token** | `(?i)bearer\\s+[a-zA-Z0-9_\\-\\.=]+` | `Bearer [REDACTED_TOKEN]` |
| **URL Query Secrets (`api_key`, `access_token`, `code`, `secret`)** | `(?i)([?&](?:api_key|access_token|code|secret|password|token)=)[^&\\s"']+` | `${1}[REDACTED]` |

---

## 4. Header & Query Parameter Scrubbing

Always delete sensitive HTTP **request and response** headers at the collector tier via `drop_attributes` in `otel_configure_processing` (covering both underscore and hyphenated semantic conventions):
- `http.request.header.authorization`
- `http.request.header.cookie`
- `http.request.header.x_api_key` and `http.request.header.x-api-key`
- `http.response.header.set_cookie` and `http.response.header.set-cookie`
- Scrub URL query parameters (`api_key`, `access_token`, `code`, `secret`) in `url.full`, `url.query`, `http.target`, and log `body.string` using `replace_pattern(..., "(?i)([?&](?:api_key|access_token|code|secret)=)[^&\\s\"']+", "${1}[REDACTED]")`.
- Parameterize `db.statement` values when SQL queries are not parameterized by the ORM.

---

## 5. Verifying Redaction Posture

After applying `otel_configure_processing(..., rules={"mask_pii": ["email", "credit_card", "ssn", "jwt", "bearer_token"]}, dry_run=False)`:
1. Call `otel_audit_security_posture` (`namespace`) to verify that `SEC_PII_REDACTION_MISSING` is cleared for the collector.
2. Read `otel://logs-profile/{namespace}/{collector}` to confirm PII redaction is listed as active.
