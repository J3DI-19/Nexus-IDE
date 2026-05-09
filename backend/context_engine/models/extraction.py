from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from .file import FileMetadata
from .symbol import Symbol, DependencyEdge
from .artifact import FrameworkArtifact

class CodeSlice(BaseModel):
    content: str
    start_line: int
    end_line: int
    reason: str
    anchor_symbol: Optional[str] = None
    confidence: float = 1.0
    expansion_type: str = "exact"

class ExtractionResult(BaseModel):
    file_metadata: FileMetadata
    symbols: List[Symbol] = []
    dependency_edges: List[DependencyEdge] = []
    artifacts: List[FrameworkArtifact] = []
