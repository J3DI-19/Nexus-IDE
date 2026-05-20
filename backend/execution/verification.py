from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set

from context_engine.android.detector import detect_android_project
from context_engine.core.scanner import fast_recursive_scan

from .android_risk import AndroidRiskClass, AndroidRiskTarget, classify_android_patch_targets
from .config import AndroidVerificationConfig
from .verifiers.base import VerificationDiagnostic, VerificationMode, VerificationState
from .verifiers.registry import VerifierRegistry, build_default_registry


@dataclass
class AndroidCheckSummary:
    name: str
    status: str
    targets: int
    diagnostics_count: int


@dataclass
class AndroidVerificationSummary:
    enabled: bool
    is_android_project: bool
    config_source: str
    risk_summary: Dict[str, Any]
    checks: List[AndroidCheckSummary] = field(default_factory=list)
    checks_failed: int = 0
    checks_unverified: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "is_android_project": self.is_android_project,
            "config_source": self.config_source,
            "risk_summary": self.risk_summary,
            "checks": [
                {
                    "name": item.name,
                    "status": item.status,
                    "targets": item.targets,
                    "diagnostics_count": item.diagnostics_count,
                }
                for item in self.checks
            ],
            "checks_failed": self.checks_failed,
            "checks_unverified": self.checks_unverified,
        }


@dataclass
class VerificationSummary:
    mode: VerificationMode
    state: VerificationState
    files_checked: int
    files_unverified: int
    files_failed: int
    diagnostics: list[VerificationDiagnostic] = field(default_factory=list)
    verification_passed: bool = True
    android: AndroidVerificationSummary = field(
        default_factory=lambda: AndroidVerificationSummary(
            enabled=False,
            is_android_project=False,
            config_source="default",
            risk_summary={
                "files_scanned": 0,
                "by_class": {
                    "manifest": 0,
                    "layout_resource": 0,
                    "gradle_module": 0,
                    "source_link": 0,
                    "non_android": 0,
                },
            },
        )
    )

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "state": self.state.value,
            "files_checked": self.files_checked,
            "files_unverified": self.files_unverified,
            "files_failed": self.files_failed,
            "diagnostics": [d.as_dict() for d in self.diagnostics],
            "android": self.android.as_dict(),
        }


def run_verification(
    root: Path,
    applied_changes: Iterable[Any],
    mode: VerificationMode,
    registry: VerifierRegistry | None = None,
    injected_diagnostics: list[VerificationDiagnostic] | None = None,
    android_config: AndroidVerificationConfig | None = None,
) -> VerificationSummary:
    verification_registry = registry or build_default_registry()
    diagnostics: list[VerificationDiagnostic] = list(injected_diagnostics or [])
    all_changes = list(applied_changes)
    candidates = [c for c in all_changes if getattr(c, "content", None) is not None]
    files_checked = len(candidates)

    all_paths = fast_recursive_scan(str(root), include_dirs=True)
    detection = detect_android_project(root, all_paths)
    risk_targets = classify_android_patch_targets(all_changes)
    risk_summary = _build_risk_summary(risk_targets)

    android_options = android_config or AndroidVerificationConfig()
    android_enabled = _is_android_verification_enabled(android_options.mode, detection.is_android_project)
    android_summary = AndroidVerificationSummary(
        enabled=android_enabled,
        is_android_project=detection.is_android_project,
        config_source=android_options.config_source,
        risk_summary=risk_summary,
    )

    if mode == VerificationMode.OFF:
        diagnostics.append(
            VerificationDiagnostic(
                severity="warning",
                code="verification_skipped",
                message="Verification mode is OFF; syntax checks were skipped.",
            )
        )
        diagnostics.append(
            VerificationDiagnostic(
                severity="warning",
                code="android_verification_skipped_mode_off",
                message="Android verification skipped because verification mode is OFF.",
            )
        )
        return VerificationSummary(
            mode=mode,
            state=VerificationState.UNVERIFIED,
            files_checked=files_checked,
            files_unverified=files_checked,
            files_failed=0,
            diagnostics=diagnostics,
            verification_passed=True,
            android=android_summary,
        )

    verified_count = 0
    failed_paths: set[str] = set()
    unverified_paths: set[str] = set()

    for change in candidates:
        rel_path = str(getattr(change, "path", ""))
        target = (root / rel_path).resolve()
        if not target.exists():
            failed_paths.add(rel_path)
            diagnostics.append(
                VerificationDiagnostic(
                    severity="error",
                    code="file_missing_after_apply",
                    message="File missing after apply.",
                    path=rel_path,
                    verifier="verification_coordinator",
                )
            )
            continue
        if target.is_dir():
            failed_paths.add(rel_path)
            diagnostics.append(
                VerificationDiagnostic(
                    severity="error",
                    code="path_type_mismatch",
                    message="Path resolved to a directory after apply.",
                    path=rel_path,
                    verifier="verification_coordinator",
                )
            )
            continue

        verifier = verification_registry.resolve_for_path(rel_path)
        if verifier is None:
            ext = Path(rel_path).suffix.lower() or "(no extension)"
            unverified_paths.add(rel_path)
            diagnostics.append(
                VerificationDiagnostic(
                    severity="warning",
                    code="verifier_unavailable",
                    message=f"No verifier registered for extension {ext}.",
                    path=rel_path,
                    tooling_missing=True,
                )
            )
            continue

        try:
            content = target.read_text(encoding="utf-8")
            result = verifier.verify(target, content)
        except Exception as exc:
            failed_paths.add(rel_path)
            diagnostics.append(
                VerificationDiagnostic(
                    severity="error",
                    code="verifier_runtime_error",
                    message="Verifier crashed while checking file.",
                    path=rel_path,
                    verifier=getattr(verifier, "name", "unknown"),
                    details=str(exc),
                )
            )
            continue

        diagnostics.extend(result.diagnostics)
        if result.failed:
            failed_paths.add(rel_path)
        elif result.verified:
            verified_count += 1
        else:
            unverified_paths.add(rel_path)

    _run_android_check_layer(
        root=root,
        mode=mode,
        verification_registry=verification_registry,
        risk_targets=risk_targets,
        android_options=android_options,
        android_enabled=android_enabled,
        android_is_project=detection.is_android_project,
        diagnostics=diagnostics,
        failed_paths=failed_paths,
        unverified_paths=unverified_paths,
        android_summary=android_summary,
    )

    if failed_paths:
        state = VerificationState.FAILED
    elif verified_count > 0 and not unverified_paths:
        state = VerificationState.FULLY_VERIFIED
    elif verified_count > 0 and unverified_paths:
        state = VerificationState.PARTIALLY_VERIFIED
    else:
        state = VerificationState.UNVERIFIED

    if mode == VerificationMode.WARN:
        verification_passed = state != VerificationState.FAILED
    else:
        verification_passed = state == VerificationState.FULLY_VERIFIED

    diagnostics = sorted(
        diagnostics,
        key=lambda item: (
            item.severity,
            item.code,
            item.path or "",
            item.message,
        ),
    )
    return VerificationSummary(
        mode=mode,
        state=state,
        files_checked=files_checked,
        files_unverified=len(unverified_paths),
        files_failed=len(failed_paths),
        diagnostics=diagnostics,
        verification_passed=verification_passed,
        android=android_summary,
    )


def _run_android_check_layer(
    root: Path,
    mode: VerificationMode,
    verification_registry: VerifierRegistry,
    risk_targets: List[AndroidRiskTarget],
    android_options: AndroidVerificationConfig,
    android_enabled: bool,
    android_is_project: bool,
    diagnostics: List[VerificationDiagnostic],
    failed_paths: Set[str],
    unverified_paths: Set[str],
    android_summary: AndroidVerificationSummary,
) -> None:
    android_risky_targets = [target for target in risk_targets if target.risk_class != AndroidRiskClass.NON_ANDROID]
    if not android_enabled:
        diagnostics.append(
            VerificationDiagnostic(
                severity="warning",
                code="android_verification_not_applicable",
                message="Android verification is disabled for this project/configuration.",
            )
        )
        return
    if not android_is_project:
        diagnostics.append(
            VerificationDiagnostic(
                severity="warning",
                code="android_verification_not_applicable",
                message="Android verification skipped because project was not detected as Android.",
            )
        )
        return
    if not android_risky_targets:
        diagnostics.append(
            VerificationDiagnostic(
                severity="warning",
                code="android_verification_not_applicable",
                message="No Android-risk patch targets were found.",
            )
        )
        return

    checkers = verification_registry.resolve_android_checkers(risk_targets, android_options)
    available_risks: Set[str] = set()
    for checker in checkers:
        available_risks.update(checker.supported_risks)
    required_risks = _enabled_risks(android_options).intersection(
        {target.risk_class.value for target in android_risky_targets}
    )
    missing_risks = sorted(required_risks.difference(available_risks))
    for risk in missing_risks:
        diag = VerificationDiagnostic(
            severity="warning",
            code="android_verifier_unavailable",
            message=f"No Android checker is registered for risk class '{risk}'.",
            verifier="verification_coordinator",
            tooling_missing=True,
        )
        diagnostics.append(diag)
        android_summary.checks_unverified += 1
        if mode == VerificationMode.STRICT:
            unverified_paths.add(f"android:{risk}")

    for checker in checkers:
        check_result = checker.check(root=root, targets=risk_targets, mode=mode)
        diagnostics.extend(check_result.diagnostics)
        if check_result.failed:
            android_summary.checks_failed += 1
            _merge_paths(failed_paths, check_result.diagnostics, fallback_prefix=f"android:{checker.name}")
            status = "failed"
        elif check_result.unverified:
            android_summary.checks_unverified += 1
            _merge_paths(unverified_paths, check_result.diagnostics, fallback_prefix=f"android:{checker.name}")
            status = "unverified"
        elif check_result.targets_checked == 0:
            status = "skipped"
        else:
            status = "passed"

        android_summary.checks.append(
            AndroidCheckSummary(
                name=checker.name,
                status=status,
                targets=check_result.targets_checked,
                diagnostics_count=len(check_result.diagnostics),
            )
        )


def _build_risk_summary(risk_targets: List[AndroidRiskTarget]) -> Dict[str, Any]:
    by_class = {
        "manifest": 0,
        "layout_resource": 0,
        "gradle_module": 0,
        "source_link": 0,
        "non_android": 0,
    }
    for target in risk_targets:
        by_class[target.risk_class.value] = by_class.get(target.risk_class.value, 0) + 1
    return {
        "files_scanned": len(risk_targets),
        "by_class": by_class,
    }


def _enabled_risks(android_options: AndroidVerificationConfig) -> Set[str]:
    risks: Set[str] = set()
    if android_options.check_manifest:
        risks.add("manifest")
    if android_options.check_layout_resource:
        risks.add("layout_resource")
    if android_options.check_gradle_module:
        risks.add("gradle_module")
    if android_options.check_source_link:
        risks.add("source_link")
    return risks


def _merge_paths(bucket: Set[str], diagnostics: List[VerificationDiagnostic], fallback_prefix: str) -> None:
    before = len(bucket)
    for diagnostic in diagnostics:
        if diagnostic.path:
            bucket.add(diagnostic.path)
    if len(bucket) == before:
        bucket.add(fallback_prefix)


def _is_android_verification_enabled(mode: str, is_android_project: bool) -> bool:
    normalized = (mode or "auto").lower()
    if normalized == "off":
        return False
    if normalized == "on":
        return True
    return bool(is_android_project)
