from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .models import AndroidDiagnostic


@dataclass
class AndroidFeatureConfig:
    explicit_enabled: Optional[bool] = None
    effective_enabled: bool = False
    source: str = "auto_detection"
    diagnostics: list[AndroidDiagnostic] = field(default_factory=list)


def resolve_android_feature_config(project_root: Path, is_android_project: bool) -> AndroidFeatureConfig:
    config_path = project_root / "nexus.toml"
    if not config_path.exists():
        return AndroidFeatureConfig(
            explicit_enabled=None,
            effective_enabled=is_android_project,
            source="auto_detection",
        )

    try:
        raw_text = config_path.read_text(encoding="utf-8")
    except Exception as exc:
        return AndroidFeatureConfig(
            explicit_enabled=None,
            effective_enabled=is_android_project,
            source="auto_detection",
            diagnostics=[
                AndroidDiagnostic(
                    severity="warning",
                    code="invalid_android_feature_config",
                    message="Failed to read nexus.toml; falling back to auto Android feature detection.",
                    source_path=str(config_path),
                    details=str(exc),
                )
            ],
        )

    raw_value = _read_android_feature_flag(raw_text)
    if raw_value is None:
        return AndroidFeatureConfig(
            explicit_enabled=None,
            effective_enabled=is_android_project,
            source="auto_detection",
        )

    normalized = raw_value.strip().strip("\"'").lower()
    if normalized == "true":
        return AndroidFeatureConfig(
            explicit_enabled=True,
            effective_enabled=True,
            source="config",
        )
    if normalized == "false":
        return AndroidFeatureConfig(
            explicit_enabled=False,
            effective_enabled=False,
            source="config",
        )

    return AndroidFeatureConfig(
        explicit_enabled=None,
        effective_enabled=is_android_project,
        source="auto_detection",
        diagnostics=[
            AndroidDiagnostic(
                severity="warning",
                code="invalid_android_feature_config",
                message=f"Unsupported android_intelligence_v1='{raw_value}'. Falling back to auto detection.",
                source_path=str(config_path),
            )
        ],
    )


def _read_android_feature_flag(raw_text: str) -> Optional[str]:
    in_features = False
    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1].strip().lower()
            in_features = section == "features"
            continue
        if not in_features:
            continue
        body = stripped.split("#", 1)[0].strip()
        if "=" not in body:
            continue
        key, value = body.split("=", 1)
        if key.strip().lower() == "android_intelligence_v1":
            return value.strip()
    return None
