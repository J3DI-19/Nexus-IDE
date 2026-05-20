from __future__ import annotations

import re
from typing import Dict, List, Optional, Set, Tuple

from .models import AndroidDiagnostic, AndroidFailureContext, AndroidRuntimeSignal


STACKTRACE_RE = re.compile(r"\bat\s+([A-Za-z0-9_.$]+)\(([^:()]+):(\d+)\)")
FILE_LINE_RE = re.compile(r"([A-Za-z0-9_./\\-]+\.(?:kt|java|xml)):(\d+)")
GRADLE_TASK_RE = re.compile(r"Execution failed for task '([^']+)'")
MANIFEST_MERGE_RE = re.compile(r"Manifest merger failed", re.IGNORECASE)
AAPT_RE = re.compile(r"(AAPT|resource linking failed|error:\s*resource)", re.IGNORECASE)
KOTLIN_COMPILE_RE = re.compile(r"\be:\s+([A-Za-z0-9_./\\-]+\.kt):\s*\((\d+),\s*\d+\)\s*(.*)")
JAVA_COMPILE_RE = re.compile(r"([A-Za-z0-9_./\\-]+\.java):(\d+):\s*error:\s*(.*)")
SYMBOL_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)")
MODULE_FROM_TASK_RE = re.compile(r"^:([A-Za-z0-9:_-]+):")


class AndroidRuntimeParser:
    def parse(self, log: str) -> Tuple[List[AndroidRuntimeSignal], List[AndroidFailureContext], List[AndroidDiagnostic]]:
        signals: List[AndroidRuntimeSignal] = []
        contexts: List[AndroidFailureContext] = []
        diagnostics: List[AndroidDiagnostic] = []

        stripped_log = (log or "").strip()
        if not stripped_log:
            diagnostics.append(
                AndroidDiagnostic(
                    severity="warning",
                    code="android_runtime_empty_log",
                    message="Runtime log is empty; no Android runtime signals extracted.",
                )
            )
            return signals, contexts, diagnostics

        lines = [line.rstrip() for line in stripped_log.splitlines() if line.strip()]
        categories_found: Set[str] = set()

        gradle_task = self._extract_gradle_task(stripped_log)
        module_from_task = self._extract_module_from_task(gradle_task)

        if MANIFEST_MERGE_RE.search(stripped_log):
            categories_found.add("manifest_merge_failure")
            signal = AndroidRuntimeSignal(
                category="manifest_merge_failure",
                severity="error",
                message="Manifest merge failure detected.",
                module=module_from_task,
                raw_excerpt=self._first_matching_line(lines, MANIFEST_MERGE_RE),
                confidence="medium",
            )
            signals.append(signal)
            contexts.append(
                AndroidFailureContext(
                    failure_kind="manifest_merge",
                    stage=gradle_task or "manifest_processing",
                    implicated_modules=[module_from_task] if module_from_task else [],
                    probable_root=signal.raw_excerpt or signal.message,
                    confidence="medium",
                )
            )

        if AAPT_RE.search(stripped_log):
            categories_found.add("aapt_resource_linking_failure")
            file_path, line = self._extract_first_file_line(stripped_log)
            signal = AndroidRuntimeSignal(
                category="aapt_resource_linking_failure",
                severity="error",
                message="AAPT/resource linking failure detected.",
                module=module_from_task or self._infer_module_from_path(file_path),
                file=file_path,
                line=line,
                raw_excerpt=self._first_matching_line(lines, AAPT_RE),
                confidence="high" if file_path and line else "medium",
            )
            signals.append(signal)
            contexts.append(
                AndroidFailureContext(
                    failure_kind="resource_linking",
                    stage=gradle_task or "aapt",
                    implicated_modules=[signal.module] if signal.module else [],
                    implicated_files=[file_path] if file_path else [],
                    probable_root=signal.raw_excerpt or signal.message,
                    confidence=signal.confidence,
                )
            )

        kotlin_hits = list(KOTLIN_COMPILE_RE.finditer(stripped_log))
        for match in kotlin_hits[:5]:
            categories_found.add("kotlin_compile_error")
            file_path = self._normalize_path(match.group(1))
            line_number = _safe_int(match.group(2))
            message = match.group(3).strip() or "Kotlin compiler error"
            module = self._infer_module_from_path(file_path) or module_from_task
            signal = AndroidRuntimeSignal(
                category="kotlin_compile_error",
                severity="error",
                message=message,
                module=module,
                file=file_path,
                line=line_number,
                raw_excerpt=match.group(0).strip(),
                confidence="high",
            )
            signals.append(signal)

        java_hits = list(JAVA_COMPILE_RE.finditer(stripped_log))
        for match in java_hits[:5]:
            categories_found.add("java_compile_error")
            file_path = self._normalize_path(match.group(1))
            line_number = _safe_int(match.group(2))
            message = match.group(3).strip() or "Java compiler error"
            module = self._infer_module_from_path(file_path) or module_from_task
            signal = AndroidRuntimeSignal(
                category="java_compile_error",
                severity="error",
                message=message,
                module=module,
                file=file_path,
                line=line_number,
                raw_excerpt=match.group(0).strip(),
                confidence="high",
            )
            signals.append(signal)

        if gradle_task and "BUILD FAILED" in stripped_log.upper():
            categories_found.add("gradle_failure")
            signal = AndroidRuntimeSignal(
                category="gradle_failure",
                severity="error",
                message=f"Gradle task failure at {gradle_task}",
                module=module_from_task,
                raw_excerpt=f"Execution failed for task '{gradle_task}'",
                confidence="medium",
            )
            signals.append(signal)

        stack_hits = list(STACKTRACE_RE.finditer(stripped_log))
        for match in stack_hits[:8]:
            categories_found.add("logcat_exception")
            symbol = match.group(1)
            file_name = match.group(2)
            line_number = _safe_int(match.group(3))
            signal = AndroidRuntimeSignal(
                category="logcat_exception",
                severity="error",
                message=f"Stacktrace frame at {symbol}",
                module=module_from_task,
                file=file_name,
                line=line_number,
                symbol=symbol,
                raw_excerpt=match.group(0).strip(),
                confidence="high",
            )
            signals.append(signal)

        if signals:
            contexts.extend(self._build_contexts_from_signals(signals, gradle_task))
        else:
            diagnostics.append(
                AndroidDiagnostic(
                    severity="warning",
                    code="android_runtime_unclassified_log",
                    message="No Android runtime pattern matched; log kept as raw runtime artifact.",
                )
            )

        signals = _dedupe_signals(signals)
        contexts = _dedupe_contexts(contexts)
        diagnostics = sorted(diagnostics, key=lambda item: (item.code, item.message))
        return signals, contexts, diagnostics

    def _extract_gradle_task(self, log: str) -> Optional[str]:
        match = GRADLE_TASK_RE.search(log)
        if not match:
            return None
        return match.group(1)

    def _extract_module_from_task(self, task: Optional[str]) -> Optional[str]:
        if not task:
            return None
        match = MODULE_FROM_TASK_RE.match(task)
        if not match:
            return None
        module_fragment = match.group(1)
        module = module_fragment.split(":")[0]
        return module or None

    def _extract_first_file_line(self, log: str) -> Tuple[Optional[str], Optional[int]]:
        match = FILE_LINE_RE.search(log)
        if not match:
            return None, None
        return self._normalize_path(match.group(1)), _safe_int(match.group(2))

    def _infer_module_from_path(self, path: Optional[str]) -> Optional[str]:
        if not path:
            return None
        normalized = self._normalize_path(path)
        parts = normalized.split("/")
        if len(parts) >= 2 and parts[1] == "src":
            return parts[0]
        return parts[0] if parts else None

    def _normalize_path(self, path: str) -> str:
        return path.replace("\\", "/").strip()

    def _first_matching_line(self, lines: List[str], pattern: re.Pattern) -> Optional[str]:
        for line in lines:
            if pattern.search(line):
                return line.strip()
        return None

    def _build_contexts_from_signals(
        self,
        signals: List[AndroidRuntimeSignal],
        gradle_task: Optional[str],
    ) -> List[AndroidFailureContext]:
        contexts: List[AndroidFailureContext] = []
        by_category: Dict[str, List[AndroidRuntimeSignal]] = {}
        for signal in signals:
            by_category.setdefault(signal.category, []).append(signal)

        for category, category_signals in sorted(by_category.items(), key=lambda item: item[0]):
            modules = sorted({item.module for item in category_signals if item.module})
            files = sorted({item.file for item in category_signals if item.file})
            symbols = sorted({item.symbol for item in category_signals if item.symbol})
            top = category_signals[0]
            confidence = _min_confidence([item.confidence for item in category_signals])
            contexts.append(
                AndroidFailureContext(
                    failure_kind=category,
                    stage=gradle_task or category,
                    implicated_modules=modules,
                    implicated_files=files,
                    implicated_symbols=symbols,
                    probable_root=top.raw_excerpt or top.message,
                    confidence=confidence,
                )
            )
        return contexts


def _safe_int(value: str) -> Optional[int]:
    try:
        return int(value)
    except Exception:
        return None


def _confidence_rank(value: str) -> int:
    ordering = {"high": 0, "medium": 1, "low": 2}
    return ordering.get(value, 2)


def _min_confidence(values: List[str]) -> str:
    if not values:
        return "low"
    return sorted(values, key=_confidence_rank)[0]


def _dedupe_signals(signals: List[AndroidRuntimeSignal]) -> List[AndroidRuntimeSignal]:
    deduped: Dict[str, AndroidRuntimeSignal] = {}
    for signal in signals:
        key = "|".join(
            [
                signal.category,
                signal.file or "",
                str(signal.line or 0),
                signal.symbol or "",
                signal.message,
            ]
        )
        deduped[key] = signal
    return sorted(
        deduped.values(),
        key=lambda item: (item.category, item.file or "", item.line or 0, item.symbol or ""),
    )


def _dedupe_contexts(contexts: List[AndroidFailureContext]) -> List[AndroidFailureContext]:
    deduped: Dict[str, AndroidFailureContext] = {}
    for context in contexts:
        key = "|".join(
            [
                context.failure_kind,
                context.stage,
                ",".join(context.implicated_modules),
                ",".join(context.implicated_files),
            ]
        )
        deduped[key] = context
    return sorted(
        deduped.values(),
        key=lambda item: (item.failure_kind, item.stage, ",".join(item.implicated_modules)),
    )
