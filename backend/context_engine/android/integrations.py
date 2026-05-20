from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .models import AndroidDiagnostic, AndroidIntegrationSignal, AndroidIntegrationsSummary


@dataclass
class AndroidIntegrationsConfig:
    enabled: bool = False
    source_files: Dict[str, str] = field(default_factory=dict)
    diagnostics: List[AndroidDiagnostic] = field(default_factory=list)


_SOURCE_KEY_MAP = {
    "adb_log_file": "adb",
    "emulator_status_file": "emulator",
    "studio_events_file": "studio",
    "ci_report_file": "ci",
}


def load_android_integrations_summary(project_root: Path) -> AndroidIntegrationsSummary:
    config_path = project_root / "nexus.toml"
    config = _read_android_integrations_config(config_path)
    if not config.enabled:
        return AndroidIntegrationsSummary(
            enabled=False,
            configured_sources=sorted(config.source_files.keys()),
            signals=[],
            diagnostics=sorted(config.diagnostics, key=lambda item: (item.code, item.source_path or "")),
        )

    signals: List[AndroidIntegrationSignal] = []
    diagnostics: List[AndroidDiagnostic] = list(config.diagnostics)
    configured_sources = sorted(config.source_files.keys())

    for source in configured_sources:
        rel_path = config.source_files[source]
        file_path = (project_root / rel_path).resolve()
        if not file_path.exists():
            diagnostics.append(
                AndroidDiagnostic(
                    severity="warning",
                    code="android_integration_source_missing",
                    message=f"Configured Android integration source file is missing for '{source}'.",
                    source_path=rel_path,
                )
            )
            continue
        parsed_signals, parse_diagnostics = _parse_source_file(source=source, file_path=file_path, source_path=rel_path)
        signals.extend(parsed_signals)
        diagnostics.extend(parse_diagnostics)

    return AndroidIntegrationsSummary(
        enabled=True,
        configured_sources=configured_sources,
        signals=sorted(
            signals,
            key=lambda item: (
                item.source,
                item.category,
                item.severity,
                item.module or "",
                item.file or "",
                item.line or 0,
                item.message,
            ),
        )[:30],
        diagnostics=sorted(diagnostics, key=lambda item: (item.code, item.source_path or "", item.message)),
    )


def _read_android_integrations_config(config_path: Path) -> AndroidIntegrationsConfig:
    if not config_path.exists():
        return AndroidIntegrationsConfig(enabled=False)

    try:
        raw_text = config_path.read_text(encoding="utf-8")
    except Exception as exc:
        return AndroidIntegrationsConfig(
            enabled=False,
            diagnostics=[
                AndroidDiagnostic(
                    severity="warning",
                    code="invalid_android_integrations_config",
                    message="Failed to read nexus.toml for Android integrations.",
                    source_path=str(config_path),
                    details=str(exc),
                )
            ],
        )

    section = _read_section(raw_text, "android_integrations")
    if not section:
        return AndroidIntegrationsConfig(enabled=False)

    enabled_raw = section.get("enabled", "false").strip().strip("\"'").lower()
    enabled = enabled_raw == "true"
    if enabled_raw not in {"true", "false"}:
        return AndroidIntegrationsConfig(
            enabled=False,
            diagnostics=[
                AndroidDiagnostic(
                    severity="warning",
                    code="invalid_android_integrations_config",
                    message=f"Unsupported android_integrations.enabled='{section.get('enabled')}'. Expected true/false.",
                    source_path=str(config_path),
                )
            ],
        )

    source_files: Dict[str, str] = {}
    for key, source in _SOURCE_KEY_MAP.items():
        raw_value = section.get(key)
        if not raw_value:
            continue
        normalized = raw_value.strip().strip("\"'")
        if normalized:
            source_files[source] = normalized.replace("\\", "/")
    return AndroidIntegrationsConfig(enabled=enabled, source_files=source_files)


def _read_section(raw_text: str, section_name: str) -> Dict[str, str]:
    in_section = False
    values: Dict[str, str] = {}
    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            in_section = stripped[1:-1].strip().lower() == section_name.lower()
            continue
        if not in_section:
            continue
        body = stripped.split("#", 1)[0].strip()
        if "=" not in body:
            continue
        key, value = body.split("=", 1)
        values[key.strip().lower()] = value.strip()
    return values


def _parse_source_file(source: str, file_path: Path, source_path: str) -> tuple[List[AndroidIntegrationSignal], List[AndroidDiagnostic]]:
    diagnostics: List[AndroidDiagnostic] = []
    signals: List[AndroidIntegrationSignal] = []
    try:
        raw_text = file_path.read_text(encoding="utf-8")
    except Exception as exc:
        diagnostics.append(
            AndroidDiagnostic(
                severity="warning",
                code="android_integration_source_read_error",
                message=f"Failed to read Android integration source '{source}'.",
                source_path=source_path,
                details=str(exc),
            )
        )
        return signals, diagnostics

    suffix = file_path.suffix.lower()
    if suffix == ".json":
        try:
            payload = json.loads(raw_text)
        except Exception as exc:
            diagnostics.append(
                AndroidDiagnostic(
                    severity="warning",
                    code="android_integration_source_parse_error",
                    message=f"Invalid JSON in Android integration source '{source}'.",
                    source_path=source_path,
                    details=str(exc),
                )
            )
            return signals, diagnostics
        return _parse_json_signals(source, source_path, payload), diagnostics

    for idx, line in enumerate(raw_text.splitlines(), start=1):
        clean = line.strip()
        if not clean:
            continue
        signals.append(
            AndroidIntegrationSignal(
                source=source,
                category=f"{source}_text_signal",
                severity="info",
                message=clean[:240],
                line=idx,
                evidence=source_path,
            )
        )
        if len(signals) >= 20:
            break
    return signals, diagnostics


def _parse_json_signals(source: str, source_path: str, payload: object) -> List[AndroidIntegrationSignal]:
    signals: List[AndroidIntegrationSignal] = []

    def add_signal(item: dict):
        message = str(item.get("message", "")).strip()
        if not message:
            return
        line_value = item.get("line")
        line = int(line_value) if isinstance(line_value, int) else None
        signals.append(
            AndroidIntegrationSignal(
                source=source,
                category=str(item.get("category", f"{source}_json_signal")),
                severity=str(item.get("severity", "info")),
                message=message[:240],
                module=str(item.get("module")) if item.get("module") is not None else None,
                file=str(item.get("file")) if item.get("file") is not None else None,
                line=line,
                evidence=source_path,
            )
        )

    if isinstance(payload, list):
        for entry in payload:
            if isinstance(entry, dict):
                add_signal(entry)
    elif isinstance(payload, dict):
        if isinstance(payload.get("signals"), list):
            for entry in payload.get("signals", []):
                if isinstance(entry, dict):
                    add_signal(entry)
        else:
            add_signal(payload)
    return signals[:20]
