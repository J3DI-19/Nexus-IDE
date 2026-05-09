from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from ..models.file import FileMetadata

class ScoreComponent(BaseModel):
    factor: str
    points: float
    reason: str
    path: Optional[List[str]] = None

class RetrievalQuery(BaseModel):
    task: str
    mode: str = "feature" # Using string to avoid circular import with prompt_builder
    active_file: Optional[str] = None
    selected_files: List[str] = Field(default_factory=list)
    preferred_symbols: List[str] = Field(default_factory=list)
    framework_focus: Optional[str] = None
    include_slices: bool = False

from ..models.extraction import CodeSlice

class ContextCandidate(BaseModel):
    file_metadata: FileMetadata
    score: float
    score_breakdown: List[ScoreComponent]
    matched_symbols: List[str] = Field(default_factory=list)
    matched_artifacts: List[str] = Field(default_factory=list)
    relationship_path: List[str] = Field(default_factory=list) # e.g. ["main.py", "auth.py"]
    slices: List[CodeSlice] = Field(default_factory=list)
