from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from context_engine.index.manager import IndexManager
from context_engine.runtime.analyzer import RuntimeAnalyzer

from .models import (
    AndroidIntegrationSignal,
    AndroidManifestModel,
    AndroidModuleModel,
    AndroidRelationship,
    AndroidRetrievalContext,
    AndroidRetrievalSignal,
    AndroidRetrievalSignalSummary,
)
from .taxonomy import AndroidRelationshipType


ANDROID_LIFECYCLE_KEYWORDS = {
    "activity": "activity",
    "fragment": "fragment",
    "service": "service",
    "receiver": "receiver",
    "provider": "provider",
}


def build_android_retrieval_context(
    query: Any,
    index: IndexManager,
    runtime: Optional[RuntimeAnalyzer] = None,
    manifests: Optional[List[AndroidManifestModel]] = None,
    relationships: Optional[List[AndroidRelationship]] = None,
    modules: Optional[List[AndroidModuleModel]] = None,
    integration_signals: Optional[List[AndroidIntegrationSignal]] = None,
    enabled: bool = True,
    is_android_project: bool = True,
) -> AndroidRetrievalContext:
    active_file = (query.active_file or "").replace("\\", "/")
    if not active_file:
        return AndroidRetrievalContext(enabled=False, is_android_project=False)

    related_layouts = _collect_active_layout_refs(active_file, index)
    related_resources = _collect_active_resource_refs(active_file, index)
    active_module = _module_key(active_file)
    runtime_tags = sorted((runtime.get_android_runtime_tags() if runtime else []))
    integration_tags = sorted({signal.category for signal in (integration_signals or [])})
    integration_file_hints = sorted(
        {
            signal.file.replace("\\", "/")
            for signal in (integration_signals or [])
            if signal.file
        }
    )
    integration_module_hints = sorted(
        {
            signal.module
            for signal in (integration_signals or [])
            if signal.module
        }
    )

    active_components = _resolve_active_components(active_file, manifests or [])
    signals = _build_signals(
        query=query,
        active_file=active_file,
        active_module=active_module,
        active_components=active_components,
        related_layouts=related_layouts,
        related_resources=related_resources,
        runtime_tags=runtime_tags,
        integration_tags=integration_tags,
        integration_file_hints=integration_file_hints,
        integration_module_hints=integration_module_hints,
        relationships=relationships or [],
        modules=modules or [],
    )
    return AndroidRetrievalContext(
        enabled=enabled and is_android_project,
        is_android_project=is_android_project,
        active_module=active_module or None,
        active_component_candidates=active_components,
        related_layouts=related_layouts,
        related_resources=related_resources,
        runtime_tags=runtime_tags,
        integration_tags=integration_tags,
        integration_file_hints=integration_file_hints,
        integration_module_hints=integration_module_hints,
        signals=signals,
    )


def summarize_android_retrieval_signals(
    manifests: List[AndroidManifestModel],
    relationships: List[AndroidRelationship],
    modules: List[AndroidModuleModel],
    integration_signals: Optional[List[AndroidIntegrationSignal]] = None,
) -> AndroidRetrievalSignalSummary:
    signals: List[AndroidRetrievalSignal] = []
    component_count = sum(
        len(manifest.activities) + len(manifest.services) + len(manifest.receivers) + len(manifest.providers)
        for manifest in manifests
    )
    if component_count > 0:
        signals.append(
            AndroidRetrievalSignal(
                signal_type="manifest_component_density",
                weight=min(30.0, float(component_count) * 2.0),
                evidence=f"{component_count} Android components declared in manifests",
                source_artifact_ids=[f"manifest:{manifest.source_path}" for manifest in manifests],
            )
        )

    layout_rel_count = len(
        [
            rel for rel in relationships
            if rel.relationship_type == AndroidRelationshipType.LAYOUT_REFERENCES_RESOURCE.value
        ]
    )
    if layout_rel_count > 0:
        signals.append(
            AndroidRetrievalSignal(
                signal_type="layout_resource_connectivity",
                weight=min(24.0, float(layout_rel_count)),
                evidence=f"{layout_rel_count} layout→resource relationships found",
                source_artifact_ids=[],
            )
        )

    module_rel_count = len(
        [
            rel for rel in relationships
            if rel.relationship_type == AndroidRelationshipType.MODULE_DEPENDS_ON_MODULE.value
        ]
    )
    if module_rel_count > 0:
        signals.append(
            AndroidRetrievalSignal(
                signal_type="module_graph_density",
                weight=min(20.0, float(module_rel_count) * 2.0),
                evidence=f"{module_rel_count} module dependency edges found",
                source_artifact_ids=[f"module:{module.module_path}" for module in modules],
            )
        )

    if integration_signals:
        sources = sorted({signal.source for signal in integration_signals})
        categories = sorted({signal.category for signal in integration_signals})
        signals.append(
            AndroidRetrievalSignal(
                signal_type="integration_signal_presence",
                weight=min(12.0, 4.0 + float(len(categories))),
                evidence=(
                    f"{len(integration_signals)} optional integration signals from "
                    f"{', '.join(sources[:4])}"
                ),
                source_artifact_ids=[],
            )
        )

    signals = sorted(signals, key=lambda item: (-item.weight, item.signal_type, item.evidence))
    return AndroidRetrievalSignalSummary(
        count=len(signals),
        top_signals=signals[:6],
    )


def _collect_active_layout_refs(active_file: str, index: IndexManager) -> List[str]:
    names: Set[str] = set()
    for artifact in index.get_artifacts_for_file(active_file):
        if artifact.artifact_type == "ANDROID_LAYOUT_LINK":
            names.add(artifact.name)
    return sorted(names)


def _collect_active_resource_refs(active_file: str, index: IndexManager) -> List[str]:
    names: Set[str] = set()
    for artifact in index.get_artifacts_for_file(active_file):
        if artifact.artifact_type == "ANDROID_VIEW_ID_USAGE":
            names.add(artifact.name)
    return sorted(names)


def _resolve_active_components(active_file: str, manifests: List[AndroidManifestModel]) -> List[str]:
    file_name = Path(active_file).stem
    candidates: Set[str] = {file_name, f".{file_name}"}
    for manifest in manifests:
        for components in (manifest.activities, manifest.services, manifest.receivers, manifest.providers):
            for component in components:
                if component.name.endswith(file_name) or component.name.endswith("." + file_name):
                    candidates.add(component.name)
    return sorted(candidates)


def _build_signals(
    query: Any,
    active_file: str,
    active_module: str,
    active_components: List[str],
    related_layouts: List[str],
    related_resources: List[str],
    runtime_tags: List[str],
    integration_tags: List[str],
    integration_file_hints: List[str],
    integration_module_hints: List[str],
    relationships: List[AndroidRelationship],
    modules: List[AndroidModuleModel],
) -> List[AndroidRetrievalSignal]:
    signals: List[AndroidRetrievalSignal] = []
    if active_module:
        signals.append(
            AndroidRetrievalSignal(
                signal_type="module_locality",
                weight=16.0,
                evidence=f"Active file belongs to module '{active_module}'",
                source_artifact_ids=[f"module:{active_module}"],
            )
        )

    if active_file.lower().endswith("androidmanifest.xml"):
        signals.append(
            AndroidRetrievalSignal(
                signal_type="manifest_proximity",
                weight=12.0,
                evidence="Active file is AndroidManifest.xml",
                source_artifact_ids=[f"manifest:{active_file}"],
            )
        )

    if related_layouts:
        signals.append(
            AndroidRetrievalSignal(
                signal_type="layout_resource_bridge",
                weight=min(22.0, 10.0 + (len(related_layouts) * 4.0)),
                evidence=f"Active source references layouts: {', '.join(related_layouts[:3])}",
                source_artifact_ids=[f"layout:{name}" for name in related_layouts[:5]],
            )
        )

    if related_resources:
        signals.append(
            AndroidRetrievalSignal(
                signal_type="view_id_bridge",
                weight=min(14.0, 8.0 + (len(related_resources) * 2.0)),
                evidence=f"Active source references ids: {', '.join(related_resources[:4])}",
                source_artifact_ids=[f"view_id:{name}" for name in related_resources[:6]],
            )
        )

    task_lower = (query.task or "").lower()
    lifecycle_hits = sorted(
        {
            alias for key, alias in ANDROID_LIFECYCLE_KEYWORDS.items()
            if key in task_lower
        }
    )
    if lifecycle_hits:
        signals.append(
            AndroidRetrievalSignal(
                signal_type="lifecycle_hint",
                weight=10.0 + float(len(lifecycle_hits)),
                evidence=f"Task mentions lifecycle concepts: {', '.join(lifecycle_hits)}",
                source_artifact_ids=[],
            )
        )

    if active_components:
        signals.append(
            AndroidRetrievalSignal(
                signal_type="component_linkage",
                weight=min(18.0, 8.0 + float(len(active_components))),
                evidence=f"Active file maps to component candidates: {', '.join(active_components[:3])}",
                source_artifact_ids=[f"component:{name}" for name in active_components[:6]],
            )
        )

    if runtime_tags:
        signals.append(
            AndroidRetrievalSignal(
                signal_type="runtime_hint",
                weight=min(16.0, 6.0 + float(len(runtime_tags))),
                evidence=f"Runtime tags available: {', '.join(runtime_tags[:4])}",
                source_artifact_ids=[],
            )
        )

    if integration_tags:
        signals.append(
            AndroidRetrievalSignal(
                signal_type="integration_hint",
                weight=min(12.0, 4.0 + float(len(integration_tags))),
                evidence=f"Optional integration tags available: {', '.join(integration_tags[:4])}",
                source_artifact_ids=[],
            )
        )
    if integration_file_hints:
        signals.append(
            AndroidRetrievalSignal(
                signal_type="integration_file_hint",
                weight=min(10.0, 4.0 + float(len(integration_file_hints))),
                evidence=f"Integration file hints: {', '.join(integration_file_hints[:3])}",
                source_artifact_ids=[],
            )
        )
    if integration_module_hints:
        signals.append(
            AndroidRetrievalSignal(
                signal_type="integration_module_hint",
                weight=min(8.0, 3.0 + float(len(integration_module_hints))),
                evidence=f"Integration module hints: {', '.join(integration_module_hints[:4])}",
                source_artifact_ids=[],
            )
        )

    if relationships:
        module_edges = len(
            [
                rel for rel in relationships
                if rel.relationship_type == AndroidRelationshipType.MODULE_DEPENDS_ON_MODULE.value
            ]
        )
        if module_edges > 0:
            signals.append(
                AndroidRetrievalSignal(
                    signal_type="module_traversal_ready",
                    weight=min(10.0, float(module_edges)),
                    evidence=f"{module_edges} module dependency edges available for traversal",
                    source_artifact_ids=[],
                )
            )

    if modules:
        signals.append(
            AndroidRetrievalSignal(
                signal_type="android_modules_present",
                weight=min(8.0, float(len(modules)) * 2.0),
                evidence=f"{len(modules)} Android modules discovered",
                source_artifact_ids=[f"module:{module.module_path}" for module in modules[:6]],
            )
        )

    return sorted(signals, key=lambda item: (-item.weight, item.signal_type, item.evidence))


def _module_key(path: str) -> str:
    normalized = path.replace("\\", "/").strip("/")
    parts = normalized.split("/")
    if len(parts) >= 2 and parts[1] == "src":
        return parts[0]
    if normalized.endswith("build.gradle") or normalized.endswith("build.gradle.kts"):
        return parts[0] if len(parts) > 1 else "root"
    return parts[0] if parts else ""
