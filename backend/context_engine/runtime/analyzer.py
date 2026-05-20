from typing import List, Optional
import threading
from .models import RuntimeArtifact, RuntimeArtifactType
from .detectors import RuntimeDetector
from ..android.models import AndroidRuntimeSignal, AndroidFailureContext, AndroidDiagnostic
from ..android.runtime_parser import AndroidRuntimeParser

class RuntimeAnalyzer:
    def __init__(self):
        self.detector = RuntimeDetector()
        self.android_parser = AndroidRuntimeParser()
        self._lock = threading.RLock()
        self._current_artifacts: List[RuntimeArtifact] = []
        self._android_runtime_signals: List[AndroidRuntimeSignal] = []
        self._android_failure_contexts: List[AndroidFailureContext] = []
        self._android_runtime_diagnostics: List[AndroidDiagnostic] = []
        self._diagnostic_versions = {}

    def ingest_log(self, log: str):
        artifact = self.detector.detect_and_parse(log)
        android_signals, android_contexts, android_diagnostics = self.android_parser.parse(log)
        if artifact:
            artifact.metadata["android_runtime"] = {
                "signals": [_dump_model(signal) for signal in android_signals],
                "failure_contexts": [_dump_model(ctx) for ctx in android_contexts],
                "diagnostics": [_dump_model(diag) for diag in android_diagnostics],
            }
            with self._lock:
                # Maintain a rolling buffer of top 5 artifacts
                self._current_artifacts.insert(0, artifact)
                self._current_artifacts = self._current_artifacts[:5]
                self._android_runtime_signals = _merge_android_signals(
                    new_items=android_signals,
                    existing=self._android_runtime_signals,
                    limit=30,
                )
                self._android_failure_contexts = _merge_android_failure_contexts(
                    new_items=android_contexts,
                    existing=self._android_failure_contexts,
                    limit=15,
                )
                self._android_runtime_diagnostics = _merge_android_diagnostics(
                    new_items=android_diagnostics,
                    existing=self._android_runtime_diagnostics,
                    limit=20,
                )
        return artifact

    def get_active_artifacts(self) -> List[RuntimeArtifact]:
        with self._lock:
            return list(self._current_artifacts)

    def clear(self):
        with self._lock:
            self._current_artifacts = []
            self._android_runtime_signals = []
            self._android_failure_contexts = []
            self._android_runtime_diagnostics = []
            self._diagnostic_versions = {}

    def replace_diagnostics_for_file(self, file_path: str, diagnostics: List[RuntimeArtifact], version: int = 0) -> bool:
        normalized = self._normalize_path(file_path)
        with self._lock:
            current_version = self._diagnostic_versions.get(normalized, -1)
            if version < current_version:
                return False
            self._diagnostic_versions[normalized] = version

        def is_same_file_diagnostic(artifact: RuntimeArtifact) -> bool:
            is_diagnostic = (
                artifact.metadata.get("source") == "live_diagnostics"
                or artifact.artifact_type in {
                    RuntimeArtifactType.COMPILER_ERROR,
                    RuntimeArtifactType.BUILD_FAILURE,
                    RuntimeArtifactType.TEST_FAILURE,
                }
                or artifact.metadata.get("type") in {"syntax", "diagnostic"}
            )
            if not is_diagnostic:
                return False
            return any(self._is_same_path(frame.file_path, normalized) for frame in artifact.frames)

        with self._lock:
            self._current_artifacts = [
                artifact for artifact in self._current_artifacts
                if not is_same_file_diagnostic(artifact)
            ]

            for artifact in reversed(diagnostics):
                artifact.metadata["source"] = "live_diagnostics"
                self._current_artifacts.insert(0, artifact)

            self._current_artifacts = self._current_artifacts[:10]
        return True

    def _normalize_path(self, file_path: str) -> str:
        normalized = file_path.replace("\\", "/").strip()
        for prefix in ("/workspace/", "workspace/", "./"):
            if prefix in normalized:
                normalized = normalized.split(prefix).pop() or normalized
        return normalized.lstrip("/")

    def _is_same_path(self, artifact_path: str, target_path: str) -> bool:
        normalized_artifact = self._normalize_path(artifact_path)
        normalized_target = self._normalize_path(target_path)
        return (
            normalized_artifact == normalized_target
            or normalized_artifact.endswith("/" + normalized_target)
            or normalized_target.endswith("/" + normalized_artifact)
        )
        
    def get_referenced_files(self) -> List[str]:
        files = set()
        for art in self.get_active_artifacts():
            for frame in art.frames:
                files.add(frame.file_path)
        return list(files)

    def get_referenced_symbols(self) -> List[str]:
        symbols = set()
        for art in self.get_active_artifacts():
            for frame in art.frames:
                if frame.symbol_name:
                    symbols.add(frame.symbol_name)
        return list(symbols)

    def get_execution_chains(self) -> List[List[str]]:
        """Returns a list of execution chains (ordered list of file:symbol) from stack traces."""
        chains = []
        for art in self.get_active_artifacts():
            chain = []
            for frame in art.frames:
                if frame.symbol_name:
                    chain.append(f"{frame.file_path}:{frame.symbol_name}")
                else:
                    chain.append(frame.file_path)
            if chain:
                chains.append(chain)
        return chains

    def get_hot_symbols(self) -> List[dict]:
        """Identifies volatile symbols that are currently part of failing execution paths."""
        hot_map = {}
        for art in self.get_active_artifacts():
            for i, frame in enumerate(art.frames):
                if frame.symbol_name:
                    key = f"{frame.file_path}:{frame.symbol_name}"
                    if key not in hot_map:
                        hot_map[key] = {"name": frame.symbol_name, "file": frame.file_path, "hits": 0, "is_leaf": i == 0}
                    hot_map[key]["hits"] += 1
        
        # Sort by hits and leaf status
        sorted_hot = sorted(hot_map.values(), key=lambda x: (x["is_leaf"], x["hits"]), reverse=True)
        return sorted_hot[:5]

    def get_android_runtime_signals(self) -> List[AndroidRuntimeSignal]:
        with self._lock:
            return list(self._android_runtime_signals)

    def get_android_failure_contexts(self) -> List[AndroidFailureContext]:
        with self._lock:
            return list(self._android_failure_contexts)

    def get_android_runtime_diagnostics(self) -> List[AndroidDiagnostic]:
        with self._lock:
            return list(self._android_runtime_diagnostics)

    def get_android_runtime_tags(self) -> List[str]:
        with self._lock:
            tags = {signal.category for signal in self._android_runtime_signals}
        return sorted(tags)

    def get_android_runtime_summary(self) -> dict:
        with self._lock:
            categories = {}
            for signal in self._android_runtime_signals:
                categories[signal.category] = categories.get(signal.category, 0) + 1
            return {
                "count": len(self._android_runtime_signals),
                "categories": dict(sorted(categories.items(), key=lambda item: item[0])),
                "signals": [_dump_model(signal) for signal in self._android_runtime_signals[:12]],
                "failure_contexts": [_dump_model(ctx) for ctx in self._android_failure_contexts[:8]],
                "diagnostics": [_dump_model(diag) for diag in self._android_runtime_diagnostics[:12]],
            }


def _merge_android_signals(
    new_items: List[AndroidRuntimeSignal],
    existing: List[AndroidRuntimeSignal],
    limit: int,
) -> List[AndroidRuntimeSignal]:
    merged = list(new_items) + list(existing)
    deduped = {}
    for signal in merged:
        key = "|".join(
            [
                signal.category,
                signal.file or "",
                str(signal.line or 0),
                signal.symbol or "",
                signal.message,
            ]
        )
        if key not in deduped:
            deduped[key] = signal
    items = sorted(deduped.values(), key=lambda item: (item.category, item.file or "", item.line or 0, item.symbol or ""))
    return items[:limit]


def _merge_android_failure_contexts(
    new_items: List[AndroidFailureContext],
    existing: List[AndroidFailureContext],
    limit: int,
) -> List[AndroidFailureContext]:
    merged = list(new_items) + list(existing)
    deduped = {}
    for ctx in merged:
        key = "|".join(
            [
                ctx.failure_kind,
                ctx.stage,
                ",".join(ctx.implicated_modules),
                ",".join(ctx.implicated_files),
                ",".join(ctx.implicated_symbols),
            ]
        )
        if key not in deduped:
            deduped[key] = ctx
    items = sorted(deduped.values(), key=lambda item: (item.failure_kind, item.stage))
    return items[:limit]


def _merge_android_diagnostics(
    new_items: List[AndroidDiagnostic],
    existing: List[AndroidDiagnostic],
    limit: int,
) -> List[AndroidDiagnostic]:
    merged = list(new_items) + list(existing)
    deduped = {}
    for diag in merged:
        key = "|".join(
            [
                diag.code,
                diag.message,
                diag.source_path or "",
                str(diag.line or 0),
                str(diag.column or 0),
            ]
        )
        if key not in deduped:
            deduped[key] = diag
    items = sorted(deduped.values(), key=lambda item: (item.code, item.source_path or ""))
    return items[:limit]


def _dump_model(model):
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()
