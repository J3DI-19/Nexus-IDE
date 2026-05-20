from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from .verifiers.base import VerificationDiagnostic, VerificationMode


@dataclass
class AndroidVerificationConfig:
    mode: str = "auto"  # auto | on | off
    check_manifest: bool = True
    check_layout_resource: bool = True
    check_gradle_module: bool = True
    check_source_link: bool = True
    config_source: str = "default"


@dataclass
class ExecutorVerificationConfig:
    mode: VerificationMode = VerificationMode.WARN
    android: AndroidVerificationConfig = field(default_factory=AndroidVerificationConfig)
    diagnostics: list[VerificationDiagnostic] = field(default_factory=list)


def load_executor_verification_config(project_root: Path) -> ExecutorVerificationConfig:
    config_path = project_root / "nexus.toml"
    if not config_path.exists():
        return ExecutorVerificationConfig(mode=VerificationMode.WARN)

    try:
        raw_text = config_path.read_text(encoding="utf-8")
    except Exception as exc:
        return ExecutorVerificationConfig(
            mode=VerificationMode.WARN,
            diagnostics=[
                VerificationDiagnostic(
                    severity="warning",
                    code="invalid_verification_mode_config",
                    message="Failed to read nexus.toml; using WARN verification mode.",
                    path=str(config_path),
                    details=str(exc),
                )
            ],
        )

    values = _read_executor_section_values(raw_text)
    diagnostics: list[VerificationDiagnostic] = []

    mode_value = values.get("verification_mode")
    if mode_value is None:
        mode = VerificationMode.WARN
    else:
        normalized_mode = mode_value.strip().strip("\"'").lower()
        if normalized_mode not in {m.value for m in VerificationMode}:
            diagnostics.append(
                VerificationDiagnostic(
                    severity="warning",
                    code="invalid_verification_mode_config",
                    message=f"Unsupported verification_mode='{mode_value}'. Falling back to WARN.",
                    path=str(config_path),
                )
            )
            mode = VerificationMode.WARN
        else:
            mode = VerificationMode(normalized_mode)

    android_config = _parse_android_verification_config(values, config_path, diagnostics)
    if values:
        android_config.config_source = "nexus_toml"
    return ExecutorVerificationConfig(mode=mode, android=android_config, diagnostics=diagnostics)


def _read_executor_section_values(raw_text: str) -> Dict[str, str]:
    in_executor = False
    values: Dict[str, str] = {}
    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1].strip().lower()
            in_executor = section == "executor"
            continue
        if not in_executor:
            continue

        body = stripped.split("#", 1)[0].strip()
        if "=" not in body:
            continue
        key, value = body.split("=", 1)
        values[key.strip().lower()] = value.strip()
    return values


def _parse_android_verification_config(
    values: Dict[str, str],
    config_path: Path,
    diagnostics: list[VerificationDiagnostic],
) -> AndroidVerificationConfig:
    cfg = AndroidVerificationConfig()
    mode_raw = values.get("android_verification")
    if mode_raw is not None:
        normalized = mode_raw.strip().strip("\"'").lower()
        if normalized not in {"auto", "on", "off"}:
            diagnostics.append(
                VerificationDiagnostic(
                    severity="warning",
                    code="invalid_android_verification_config",
                    message=f"Unsupported android_verification='{mode_raw}'. Falling back to auto.",
                    path=str(config_path),
                )
            )
        else:
            cfg.mode = normalized

    cfg.check_manifest = _parse_bool_option(
        values,
        "android_check_manifest",
        cfg.check_manifest,
        config_path,
        diagnostics,
    )
    cfg.check_layout_resource = _parse_bool_option(
        values,
        "android_check_layout_resource",
        cfg.check_layout_resource,
        config_path,
        diagnostics,
    )
    cfg.check_gradle_module = _parse_bool_option(
        values,
        "android_check_gradle_module",
        cfg.check_gradle_module,
        config_path,
        diagnostics,
    )
    cfg.check_source_link = _parse_bool_option(
        values,
        "android_check_source_link",
        cfg.check_source_link,
        config_path,
        diagnostics,
    )
    return cfg


def _parse_bool_option(
    values: Dict[str, str],
    key: str,
    default: bool,
    config_path: Path,
    diagnostics: list[VerificationDiagnostic],
) -> bool:
    raw_value = values.get(key)
    if raw_value is None:
        return default
    normalized = raw_value.strip().strip("\"'").lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    diagnostics.append(
        VerificationDiagnostic(
            severity="warning",
            code="invalid_android_verification_config",
            message=f"Unsupported {key}='{raw_value}'. Falling back to {str(default).lower()}.",
            path=str(config_path),
        )
    )
    return default
