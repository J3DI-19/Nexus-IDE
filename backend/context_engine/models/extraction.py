from pydantic import BaseModel
from typing import List, Dict, Any
from .file import FileMetadata
from .symbol import Symbol, DependencyEdge
from .artifact import FrameworkArtifact

class ExtractionResult(BaseModel):
    file_metadata: FileMetadata
    symbols: List[Symbol] = []
    dependency_edges: List[DependencyEdge] = []
    artifacts: List[FrameworkArtifact] = []
