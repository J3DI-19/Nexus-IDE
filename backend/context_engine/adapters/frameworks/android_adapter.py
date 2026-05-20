import re
from typing import List
import xml.etree.ElementTree as ET

from ..base import FrameworkAdapter
from ...models.artifact import FrameworkArtifact


LAYOUT_PATH_RE = re.compile(r"/res/layout/([^/]+)\.xml$", re.IGNORECASE)
SET_CONTENT_VIEW_RE = re.compile(r"setContentView\s*\(\s*R\.layout\.([A-Za-z0-9_]+)\s*\)")
INFLATE_RE = re.compile(r"inflate\s*\(\s*R\.layout\.([A-Za-z0-9_]+)")
VIEW_ID_RE = re.compile(r"R\.id\.([A-Za-z0-9_]+)")
PLUGIN_ID_RE = re.compile(r"id\s*\(?\s*[\"']([A-Za-z0-9_.-]+)[\"']\s*\)?")
PROJECT_DEP_RE = re.compile(r"project\s*\(\s*[\"'](:[A-Za-z0-9:_-]+)[\"']\s*\)")


class AndroidAdapter(FrameworkAdapter):
    def can_handle(self, rel_path: str) -> bool:
        lower = rel_path.lower()
        if "/res/layout/" in lower and lower.endswith(".xml"):
            return True
        if lower.endswith(".kt") or lower.endswith(".kts") or lower.endswith(".java"):
            return True
        if lower.endswith("build.gradle") or lower.endswith("build.gradle.kts"):
            return True
        return False

    def extract_artifacts(self, content: str, file_path: str) -> List[FrameworkArtifact]:
        artifacts: List[FrameworkArtifact] = []
        lower = file_path.lower()
        if "/res/layout/" in lower and lower.endswith(".xml"):
            artifacts.extend(self._extract_layout_artifacts(content, file_path))
        if lower.endswith(".kt") or lower.endswith(".kts") or lower.endswith(".java"):
            artifacts.extend(self._extract_source_artifacts(content, file_path))
        if lower.endswith("build.gradle") or lower.endswith("build.gradle.kts"):
            artifacts.extend(self._extract_gradle_artifacts(content, file_path))
        return artifacts

    def _extract_layout_artifacts(self, content: str, file_path: str) -> List[FrameworkArtifact]:
        artifacts: List[FrameworkArtifact] = []
        match = LAYOUT_PATH_RE.search(file_path.replace("\\", "/"))
        if not match:
            return artifacts
        layout_name = match.group(1)
        artifacts.append(
            FrameworkArtifact(
                artifact_type="ANDROID_LAYOUT",
                name=layout_name,
                rel_path=file_path,
                start_line=1,
                end_line=max(1, len(content.splitlines())),
                metadata={},
            )
        )

        try:
            root = ET.fromstring(content)
        except ET.ParseError:
            return artifacts

        ns = "{http://schemas.android.com/apk/res/android}"
        for element in root.iter():
            element_id = element.attrib.get(f"{ns}id")
            if element_id and (element_id.startswith("@+id/") or element_id.startswith("@id/")):
                artifacts.append(
                    FrameworkArtifact(
                        artifact_type="ANDROID_VIEW_ID",
                        name=element_id.split("/", 1)[1],
                        rel_path=file_path,
                        start_line=1,
                        end_line=1,
                        metadata={},
                    )
                )
        return artifacts

    def _extract_source_artifacts(self, content: str, file_path: str) -> List[FrameworkArtifact]:
        artifacts: List[FrameworkArtifact] = []
        for layout_name in sorted(set(SET_CONTENT_VIEW_RE.findall(content))):
            artifacts.append(
                FrameworkArtifact(
                    artifact_type="ANDROID_LAYOUT_LINK",
                    name=layout_name,
                    rel_path=file_path,
                    start_line=1,
                    end_line=1,
                    metadata={"usage": "setContentView"},
                )
            )
        for layout_name in sorted(set(INFLATE_RE.findall(content))):
            artifacts.append(
                FrameworkArtifact(
                    artifact_type="ANDROID_LAYOUT_LINK",
                    name=layout_name,
                    rel_path=file_path,
                    start_line=1,
                    end_line=1,
                    metadata={"usage": "inflate"},
                )
            )
        for view_id in sorted(set(VIEW_ID_RE.findall(content))):
            artifacts.append(
                FrameworkArtifact(
                    artifact_type="ANDROID_VIEW_ID_USAGE",
                    name=view_id,
                    rel_path=file_path,
                    start_line=1,
                    end_line=1,
                    metadata={},
                )
            )
        if "@Composable" in content or "setContent {" in content:
            artifacts.append(
                FrameworkArtifact(
                    artifact_type="ANDROID_COMPOSE_SIGNAL",
                    name="compose",
                    rel_path=file_path,
                    start_line=1,
                    end_line=1,
                    metadata={},
                )
            )
        if "DataBindingUtil" in content or "Binding.inflate(" in content:
            artifacts.append(
                FrameworkArtifact(
                    artifact_type="ANDROID_BINDING_SIGNAL",
                    name="binding",
                    rel_path=file_path,
                    start_line=1,
                    end_line=1,
                    metadata={},
                )
            )
        return artifacts

    def _extract_gradle_artifacts(self, content: str, file_path: str) -> List[FrameworkArtifact]:
        artifacts: List[FrameworkArtifact] = []
        for plugin in sorted(set(PLUGIN_ID_RE.findall(content))):
            if not plugin.startswith("com.android"):
                continue
            artifacts.append(
                FrameworkArtifact(
                    artifact_type="ANDROID_PLUGIN",
                    name=plugin,
                    rel_path=file_path,
                    start_line=1,
                    end_line=1,
                    metadata={},
                )
            )
        for module_dep in sorted(set(PROJECT_DEP_RE.findall(content))):
            artifacts.append(
                FrameworkArtifact(
                    artifact_type="ANDROID_MODULE_DEP",
                    name=module_dep,
                    rel_path=file_path,
                    start_line=1,
                    end_line=1,
                    metadata={},
                )
            )
        return artifacts
