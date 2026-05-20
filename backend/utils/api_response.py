from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from fastapi import Request

logger = logging.getLogger("nexus.api")


def request_id_from(request: Request | None) -> str:
    if request is None:
        return str(uuid.uuid4())
    existing = request.headers.get("x-request-id")
    return existing or str(uuid.uuid4())


def ok(data: dict[str, Any] | None = None, request_id: str | None = None) -> dict[str, Any]:
    payload = {"status": "success"}
    if request_id:
        payload["request_id"] = request_id
    if data:
        payload.update(data)
    return payload


def err(code: str, message: str, details: Any = None, request_id: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"status": "error", "code": code, "message": message}
    if details is not None:
        payload["details"] = details
    if request_id:
        payload["request_id"] = request_id
    return payload


def log_route_start(route: str, request_id: str) -> float:
    start = time.perf_counter()
    logger.info("[route:start] %s request_id=%s", route, request_id)
    return start


def log_route_end(route: str, request_id: str, start: float, ok_status: bool = True) -> None:
    elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)
    logger.info("[route:end] %s request_id=%s ok=%s duration_ms=%s", route, request_id, ok_status, elapsed_ms)
