from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from ..models.symbol import Symbol
from ..models.artifact import FrameworkArtifact

class CodeSlice(BaseModel):
    content: str
    start_line: int
    end_line: int
    reason: str

class ExtractedFile(BaseModel):
    rel_path: str
    classification: str
    symbols: List[Symbol] = Field(default_factory=list)
    slices: List[CodeSlice] = Field(default_factory=list)
    imports: List[str] = Field(default_factory=list)
    artifacts: List[FrameworkArtifact] = Field(default_factory=list)
    reason: str

class ExtractionContext(BaseModel):
    active_file: Optional[ExtractedFile] = None
    related_files: List[ExtractedFile] = Field(default_factory=list)
    global_artifacts: Dict[str, Any] = Field(default_factory=dict)
