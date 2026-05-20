from __future__ import annotations

from pathlib import Path
import re
from typing import Dict, Set

from context_engine.android.ui_parser import parse_layout_xml
from context_engine.core.scanner import fast_recursive_scan
from execution.android_risk import AndroidRiskClass

from .base import AndroidCheckResult, AndroidConsistencyChecker, VerificationDiagnostic, VerificationMode


LAYOUT_REF_RE = re.compile(r"R\.layout\.([A-Za-z0-9_]+)")
VIEW_ID_REF_RE = re.compile(r"R\.id\.([A-Za-z0-9_]+)")


class AndroidSourceLinkChecker(AndroidConsistencyChecker):
    @property
    def name(self) -> str:
        return "android_source_link_checker"

    @property
    def supported_risks(self) -> Set[str]:
        return {AndroidRiskClass.SOURCE_LINK.value}

    def check(self, root: Path, targets: list[object], mode: VerificationMode) -> AndroidCheckResult:
        result = AndroidCheckResult(name=self.name)
        relevant = [t for t in targets if getattr(t, "risk_class", None) == AndroidRiskClass.SOURCE_LINK]
        result.targets_checked = len(relevant)
        if not relevant:
            result.verified = True
            return result

        inventory = _build_layout_inventory(root)
        layout_names = inventory["layout_names"]
        view_ids = inventory["view_ids"]
        failed = False
        unverified = False

        for target in relevant:
            rel_path = str(getattr(target, "path", ""))
            if getattr(target, "is_deleted", False):
                continue
            abs_path = root / rel_path
            if not abs_path.exists():
                continue
            try:
                content = abs_path.read_text(encoding="utf-8", errors="ignore")
            except OSError as exc:
                unverified = True
                result.diagnostics.append(
                    VerificationDiagnostic(
                        severity="warning",
                        code="android_source_link_unverified_insufficient_context",
                        message="Source-link checker could not read source file.",
                        path=rel_path,
                        verifier=self.name,
                        tooling_missing=True,
                        details=str(exc),
                    )
                )
                continue

            layout_refs = sorted(set(LAYOUT_REF_RE.findall(content)))
            view_id_refs = sorted(set(VIEW_ID_REF_RE.findall(content)))
            if (layout_refs or view_id_refs) and not layout_names and not view_ids:
                unverified = True
                result.diagnostics.append(
                    VerificationDiagnostic(
                        severity="warning",
                        code="android_source_link_unverified_insufficient_context",
                        message="No layout/resource inventory available to validate source links.",
                        path=rel_path,
                        verifier=self.name,
                        tooling_missing=True,
                    )
                )
                continue

            for layout_name in layout_refs:
                if layout_name not in layout_names:
                    failed = True
                    result.diagnostics.append(
                        VerificationDiagnostic(
                            severity="error",
                            code="android_source_layout_link_missing",
                            message=f"Source references missing layout 'R.layout.{layout_name}'.",
                            path=rel_path,
                            verifier=self.name,
                        )
                    )

            for view_id in view_id_refs:
                if view_id not in view_ids:
                    failed = True
                    result.diagnostics.append(
                        VerificationDiagnostic(
                            severity="error",
                            code="android_source_view_id_link_missing",
                            message=f"Source references missing id 'R.id.{view_id}'.",
                            path=rel_path,
                            verifier=self.name,
                        )
                    )

        result.failed = failed
        result.unverified = (not failed) and unverified
        result.verified = not failed and not unverified
        return result


def _build_layout_inventory(root: Path) -> Dict[str, Set[str]]:
    file_paths = fast_recursive_scan(str(root))
    layout_paths = [
        p.replace("\\", "/")
        for p in file_paths
        if "/res/layout/" in p.replace("\\", "/").lower() and p.lower().endswith(".xml")
    ]
    layout_names: Set[str] = set()
    view_ids: Set[str] = set()
    for rel_path in layout_paths:
        model = parse_layout_xml(root, rel_path)
        if model.malformed:
            continue
        layout_names.add(model.layout_name)
        view_ids.update(model.resource_ids)
    return {"layout_names": layout_names, "view_ids": view_ids}
