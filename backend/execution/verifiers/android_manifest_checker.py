from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Set

from context_engine.android.manifest_parser import ANDROID_NS_KEY

from execution.android_risk import AndroidRiskClass

from .base import AndroidCheckResult, AndroidConsistencyChecker, VerificationDiagnostic, VerificationMode


class AndroidManifestChecker(AndroidConsistencyChecker):
    @property
    def name(self) -> str:
        return "android_manifest_checker"

    @property
    def supported_risks(self) -> Set[str]:
        return {AndroidRiskClass.MANIFEST.value}

    def check(self, root: Path, targets: list[object], mode: VerificationMode) -> AndroidCheckResult:
        result = AndroidCheckResult(name=self.name)
        relevant = [t for t in targets if getattr(t, "risk_class", None) == AndroidRiskClass.MANIFEST]
        result.targets_checked = len(relevant)
        if not relevant:
            result.verified = True
            return result

        failed = False
        unverified = False
        for target in relevant:
            rel_path = str(getattr(target, "path", ""))
            abs_path = root / rel_path
            if not abs_path.exists():
                failed = True
                result.diagnostics.append(
                    VerificationDiagnostic(
                        severity="error",
                        code="android_manifest_malformed",
                        message="Manifest file is missing after patch apply.",
                        path=rel_path,
                        verifier=self.name,
                    )
                )
                continue
            try:
                tree = ET.parse(abs_path)
                root_node = tree.getroot()
            except ET.ParseError as exc:
                failed = True
                result.diagnostics.append(
                    VerificationDiagnostic(
                        severity="error",
                        code="android_manifest_malformed",
                        message="AndroidManifest.xml parsing failed.",
                        path=rel_path,
                        verifier=self.name,
                        details=str(exc),
                    )
                )
                continue
            except OSError as exc:
                unverified = True
                result.diagnostics.append(
                    VerificationDiagnostic(
                        severity="warning",
                        code="android_verifier_unavailable",
                        message="Manifest checker could not read AndroidManifest.xml.",
                        path=rel_path,
                        verifier=self.name,
                        tooling_missing=True,
                        details=str(exc),
                    )
                )
                continue

            application = _find_child(root_node, "application")
            if application is None:
                continue
            for comp_tag in ("activity", "service", "receiver", "provider"):
                for component in _find_children(application, comp_tag):
                    comp_name = _android_attr(component, "name")
                    if not comp_name:
                        failed = True
                        result.diagnostics.append(
                            VerificationDiagnostic(
                                severity="error",
                                code="android_manifest_component_missing_name",
                                message=f"Manifest component <{comp_tag}> is missing android:name.",
                                path=rel_path,
                                verifier=self.name,
                            )
                        )
                        continue
                    has_intent_filter = bool(_find_children(component, "intent-filter"))
                    exported = _android_attr(component, "exported")
                    if has_intent_filter and exported is None:
                        failed = True
                        result.diagnostics.append(
                            VerificationDiagnostic(
                                severity="error",
                                code="android_manifest_exported_inconsistent",
                                message=(
                                    f"Manifest component '{comp_name}' has intent-filters but no android:exported value."
                                ),
                                path=rel_path,
                                verifier=self.name,
                            )
                        )

        result.failed = failed
        result.unverified = (not failed) and unverified
        result.verified = not failed and not unverified
        return result


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _find_child(element: ET.Element, local_name: str):
    for child in list(element):
        if _local_name(child.tag) == local_name:
            return child
    return None


def _find_children(element: ET.Element, local_name: str) -> List[ET.Element]:
    return [child for child in list(element) if _local_name(child.tag) == local_name]


def _android_attr(element: ET.Element, name: str):
    return element.attrib.get(f"{ANDROID_NS_KEY}{name}") or element.attrib.get(name)
