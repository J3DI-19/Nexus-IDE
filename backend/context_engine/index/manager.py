from typing import Dict, List, Optional, Set, Tuple
import threading
from ..models.file import FileMetadata
from ..models.symbol import Symbol, DependencyEdge
from ..models.extraction import ExtractionResult
from ..models.artifact import FrameworkArtifact

class IndexManager:
    def __init__(self):
        self._lock = threading.RLock()
        # Primary storage
        self.files: Dict[str, FileMetadata] = {}
        self.symbols: Dict[str, List[Symbol]] = {}  # rel_path -> symbols
        self.edges: List[DependencyEdge] = []
        self.artifacts: Dict[str, List[FrameworkArtifact]] = {} # rel_path -> artifacts
        
        # Accelerated lookup structures
        self._import_graph: Dict[str, Set[str]] = {}  # file -> set of imported files/modules
        self._symbol_registry: Dict[str, Set[str]] = {} # symbol_name -> set of files

    def register_extraction_result(self, result: ExtractionResult):
        with self._lock:
            rel_path = result.file_metadata.rel_path

            # 1. Update File Metadata
            self.files[rel_path] = result.file_metadata

            # 2. Update Symbols
            self.symbols[rel_path] = result.symbols
            for sym in result.symbols:
                if sym.name not in self._symbol_registry:
                    self._symbol_registry[sym.name] = set()
                self._symbol_registry[sym.name].add(rel_path)

            # 3. Update Dependency Edges
            prefix = f"{rel_path}:"
            self.edges = [e for e in self.edges if e.source_id != rel_path and not e.source_id.startswith(prefix)]
            self.edges.extend(result.dependency_edges)

            # 4. Update Import Graph
            self._import_graph[rel_path] = {
                edge.target_id for edge in result.dependency_edges
                if edge.type == "import"
            }

            # 5. Update Artifacts
            self.artifacts[rel_path] = result.artifacts

    def get_file_metadata(self, rel_path: str) -> Optional[FileMetadata]:
        with self._lock:
            return self.files.get(rel_path)

    def get_symbols_for_file(self, rel_path: str) -> List[Symbol]:
        with self._lock:
            return list(self.symbols.get(rel_path, []))

    def get_file_for_symbol(self, symbol_name: str) -> Optional[str]:
        # Return the first file found (highest probability)
        with self._lock:
            files = self._symbol_registry.get(symbol_name)
            return next(iter(files)) if files else None

    def get_dependencies(self, rel_path: str) -> List[DependencyEdge]:
        with self._lock:
            prefix = f"{rel_path}:"
            return [e for e in self.edges if e.source_id == rel_path or e.source_id.startswith(prefix)]

    def get_artifacts_for_file(self, rel_path: str) -> List[FrameworkArtifact]:
        with self._lock:
            return list(self.artifacts.get(rel_path, []))

    def iter_files_items(self) -> List[Tuple[str, FileMetadata]]:
        with self._lock:
            return list(self.files.items())

    def clear(self):
        with self._lock:
            self.files.clear()
            self.symbols.clear()
            self.edges.clear()
            self.artifacts.clear()
            self._import_graph.clear()
            self._symbol_registry.clear()
