from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class FileMetadata(BaseModel):
    rel_path: str
    hash: str
    last_modified: float
    language: str
    classification: str  # e.g., "logic", "ui", "config"
    
class ContextCandidate(BaseModel):
    entity_id: str
    score: float
    reason: str
