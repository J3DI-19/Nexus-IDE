from pathlib import Path
from typing import Dict, List, Optional, Set

from context_engine.core.scanner import fast_recursive_scan
from context_engine.runtime.analyzer import RuntimeAnalyzer

from .config import resolve_android_feature_config
from .detector import detect_android_project
from .gradle_parser import analyze_gradle_project
from .integrations import load_android_integrations_summary
from .manifest_parser import parse_android_manifest
from .models import (
    AndroidBindingSignal,
    AndroidComposeSignal,
    AndroidDiagnostic,
    AndroidGradleModel,
    AndroidLayoutModel,
    AndroidManifestModel,
    AndroidModuleModel,
    AndroidProjectModel,
    AndroidRelationship,
    AndroidSummaryResponse,
    AndroidUiLink,
    AndroidUiSummary,
    AndroidRuntimeSignalsSummary,
)
from .retrieval import summarize_android_retrieval_signals
from .source_linker import extract_android_ui_links
from .taxonomy import AndroidRelationshipType
from .ui_parser import parse_layout_xml


def get_android_summary(project_root: Path, runtime_analyzer: Optional[RuntimeAnalyzer] = None) -> AndroidSummaryResponse:
    root = project_root.resolve()
    all_paths = fast_recursive_scan(str(root), include_dirs=True)
    file_paths = sorted(path.replace("\\", "/") for path in all_paths if not path.endswith("/"))

    detection = detect_android_project(root, all_paths)
    feature_config = resolve_android_feature_config(root, detection.is_android_project)

    manifests: List[AndroidManifestModel] = []
    layouts: List[AndroidLayoutModel] = []
    ui_links: List[AndroidUiLink] = []
    compose_signals: List[AndroidComposeSignal] = []
    binding_signals: List[AndroidBindingSignal] = []
    relationships: List[AndroidRelationship] = []
    integration_summary = load_android_integrations_summary(root)
    retrieval_signals = summarize_android_retrieval_signals([], [], [], integration_signals=integration_summary.signals)
    modules: List[AndroidModuleModel] = []
    gradle: AndroidGradleModel = AndroidGradleModel()
    diagnostics: List[AndroidDiagnostic] = list(feature_config.diagnostics)
    runtime_summary = AndroidRuntimeSignalsSummary()
    diagnostics.extend(integration_summary.diagnostics)

    if feature_config.effective_enabled and detection.is_android_project:
        manifest_paths = _select_manifest_paths(file_paths)
        for rel_path in manifest_paths:
            model = parse_android_manifest(root, rel_path)
            manifests.append(model)
            diagnostics.extend(model.diagnostics)

        layout_paths = _select_layout_paths(file_paths)
        for rel_path in layout_paths:
            layout = parse_layout_xml(root, rel_path)
            layouts.append(layout)
            diagnostics.extend(layout.diagnostics)

        component_index = _build_component_lookup(manifests)
        source_paths = _select_android_source_paths(file_paths)
        layout_names = {layout.layout_name for layout in layouts}
        ui_links, compose_signals, binding_signals, link_diagnostics = extract_android_ui_links(
            root_path=root,
            source_paths=source_paths,
            component_index=component_index,
            available_layouts=layout_names,
        )
        diagnostics.extend(link_diagnostics)

        modules, gradle, gradle_diagnostics = analyze_gradle_project(
            root_path=root,
            file_paths=file_paths,
            manifest_paths=manifest_paths,
            layout_paths=layout_paths,
        )
        diagnostics.extend(gradle_diagnostics)

        relationships = _build_relationships(
            project_root=root,
            manifests=manifests,
            layouts=layouts,
            ui_links=ui_links,
            modules=modules,
        )
        retrieval_signals = summarize_android_retrieval_signals(
            manifests=manifests,
            relationships=relationships,
            modules=modules,
            integration_signals=integration_summary.signals,
        )
        runtime_summary = _build_runtime_signal_summary(runtime_analyzer)

    project_model = _build_project_model(root, manifests)
    ui_summary = AndroidUiSummary(
        layouts=sorted(layouts, key=lambda item: item.source_path),
        links=sorted(ui_links, key=lambda item: (item.link_type, item.source_id, item.target_id, item.source_path or "")),
        compose_signals=sorted(compose_signals, key=lambda item: item.source_path),
        binding_signals=sorted(binding_signals, key=lambda item: (item.binding_type, item.source_path, item.class_name or "")),
        diagnostics=_sorted_diagnostics(
            [
                diag for diag in diagnostics
                if diag.code.startswith("malformed_layout_")
                or diag.code.startswith("layout_")
                or diag.code.startswith("android_source_")
            ]
        ),
    )
    return AndroidSummaryResponse(
        enabled=feature_config.effective_enabled,
        is_android_project=detection.is_android_project,
        feature_flag_source=feature_config.source,
        detection_reasons=detection.reasons,
        project=project_model,
        manifests=sorted(manifests, key=lambda item: item.source_path),
        ui=ui_summary,
        relationships=sorted(relationships, key=lambda item: (item.relationship_type, item.source_id, item.target_id)),
        retrieval_signals=retrieval_signals,
        diagnostics=_sorted_diagnostics(diagnostics),
        modules=sorted(modules, key=lambda item: item.module_path),
        gradle=gradle,
        runtime_signals=runtime_summary,
        integrations=integration_summary,
    )


def _build_project_model(project_root: Path, manifests: List[AndroidManifestModel]) -> AndroidProjectModel:
    package_names = sorted(
        {
            package_name
            for package_name in (manifest.package_name for manifest in manifests)
            if package_name
        }
    )
    launcher_activities = sorted(
        {
            launcher
            for launcher in (manifest.launcher_activity for manifest in manifests)
            if launcher
        }
    )
    return AndroidProjectModel(
        root_path=str(project_root),
        project_name=project_root.name,
        manifests_discovered=len(manifests),
        package_names=package_names,
        launcher_activities=launcher_activities,
    )


def _select_manifest_paths(file_paths: List[str]) -> List[str]:
    selected: List[str] = []
    for rel_path in sorted(file_paths):
        if not rel_path.endswith("AndroidManifest.xml"):
            continue
        parts = rel_path.split("/")
        if len(parts) < 4:
            continue
        if parts[-3] != "src":
            continue
        selected.append(rel_path)
    return selected


def _select_layout_paths(file_paths: List[str]) -> List[str]:
    selected: List[str] = []
    for rel_path in sorted(file_paths):
        lower = rel_path.lower()
        if "/res/layout/" in lower and lower.endswith(".xml"):
            selected.append(rel_path)
    return selected


def _select_android_source_paths(file_paths: List[str]) -> List[str]:
    selected: List[str] = []
    for rel_path in sorted(file_paths):
        lower = rel_path.lower()
        if lower.endswith(".kt") or lower.endswith(".kts") or lower.endswith(".java"):
            selected.append(rel_path)
    return selected


def _build_component_lookup(manifests: List[AndroidManifestModel]) -> Dict[str, str]:
    lookup: Dict[str, str] = {}
    for manifest in manifests:
        groups = (manifest.activities, manifest.services, manifest.receivers, manifest.providers)
        for components in groups:
            for component in components:
                component_id = f"component:{manifest.source_path}:{component.component_type}:{component.name}"
                lookup[component.name] = component_id
                if component.name.startswith("."):
                    lookup[component.name.lstrip(".")] = component_id
                if manifest.package_name and component.name.startswith("."):
                    lookup[f"{manifest.package_name}{component.name}"] = component_id
    return lookup


def _build_relationships(
    project_root: Path,
    manifests: List[AndroidManifestModel],
    layouts: List[AndroidLayoutModel],
    ui_links: List[AndroidUiLink],
    modules: List[AndroidModuleModel],
) -> List[AndroidRelationship]:
    project_id = f"project:{project_root.name}"
    items: List[AndroidRelationship] = []

    layout_name_to_id = {layout.layout_name: f"layout:{layout.layout_name}" for layout in layouts}
    view_id_to_target = {view_id: f"view_id:{view_id}" for layout in layouts for view_id in layout.resource_ids}

    for manifest in manifests:
        manifest_id = f"manifest:{manifest.source_path}"
        component_groups = (
            manifest.activities,
            manifest.services,
            manifest.receivers,
            manifest.providers,
        )
        for components in component_groups:
            for component in components:
                component_id = f"component:{manifest.source_path}:{component.component_type}:{component.name}"
                items.append(
                    AndroidRelationship(
                        relationship_type=AndroidRelationshipType.DECLARES_COMPONENT.value,
                        source_id=manifest_id,
                        target_id=component_id,
                        metadata={"component_type": component.component_type},
                    )
                )
                for index, _intent in enumerate(component.intent_filters):
                    items.append(
                        AndroidRelationship(
                            relationship_type=AndroidRelationshipType.HAS_INTENT_FILTER.value,
                            source_id=component_id,
                            target_id=f"intent_filter:{component_id}:{index}",
                        )
                    )
                for index, deeplink in enumerate(component.deep_links):
                    deeplink_target = (
                        f"deeplink:{component_id}:{index}:"
                        f"{deeplink.scheme or ''}:{deeplink.host or ''}:{deeplink.path or ''}:{deeplink.path_prefix or ''}"
                    )
                    items.append(
                        AndroidRelationship(
                            relationship_type=AndroidRelationshipType.HAS_DEEPLINK.value,
                            source_id=component_id,
                            target_id=deeplink_target,
                        )
                    )
                if manifest.launcher_activity and component.name == manifest.launcher_activity:
                    items.append(
                        AndroidRelationship(
                            relationship_type=AndroidRelationshipType.HAS_LAUNCHER_ACTIVITY.value,
                            source_id=project_id,
                            target_id=component_id,
                        )
                    )

    for layout in layouts:
        layout_id = f"layout:{layout.layout_name}"
        for resource_ref in layout.resource_refs:
            target_id = f"resource:{resource_ref.ref_type}:{resource_ref.value}"
            if resource_ref.ref_type in {"id", "+id"}:
                target_id = f"view_id:{resource_ref.value}"
            items.append(
                AndroidRelationship(
                    relationship_type=AndroidRelationshipType.LAYOUT_REFERENCES_RESOURCE.value,
                    source_id=layout_id,
                    target_id=target_id,
                    metadata={
                        "source_path": resource_ref.source_path,
                        "attribute": resource_ref.attribute or "",
                    },
                )
            )

    for link in ui_links:
        target_id = link.target_id
        if target_id.startswith("layout:"):
            layout_name = target_id.split(":", 1)[1]
            target_id = layout_name_to_id.get(layout_name, target_id)
            rel_type = AndroidRelationshipType.COMPONENT_USES_LAYOUT.value
        elif target_id.startswith("view_id:"):
            view_id = target_id.split(":", 1)[1]
            target_id = view_id_to_target.get(view_id, target_id)
            rel_type = AndroidRelationshipType.COMPONENT_USES_VIEW_ID.value
        elif target_id.startswith("compose:"):
            rel_type = AndroidRelationshipType.COMPONENT_USES_COMPOSE.value
        else:
            rel_type = link.link_type

        items.append(
            AndroidRelationship(
                relationship_type=rel_type,
                source_id=link.source_id,
                target_id=target_id,
                metadata=link.metadata,
            )
        )

    for module in modules:
        module_id = f"module:{module.module_path}"
        for plugin in module.plugins:
            items.append(
                AndroidRelationship(
                    relationship_type=AndroidRelationshipType.MODULE_DECLARES_PLUGIN.value,
                    source_id=module_id,
                    target_id=f"plugin:{plugin}",
                )
            )

        for build_type in module.variants.build_types:
            items.append(
                AndroidRelationship(
                    relationship_type=AndroidRelationshipType.MODULE_DECLARES_VARIANT.value,
                    source_id=module_id,
                    target_id=f"build_type:{module.module_path}:{build_type}",
                )
            )
        for flavor in module.variants.product_flavors:
            items.append(
                AndroidRelationship(
                    relationship_type=AndroidRelationshipType.MODULE_DECLARES_VARIANT.value,
                    source_id=module_id,
                    target_id=f"product_flavor:{module.module_path}:{flavor}",
                )
            )

        for manifest_path in module.manifest_paths:
            items.append(
                AndroidRelationship(
                    relationship_type=AndroidRelationshipType.MODULE_CONTAINS_MANIFEST.value,
                    source_id=module_id,
                    target_id=f"manifest:{manifest_path}",
                )
            )
        for layout_path in module.layout_paths:
            layout_name = Path(layout_path).stem
            items.append(
                AndroidRelationship(
                    relationship_type=AndroidRelationshipType.MODULE_CONTAINS_LAYOUT.value,
                    source_id=module_id,
                    target_id=f"layout:{layout_name}",
                )
            )

        for dependency in module.dependencies:
            if dependency.dependency_type == "module" and dependency.target_module:
                items.append(
                    AndroidRelationship(
                        relationship_type=AndroidRelationshipType.MODULE_DEPENDS_ON_MODULE.value,
                        source_id=module_id,
                        target_id=f"module:{dependency.target_module}",
                        metadata={"configuration": dependency.configuration},
                    )
                )

    return items


def _sorted_diagnostics(diagnostics: List[AndroidDiagnostic]) -> List[AndroidDiagnostic]:
    deduped: Dict[str, AndroidDiagnostic] = {}
    for item in diagnostics:
        key = "|".join([
            item.severity,
            item.code,
            item.source_path or "",
            str(item.line or 0),
            str(item.column or 0),
            item.message,
        ])
        deduped[key] = item
    return sorted(
        deduped.values(),
        key=lambda item: (
            item.severity,
            item.code,
            item.source_path or "",
            item.line or 0,
            item.column or 0,
        ),
    )


def _build_runtime_signal_summary(runtime_analyzer: Optional[RuntimeAnalyzer]) -> AndroidRuntimeSignalsSummary:
    if runtime_analyzer is None:
        return AndroidRuntimeSignalsSummary()
    signals = runtime_analyzer.get_android_runtime_signals()
    contexts = runtime_analyzer.get_android_failure_contexts()
    diagnostics = runtime_analyzer.get_android_runtime_diagnostics()
    categories: Dict[str, int] = {}
    for signal in signals:
        categories[signal.category] = categories.get(signal.category, 0) + 1
    return AndroidRuntimeSignalsSummary(
        count=len(signals),
        categories=dict(sorted(categories.items(), key=lambda item: item[0])),
        signals=signals[:12],
        failure_contexts=contexts[:8],
        diagnostics=diagnostics[:12],
    )
