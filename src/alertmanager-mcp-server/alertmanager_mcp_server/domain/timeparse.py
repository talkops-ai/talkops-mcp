"""RFC3339 timestamp parsing, UTC normalization, and silence window resolution.

Alertmanager v2 OpenAPI requires RFC3339 timestamps with explicit timezone
offsets (`Z` or `±HH:MM`). Naive timestamps without timezone offsets are
rejected by Alertmanager with HTTP 400.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


class TimeValidationError(ValueError):
    """Raised when a timestamp or time window violates RFC3339 or temporal constraints."""


def utc_now() -> datetime:
    """Return current aware UTC datetime."""
    return datetime.now(timezone.utc)


def parse_rfc3339(
    value: str | datetime,
    *,
    require_tz: bool = True,
    field_name: str = "timestamp",
) -> datetime:
    """Parse an RFC3339 timestamp string or datetime into a UTC-normalized aware datetime.

    Args:
        value: ISO-8601 / RFC3339 string or `datetime` instance.
        require_tz: When True (default), reject naive datetimes that lack an
            explicit timezone offset (`Z` or `±HH:MM`).
        field_name: Name of the field for error reporting.
    """
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            raise TimeValidationError(f"'{field_name}' cannot be empty.")
        if "T" not in raw and " " not in raw:
            raise TimeValidationError(
                f"'{field_name}' ('{value}') must be a full RFC3339 date-time "
                "(e.g. '2026-03-29T10:00:00Z'), not a date-only string."
            )
        normalized = raw[:-1] + "+00:00" if raw.endswith(("Z", "z")) else raw
        try:
            dt = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise TimeValidationError(
                f"Invalid RFC3339 {field_name} '{value}': {exc}. "
                "Expected format like '2026-03-29T10:00:00Z' or '2026-03-29T15:30:00+05:30'."
            ) from exc
    else:
        raise TimeValidationError(
            f"Unsupported type for '{field_name}': {type(value).__name__}."
        )

    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        if require_tz:
            raise TimeValidationError(
                f"'{field_name}' ('{value}') is missing an explicit timezone offset. "
                "Alertmanager v2 requires RFC3339 timestamps with 'Z' or '±HH:MM' "
                "(e.g. '2026-03-29T10:00:00Z')."
            )
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)


def format_rfc3339_utc(dt: datetime) -> str:
    """Format a datetime as an RFC3339 UTC string (`YYYY-MM-DDTHH:MM:SSZ`)."""
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise TimeValidationError(
            f"Cannot serialize naive datetime '{dt.isoformat()}' without timezone."
        )
    utc_dt = dt.astimezone(timezone.utc)
    if utc_dt.microsecond:
        return utc_dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_silence_window(
    *,
    starts_at: str | datetime | None = None,
    ends_at: str | datetime | None = None,
    duration_minutes: int | None = None,
    default_duration_minutes: int = 120,
    now: datetime | None = None,
) -> tuple[datetime, datetime, float]:
    """Resolve and validate a `(starts_at, ends_at, duration_minutes)` window in UTC.

    Enforces:
    - Explicit timezone offsets on any provided `starts_at` / `ends_at`
    - `duration_minutes > 0` when used
    - `ends_at > starts_at`
    - `ends_at > now` (cannot create an already-expired silence)
    """
    ref_now = now.astimezone(timezone.utc) if now is not None else utc_now()

    start_dt = (
        parse_rfc3339(starts_at, require_tz=True, field_name="starts_at")
        if starts_at is not None
        else ref_now
    )

    if ends_at is not None:
        end_dt = parse_rfc3339(ends_at, require_tz=True, field_name="ends_at")
    else:
        eff_minutes = (
            duration_minutes
            if duration_minutes is not None
            else default_duration_minutes
        )
        if eff_minutes <= 0:
            raise TimeValidationError(
                f"duration_minutes must be positive (got {eff_minutes})."
            )
        end_dt = start_dt + timedelta(minutes=eff_minutes)

    if end_dt <= start_dt:
        raise TimeValidationError(
            f"ends_at ({format_rfc3339_utc(end_dt)}) must be strictly after "
            f"starts_at ({format_rfc3339_utc(start_dt)})."
        )

    if end_dt <= ref_now:
        raise TimeValidationError(
            f"ends_at ({format_rfc3339_utc(end_dt)}) is in the past relative to "
            f"current UTC time ({format_rfc3339_utc(ref_now)})."
        )

    total_minutes = (end_dt - start_dt).total_seconds() / 60.0
    return start_dt, end_dt, total_minutes
