from pydantic import BaseModel
from typing import Dict, Any, List

class FrameworkArtifact(BaseModel):
    artifact_type: str  # "API_ROUTE", "REACT_COMPONENT", "REACT_HOOK", "SERVICE", "MODEL"
    name: str
    rel_path: str
    start_line: int
    end_line: int
    metadata: Dict[str, Any] = {}
    relationships: List[str] = [] # e.g. linked symbols or paths
