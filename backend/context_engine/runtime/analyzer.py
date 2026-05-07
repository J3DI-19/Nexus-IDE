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
            # For now, we only keep the latest critical error
            self._current_artifacts = [artifact]
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
