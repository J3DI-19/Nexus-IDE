from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from ..models.file import FileMetadata
from ..models.artifact import FrameworkArtifact
from ..retrieval.models import ScoreComponent

class ImpactQuery(BaseModel):
    active_file: str
    changed_symbols: List[str] = Field(default_factory=list)
    max_depth: int = 3

class ImpactCandidate(BaseModel):
    file_metadata: FileMetadata
    impact_score: float
    score_breakdown: List[ScoreComponent]
    affected_symbols: List[str] = Field(default_factory=list)
    affected_artifacts: List[FrameworkArtifact] = Field(default_factory=list)
    relationship_path: List[str] = Field(default_factory=list) # path of file/symbol dependencies
    relationship_types: List[str] = Field(default_factory=list) # types of edges in the path
    traversal_depth: int

class ImpactResult(BaseModel):
    query: ImpactQuery
    candidates: List[ImpactCandidate] = Field(default_factory=list)
