from __future__ import annotations

import os
from typing import Dict, List, Optional

from execution.config import AndroidVerificationConfig
from .base import SyntaxVerifier
from .android_gradle_module_checker import AndroidGradleModuleChecker
from .android_layout_resource_checker import AndroidLayoutResourceChecker
from .android_manifest_checker import AndroidManifestChecker
from .android_source_link_checker import AndroidSourceLinkChecker
from .json_verifier import JsonSyntaxVerifier
from .java_verifier import JavaSyntaxVerifier
from .kotlin_verifier import KotlinSyntaxVerifier
from .python_verifier import PythonSyntaxVerifier
from .xml_verifier import XmlSyntaxVerifier
from .base import AndroidConsistencyChecker


class VerifierRegistry:
    def __init__(self) -> None:
        self._by_extension: Dict[str, SyntaxVerifier] = {}
        self._android_checkers: List[AndroidConsistencyChecker] = []

    def register(self, verifier: SyntaxVerifier) -> None:
        for ext in verifier.supported_extensions:
            normalized = ext.lower()
            if not normalized.startswith("."):
                normalized = f".{normalized}"
            self._by_extension[normalized] = verifier

    def resolve_for_path(self, rel_path: str) -> Optional[SyntaxVerifier]:
        ext = os.path.splitext(rel_path)[1].lower()
        return self._by_extension.get(ext)

    def register_android_checker(self, checker: AndroidConsistencyChecker) -> None:
        self._android_checkers.append(checker)

    def resolve_android_checkers(
        self,
        risk_targets: List[object],
        android_config: AndroidVerificationConfig,
    ) -> List[AndroidConsistencyChecker]:
        enabled_risks = set()
        if android_config.check_manifest:
            enabled_risks.add("manifest")
        if android_config.check_layout_resource:
            enabled_risks.add("layout_resource")
        if android_config.check_gradle_module:
            enabled_risks.add("gradle_module")
        if android_config.check_source_link:
            enabled_risks.add("source_link")

        present_risks = {getattr(target, "risk_class").value for target in risk_targets if hasattr(target, "risk_class")}
        required_risks = enabled_risks.intersection(present_risks)
        checkers: List[AndroidConsistencyChecker] = []
        for checker in self._android_checkers:
            if checker.supported_risks.intersection(required_risks):
                checkers.append(checker)
        return checkers


def build_default_registry() -> VerifierRegistry:
    registry = VerifierRegistry()
    registry.register(PythonSyntaxVerifier())
    registry.register(JsonSyntaxVerifier())
    registry.register(XmlSyntaxVerifier())
    registry.register(JavaSyntaxVerifier())
    registry.register(KotlinSyntaxVerifier())
    registry.register_android_checker(AndroidManifestChecker())
    registry.register_android_checker(AndroidLayoutResourceChecker())
    registry.register_android_checker(AndroidGradleModuleChecker())
    registry.register_android_checker(AndroidSourceLinkChecker())
    return registry
