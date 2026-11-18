# Shadow Traffic Mirroring Guide

## Table of Contents

1. [How Traefik Traffic Mirroring Works](#1-how-traefik-traffic-mirroring-works)
2. [Idempotency & Side-Effect Risks](#2-idempotency--side-effect-risks)
3. [Request Body Buffering (`mirror_body` & `max_body_size`)](#3-request-body-buffering-mirror_body--max_body_size)
4. [Enabling, Updating, and Disabling Mirroring](#4-enabling-updating-and-disabling-mirroring)

## 1. How Traefik Traffic Mirroring Works

Traefik's `TraefikService` `spec.mirroring` sends `100%` of client requests to the primary service (`spec.mirroring.name`) and asynchronously duplicates a percentage (`1–100%`) of requests to one or more shadow services (`spec.mirroring.mirrors`). Responses from shadow backends are discarded by Traefik and never returned to the client.

## 2. Idempotency & Side-Effect Risks

Because shadow requests are real HTTP calls:
- **Never** mirror `POST`/`PUT`/`DELETE` traffic to a shadow service that writes to the same production database or payment gateway unless it runs in read-only or dry-run mode.
- Always gate `traefik_configure_traffic_mirroring(..., dry_run=False)` behind explicit operator confirmation (`confirm=True`).

## 3. Request Body Buffering (`mirror_body` & `max_body_size`)

- By default, `mirror_body: false` avoids buffering large request payloads in Traefik memory when only `GET`/`HEAD` endpoints are being benchmarked.
- When `mirror_body: true` is required for `POST` payload testing, always set a bounded `max_body_size` (e.g., `1048576` bytes = 1 MiB) to prevent memory exhaustion under high concurrency.

## 4. Enabling, Updating, and Disabling Mirroring

1. **Preview Enable**: `traefik_configure_traffic_mirroring(name="orders-mirror", action="enable", spec={...}, route_name="orders-route", dry_run=True)`
2. **Apply Enable**: `traefik_configure_traffic_mirroring(..., dry_run=False, confirm=True)`
3. **Disable & Restore Route**: `traefik_configure_traffic_mirroring(name="orders-mirror", action="disable", route_name="orders-route", dry_run=False, confirm=True)`
