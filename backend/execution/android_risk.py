from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List


class AndroidRiskClass(str, Enum):
    MANIFEST = "manifest"
    LAYOUT_RESOURCE = "layout_resource"
    GRADLE_MODULE = "gradle_module"
    SOURCE_LINK = "source_link"
    NON_ANDROID = "non_android"


@dataclass
class AndroidRiskTarget:
    path: str
    op: str
    risk_class: AndroidRiskClass
    module_key: str
    is_deleted: bool
    reasons: List[str] = field(default_factory=list)


def classify_android_patch_targets(applied_changes: List[Any]) -> List[AndroidRiskTarget]:
    targets: List[AndroidRiskTarget] = []
    for change in applied_changes:
        rel_path = str(getattr(change, "path", "")).replace("\\", "/").strip()
        if not rel_path:
            continue
        op = str(getattr(change, "operation", "unknown"))
        content = getattr(change, "content", None)
        is_deleted = content is None or op == "delete_file"
        risk_class, reasons = _classify_path(rel_path, op)
        module_key = _module_from_path(rel_path)
        targets.append(
            AndroidRiskTarget(
                path=rel_path,
                op=op,
                risk_class=risk_class,
                module_key=module_key,
                is_deleted=is_deleted,
                reasons=reasons,
            )
        )
    return sorted(targets, key=lambda item: (item.risk_class.value, item.path, item.op))


def _classify_path(path: str, op: str) -> tuple[AndroidRiskClass, List[str]]:
    lower = path.lower()
    reasons: List[str] = []
    if lower.endswith("androidmanifest.xml"):
        reasons.append("manifest_path")
        return AndroidRiskClass.MANIFEST, reasons

    if lower.endswith("settings.gradle") or lower.endswith("settings.gradle.kts"):
        reasons.append("gradle_settings")
        return AndroidRiskClass.GRADLE_MODULE, reasons
    if lower.endswith("build.gradle") or lower.endswith("build.gradle.kts"):
        reasons.append("gradle_build")
        return AndroidRiskClass.GRADLE_MODULE, reasons

    if "/res/layout/" in lower and lower.endswith(".xml"):
        reasons.append("layout_xml")
        return AndroidRiskClass.LAYOUT_RESOURCE, reasons
    if "/res/values/" in lower and lower.endswith(".xml"):
        reasons.append("values_xml")
        return AndroidRiskClass.LAYOUT_RESOURCE, reasons
    if "/res/menu/" in lower and lower.endswith(".xml"):
        reasons.append("menu_xml")
        return AndroidRiskClass.LAYOUT_RESOURCE, reasons
    if "/res/navigation/" in lower and lower.endswith(".xml"):
        reasons.append("navigation_xml")
        return AndroidRiskClass.LAYOUT_RESOURCE, reasons

    if lower.endswith(".kt") or lower.endswith(".java"):
        reasons.append("android_source_extension")
        return AndroidRiskClass.SOURCE_LINK, reasons

    return AndroidRiskClass.NON_ANDROID, reasons


def _module_from_path(path: str) -> str:
    normalized = path.replace("\\", "/").strip("/")
    parts = normalized.split("/")
    if not parts:
        return ""
    if len(parts) >= 2 and parts[1] == "src":
        return parts[0]
    return parts[0]
