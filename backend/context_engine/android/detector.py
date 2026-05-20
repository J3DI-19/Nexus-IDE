from dataclasses import dataclass, field
from pathlib import Path
from typing import List
from typing import Optional


ANDROID_PLUGIN_MARKERS = (
    "com.android.application",
    "com.android.library",
    "com.android.dynamic-feature",
    "com.android.test",
    "com.android.instantapp",
)


@dataclass
class AndroidDetectionResult:
    is_android_project: bool
    reasons: List[str] = field(default_factory=list)


def detect_android_project(root_path: Path, all_files: List[str]) -> AndroidDetectionResult:
    reasons: List[str] = []
    normalized = sorted({path.replace("\\", "/") for path in all_files})

    manifest_paths = [path for path in normalized if path.endswith("AndroidManifest.xml")]
    if manifest_paths:
        reasons.append(f"manifest_present:{manifest_paths[0]}")

    app_src_main_paths = [path for path in normalized if path.endswith("app/src/main/")]
    if app_src_main_paths:
        reasons.append(f"app_src_main_present:{app_src_main_paths[0]}")

    gradle_files = [
        path for path in normalized
        if path.endswith("build.gradle") or path.endswith("build.gradle.kts")
    ]
    plugin_reason = _detect_gradle_android_plugin(root_path, gradle_files)
    if plugin_reason:
        reasons.append(plugin_reason)

    return AndroidDetectionResult(
        is_android_project=bool(reasons),
        reasons=reasons,
    )


def _detect_gradle_android_plugin(root_path: Path, gradle_files: List[str]) -> Optional[str]:
    for rel_path in gradle_files:
        abs_path = root_path / rel_path
        try:
            content = abs_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        lowered = content.lower()
        for marker in ANDROID_PLUGIN_MARKERS:
            if marker in lowered:
                return f"gradle_android_plugin:{rel_path}:{marker}"
    return None
