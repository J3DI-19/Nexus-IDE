from __future__ import annotations

from pathlib import Path
from typing import Dict, Set

from context_engine.android.ui_parser import parse_layout_xml
from context_engine.core.scanner import fast_recursive_scan
from execution.android_risk import AndroidRiskClass

from .base import AndroidCheckResult, AndroidConsistencyChecker, VerificationDiagnostic, VerificationMode


class AndroidLayoutResourceChecker(AndroidConsistencyChecker):
    @property
    def name(self) -> str:
        return "android_layout_resource_checker"

    @property
    def supported_risks(self) -> Set[str]:
        return {AndroidRiskClass.LAYOUT_RESOURCE.value}

    def check(self, root: Path, targets: list[object], mode: VerificationMode) -> AndroidCheckResult:
        result = AndroidCheckResult(name=self.name)
        relevant = [t for t in targets if getattr(t, "risk_class", None) == AndroidRiskClass.LAYOUT_RESOURCE]
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
            abs_path = root / rel_path
            if not abs_path.exists():
                # resource deletion can be valid; checker focuses on structural breaks in remaining tree.
                continue
            if not rel_path.lower().endswith(".xml"):
                continue
            model = parse_layout_xml(root, rel_path)
            if model.malformed:
                failed = True
                result.diagnostics.append(
                    VerificationDiagnostic(
                        severity="error",
                        code="android_layout_malformed",
                        message="Layout/resource XML is malformed.",
                        path=rel_path,
                        verifier=self.name,
                    )
                )
                continue
            for ref in model.resource_refs:
                if ref.ref_type == "layout" and ref.value not in layout_names:
                    failed = True
                    result.diagnostics.append(
                        VerificationDiagnostic(
                            severity="error",
                            code="android_resource_reference_missing",
                            message=f"Referenced layout '@layout/{ref.value}' was not found.",
                            path=rel_path,
                            verifier=self.name,
                        )
                    )
                if ref.ref_type in {"id", "+id"} and ref.value not in view_ids:
                    # only unverified if we have no global id inventory
                    if not view_ids:
                        unverified = True
                        result.diagnostics.append(
                            VerificationDiagnostic(
                                severity="warning",
                                code="android_source_link_unverified_insufficient_context",
                                message="Unable to resolve view IDs because layout inventory is empty.",
                                path=rel_path,
                                verifier=self.name,
                                tooling_missing=True,
                            )
                        )
                    else:
                        failed = True
                        result.diagnostics.append(
                            VerificationDiagnostic(
                                severity="error",
                                code="android_view_id_missing",
                                message=f"Referenced view id '@id/{ref.value}' was not found in layouts.",
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
