from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("nexus.executor_formats")

EXECUTOR_RESPONSE_FORMATS = {"nexus_patch_v1", "unified_diff", "json_edits"}
DEFAULT_EXECUTOR_RESPONSE_FORMAT = "nexus_patch_v1"
LEGACY_EXECUTOR_RESPONSE_FORMATS = {
    "nexus_edits_v2": "json_edits",
}


def resolve_executor_response_format(value: Optional[str]) -> str:
    raw = (value or "").strip()
    if not raw:
        return DEFAULT_EXECUTOR_RESPONSE_FORMAT
    normalized = LEGACY_EXECUTOR_RESPONSE_FORMATS.get(raw, raw)
    if normalized in EXECUTOR_RESPONSE_FORMATS:
        return normalized
    logger.warning("Invalid executor_response_format=%r; using %s", value, DEFAULT_EXECUTOR_RESPONSE_FORMAT)
    return DEFAULT_EXECUTOR_RESPONSE_FORMAT


def is_json_edits_format(value: Optional[str]) -> bool:
    return resolve_executor_response_format(value) == "json_edits"


def validate_executor_response_format(value: Optional[str]) -> str:
    raw = (value or "").strip()
    normalized = LEGACY_EXECUTOR_RESPONSE_FORMATS.get(raw, raw)
    if normalized in EXECUTOR_RESPONSE_FORMATS:
        return normalized
    raise ValueError(f"Unsupported executor_response_format: {value}")
