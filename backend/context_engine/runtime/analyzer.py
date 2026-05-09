from typing import List, Optional
from .models import RuntimeArtifact
from .detectors import RuntimeDetector

class RuntimeAnalyzer:
    def __init__(self):
        self.detector = RuntimeDetector()
        self._current_artifacts: List[RuntimeArtifact] = []

    def ingest_log(self, log: str):
        artifact = self.detector.detect_and_parse(log)
        if artifact:
            # Maintain a rolling buffer of top 5 artifacts
            self._current_artifacts.insert(0, artifact)
            self._current_artifacts = self._current_artifacts[:5]
        return artifact

    def get_active_artifacts(self) -> List[RuntimeArtifact]:
        return self._current_artifacts

    def clear(self):
        self._current_artifacts = []
        
    def get_referenced_files(self) -> List[str]:
        files = set()
        for art in self._current_artifacts:
            for frame in art.frames:
                files.add(frame.file_path)
        return list(files)

    def get_referenced_symbols(self) -> List[str]:
        symbols = set()
        for art in self._current_artifacts:
            for frame in art.frames:
                if frame.symbol_name:
                    symbols.add(frame.symbol_name)
        return list(symbols)

    def get_execution_chains(self) -> List[List[str]]:
        """Returns a list of execution chains (ordered list of file:symbol) from stack traces."""
        chains = []
        for art in self._current_artifacts:
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
        for art in self._current_artifacts:
            for i, frame in enumerate(art.frames):
                if frame.symbol_name:
                    key = f"{frame.file_path}:{frame.symbol_name}"
                    if key not in hot_map:
                        hot_map[key] = {"name": frame.symbol_name, "file": frame.file_path, "hits": 0, "is_leaf": i == 0}
                    hot_map[key]["hits"] += 1
        
        # Sort by hits and leaf status
        sorted_hot = sorted(hot_map.values(), key=lambda x: (x["is_leaf"], x["hits"]), reverse=True)
        return sorted_hot[:5]
