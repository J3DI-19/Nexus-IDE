from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from context_engine.retrieval.models import ContextCandidate, RetrievalQuery

from .models import AndroidSummaryResponse


def build_android_engineering_briefing(
    query: RetrievalQuery,
    summary: AndroidSummaryResponse,
    selected_files: Optional[Sequence[str]] = None,
    selected_candidates: Optional[Sequence[ContextCandidate]] = None,
) -> Tuple[List[str], List[str]]:
    if not summary.enabled or not summary.is_android_project:
        return [], []

    lines: List[str] = []
    evidence: List[str] = []
    active_file = (query.active_file or "").replace("\\", "/")
    selected = sorted({path.replace("\\", "/") for path in (selected_files or []) if path})
    candidates_by_path: Dict[str, ContextCandidate] = {
        item.file_metadata.rel_path.replace("\\", "/"): item for item in (selected_candidates or [])
    }

    package_hint = summary.project.package_names[0] if summary.project.package_names else "unknown"
    lines.append(f"Android package namespace focus: `{package_hint}`")
    lines.append(f"Modules detected: {len(summary.modules)}; manifests: {len(summary.manifests)}; layouts: {len(summary.ui.layouts)}")

    if summary.project.launcher_activities:
        lines.append(f"Launcher entrypoints: {', '.join(summary.project.launcher_activities[:3])}")
    if summary.ui.compose_signals:
        lines.append(f"Compose usage signals: {len(summary.ui.compose_signals)} file(s)")
    if summary.ui.binding_signals:
        lines.append(f"Binding usage signals: {len(summary.ui.binding_signals)} file(s)")
    if summary.runtime_signals.categories:
        runtime_tags = ", ".join(list(summary.runtime_signals.categories.keys())[:4])
        lines.append(f"Active Android runtime categories: {runtime_tags}")
    if summary.integrations.enabled and summary.integrations.signals:
        lines.append(
            f"Optional Android integration signals loaded: {len(summary.integrations.signals)} "
            f"from {', '.join(summary.integrations.configured_sources[:3])}"
        )

    if active_file:
        evidence.append(f"Active file: `{active_file}`")
    if selected:
        evidence.append(f"Selected Android context files: {', '.join(selected[:6])}")

    for rel_path in selected[:8]:
        candidate = candidates_by_path.get(rel_path)
        if not candidate:
            continue
        android_factors = [
            component
            for component in candidate.score_breakdown
            if component.factor.lower().startswith("android")
        ]
        if not android_factors:
            continue
        top = sorted(android_factors, key=lambda item: item.points, reverse=True)[:2]
        evidence.append(
            f"{rel_path}: " + ", ".join(f"{item.factor}({item.points:.1f})" for item in top)
        )

    evidence.extend(_summarize_relationship_evidence(summary, selected))
    return lines[:8], evidence[:10]


def _summarize_relationship_evidence(summary: AndroidSummaryResponse, selected_files: Sequence[str]) -> List[str]:
    if not selected_files:
        return []
    selected = set(selected_files)
    relationship_hits: List[str] = []
    for rel in summary.relationships:
        src = rel.source_id.replace("manifest:", "").replace("layout:", "")
        if src not in selected and all(token not in rel.source_id for token in ("module:", "component:")):
            continue
        relationship_hits.append(f"{rel.relationship_type}: {rel.source_id} -> {rel.target_id}")
    relationship_hits = sorted(relationship_hits)
    return relationship_hits[:3]
