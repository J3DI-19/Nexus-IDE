from __future__ import annotations

from pathlib import Path
import re
from typing import List, Set

from context_engine.android.gradle_parser import analyze_gradle_project
from context_engine.core.scanner import fast_recursive_scan
from execution.android_risk import AndroidRiskClass

from .base import AndroidCheckResult, AndroidConsistencyChecker, VerificationDiagnostic, VerificationMode


class AndroidGradleModuleChecker(AndroidConsistencyChecker):
    @property
    def name(self) -> str:
        return "android_gradle_module_checker"

    @property
    def supported_risks(self) -> Set[str]:
        return {AndroidRiskClass.GRADLE_MODULE.value}

    def check(self, root: Path, targets: list[object], mode: VerificationMode) -> AndroidCheckResult:
        result = AndroidCheckResult(name=self.name)
        relevant = [t for t in targets if getattr(t, "risk_class", None) == AndroidRiskClass.GRADLE_MODULE]
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
                unverified = True
                result.diagnostics.append(
                    VerificationDiagnostic(
                        severity="warning",
                        code="android_verifier_unavailable",
                        message="Gradle target is missing after apply; module graph cannot be fully verified.",
                        path=rel_path,
                        verifier=self.name,
                        tooling_missing=True,
                    )
                )
                continue
            if _has_unbalanced_braces(abs_path):
                failed = True
                result.diagnostics.append(
                    VerificationDiagnostic(
                        severity="error",
                        code="android_gradle_parse_error",
                        message="Gradle script has unbalanced braces.",
                        path=rel_path,
                        verifier=self.name,
                    )
                )

        file_paths = [p.replace("\\", "/") for p in fast_recursive_scan(str(root))]
        manifest_paths = [p for p in file_paths if p.endswith("AndroidManifest.xml")]
        layout_paths = [p for p in file_paths if "/res/layout/" in p.lower() and p.lower().endswith(".xml")]
        modules, _gradle, diagnostics = analyze_gradle_project(
            root_path=root,
            file_paths=file_paths,
            manifest_paths=manifest_paths,
            layout_paths=layout_paths,
        )
        module_paths = {module.module_path for module in modules}
        for module in modules:
            if (module.namespace or module.compile_sdk or module.min_sdk or module.target_sdk) and not any(
                plugin.startswith("com.android.") for plugin in module.plugins
            ):
                failed = True
                result.diagnostics.append(
                    VerificationDiagnostic(
                        severity="error",
                        code="android_android_plugin_missing",
                        message=f"Module '{module.module_path}' declares Android config but no com.android.* plugin.",
                        path=module.build_file,
                        verifier=self.name,
                    )
                )
            for dep in module.dependencies:
                if dep.dependency_type == "module" and dep.target_module and dep.target_module not in module_paths:
                    failed = True
                    result.diagnostics.append(
                        VerificationDiagnostic(
                            severity="error",
                            code="android_module_dependency_missing",
                            message=f"Module dependency '{dep.target_module}' was not found in settings/modules.",
                            path=dep.source_path,
                            verifier=self.name,
                        )
                    )

        if diagnostics:
            unverified = True
            for diag in diagnostics:
                result.diagnostics.append(
                    VerificationDiagnostic(
                        severity="warning",
                        code="android_verifier_unavailable",
                        message=diag.message,
                        path=diag.source_path,
                        verifier=self.name,
                        tooling_missing=True,
                        details=diag.details,
                    )
                )

        result.failed = failed
        result.unverified = (not failed) and unverified
        result.verified = not failed and not unverified
        return result


def _has_unbalanced_braces(path: Path) -> bool:
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    sanitized = re.sub(r"//.*?$|/\*.*?\*/|\".*?\"|'.*?'", "", content, flags=re.MULTILINE | re.DOTALL)
    depth = 0
    for char in sanitized:
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        if depth < 0:
            return True
    return depth != 0
