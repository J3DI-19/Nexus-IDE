import re
from pathlib import Path
from typing import Dict, List, Set, Tuple

from .models import AndroidBindingSignal, AndroidComposeSignal, AndroidDiagnostic, AndroidUiLink
from .taxonomy import AndroidRelationshipType


LAYOUT_SET_CONTENT_RE = re.compile(r"setContentView\s*\(\s*R\.layout\.([A-Za-z0-9_]+)\s*\)")
LAYOUT_INFLATE_RE = re.compile(r"inflate\s*\(\s*R\.layout\.([A-Za-z0-9_]+)")
VIEW_ID_RE = re.compile(r"R\.id\.([A-Za-z0-9_]+)")
CLASS_RE = re.compile(r"\b(class|interface)\s+([A-Za-z_][A-Za-z0-9_]*)")
VIEW_BINDING_RE = re.compile(r"\b([A-Za-z0-9_]*Binding)\.inflate\s*\(")
DATA_BINDING_RE = re.compile(r"\bDataBindingUtil\b")
COMPOSABLE_RE = re.compile(r"@Composable\b")
SET_CONTENT_RE = re.compile(r"\bsetContent\s*\{")


def extract_android_ui_links(
    root_path: Path,
    source_paths: List[str],
    component_index: Dict[str, str],
    available_layouts: Set[str],
) -> Tuple[List[AndroidUiLink], List[AndroidComposeSignal], List[AndroidBindingSignal], List[AndroidDiagnostic]]:
    links: List[AndroidUiLink] = []
    compose_signals: List[AndroidComposeSignal] = []
    binding_signals: List[AndroidBindingSignal] = []
    diagnostics: List[AndroidDiagnostic] = []

    for rel_path in sorted(set(source_paths)):
        if not _is_android_source_file(rel_path):
            continue
        abs_path = root_path / rel_path
        try:
            content = abs_path.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            diagnostics.append(
                AndroidDiagnostic(
                    severity="warning",
                    code="android_source_read_error",
                    message="Could not read Android source file for UI linking.",
                    source_path=rel_path,
                    details=str(exc),
                )
            )
            continue

        class_name = _extract_primary_class_name(content) or Path(rel_path).stem
        fqcn_candidates = _build_component_candidates(class_name, content)
        component_name = _resolve_component_name(fqcn_candidates, component_index)
        component_id = f"component_source:{rel_path}:{class_name}"

        for layout_name in sorted(set(LAYOUT_SET_CONTENT_RE.findall(content))):
            if layout_name in available_layouts:
                links.append(
                    AndroidUiLink(
                        link_type=AndroidRelationshipType.COMPONENT_USES_LAYOUT.value,
                        source_id=component_name or component_id,
                        target_id=f"layout:{layout_name}",
                        source_path=rel_path,
                        metadata={"usage": "setContentView"},
                    )
                )

        for layout_name in sorted(set(LAYOUT_INFLATE_RE.findall(content))):
            if layout_name in available_layouts:
                links.append(
                    AndroidUiLink(
                        link_type=AndroidRelationshipType.COMPONENT_USES_LAYOUT.value,
                        source_id=component_name or component_id,
                        target_id=f"layout:{layout_name}",
                        source_path=rel_path,
                        metadata={"usage": "inflate"},
                    )
                )

        for view_id in sorted(set(VIEW_ID_RE.findall(content))):
            links.append(
                AndroidUiLink(
                    link_type=AndroidRelationshipType.COMPONENT_USES_VIEW_ID.value,
                    source_id=component_name or component_id,
                    target_id=f"view_id:{view_id}",
                    source_path=rel_path,
                )
            )

        compose_evidence: List[str] = []
        if COMPOSABLE_RE.search(content):
            compose_evidence.append("@Composable")
        if SET_CONTENT_RE.search(content):
            compose_evidence.append("setContent {}")
        if compose_evidence:
            compose_signals.append(
                AndroidComposeSignal(
                    source_path=rel_path,
                    confidence=0.8 if len(compose_evidence) > 1 else 0.6,
                    evidence=sorted(compose_evidence),
                )
            )
            links.append(
                AndroidUiLink(
                    link_type=AndroidRelationshipType.COMPONENT_USES_COMPOSE.value,
                    source_id=component_name or component_id,
                    target_id="compose:ui",
                    source_path=rel_path,
                    metadata={"evidence": ",".join(sorted(compose_evidence))},
                )
            )

        for binding_class in sorted(set(VIEW_BINDING_RE.findall(content))):
            binding_signals.append(
                AndroidBindingSignal(
                    source_path=rel_path,
                    binding_type="view_binding",
                    class_name=binding_class,
                    confidence=0.8,
                    evidence=["Binding.inflate(...)"],
                )
            )

        if DATA_BINDING_RE.search(content):
            binding_signals.append(
                AndroidBindingSignal(
                    source_path=rel_path,
                    binding_type="data_binding",
                    class_name=None,
                    confidence=0.75,
                    evidence=["DataBindingUtil"],
                )
            )

    links = sorted(
        links,
        key=lambda item: (item.link_type, item.source_id, item.target_id, item.source_path or ""),
    )
    compose_signals = sorted(compose_signals, key=lambda item: item.source_path)
    binding_signals = sorted(
        binding_signals,
        key=lambda item: (item.binding_type, item.source_path, item.class_name or ""),
    )
    return links, compose_signals, binding_signals, diagnostics


def _is_android_source_file(rel_path: str) -> bool:
    lower = rel_path.lower()
    return lower.endswith(".kt") or lower.endswith(".kts") or lower.endswith(".java")


def _extract_primary_class_name(content: str) -> str:
    match = CLASS_RE.search(content)
    if not match:
        return ""
    return match.group(2)


def _extract_package_name(content: str) -> str:
    match = re.search(r"^\s*package\s+([A-Za-z0-9_.]+)\s*$", content, re.MULTILINE)
    if not match:
        return ""
    return match.group(1)


def _build_component_candidates(class_name: str, content: str) -> List[str]:
    if not class_name:
        return []
    package_name = _extract_package_name(content)
    candidates = [class_name, f".{class_name}"]
    if package_name:
        candidates.append(f"{package_name}.{class_name}")
    return candidates


def _resolve_component_name(candidates: List[str], component_index: Dict[str, str]) -> str:
    for candidate in candidates:
        if candidate in component_index:
            return component_index[candidate]
    return ""
