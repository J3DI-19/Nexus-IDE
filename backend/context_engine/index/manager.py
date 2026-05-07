from typing import Dict, List, Optional, Set
from ..models.file import FileMetadata
from ..models.symbol import Symbol, DependencyEdge
from ..models.extraction import ExtractionResult
from ..models.artifact import FrameworkArtifact

class IndexManager:
    def __init__(self):
        # Primary storage
        self.files: Dict[str, FileMetadata] = {}
        self.symbols: Dict[str, List[Symbol]] = {}  # rel_path -> symbols
        self.edges: List[DependencyEdge] = []
        self.artifacts: Dict[str, List[FrameworkArtifact]] = {} # rel_path -> artifacts
        
        # Accelerated lookup structures
        self._symbol_to_file: Dict[str, str] = {}  # symbol_name -> rel_path
        self._import_graph: Dict[str, Set[str]] = {}  # file -> set of imported files/modules

    def register_extraction_result(self, result: ExtractionResult):
        rel_path = result.file_metadata.rel_path
        
        # 1. Update File Metadata
        self.files[rel_path] = result.file_metadata
        
        # 2. Update Symbols
        self.symbols[rel_path] = result.symbols
        for symbol in result.symbols:
            self._symbol_to_file[symbol.name] = rel_path
            
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
        return self.files.get(rel_path)

    def get_symbols_for_file(self, rel_path: str) -> List[Symbol]:
        return self.symbols.get(rel_path, [])

    def get_file_for_symbol(self, symbol_name: str) -> Optional[str]:
        return self._symbol_to_file.get(symbol_name)

    def get_dependencies(self, rel_path: str) -> List[DependencyEdge]:
        prefix = f"{rel_path}:"
        return [e for e in self.edges if e.source_id == rel_path or e.source_id.startswith(prefix)]

    def get_artifacts_for_file(self, rel_path: str) -> List[FrameworkArtifact]:
        return self.artifacts.get(rel_path, [])

    def clear(self):
        self.files.clear()
        self.symbols.clear()
        self.edges.clear()
        self.artifacts.clear()
        self._symbol_to_file.clear()
        self._import_graph.clear()
