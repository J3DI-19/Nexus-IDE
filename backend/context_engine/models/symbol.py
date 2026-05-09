from pydantic import BaseModel
from typing import List, Optional, Dict

class Symbol(BaseModel):
    name: str
    type: str  # "class", "function", "method", "variable"
    start_line: int
    end_line: int
    docstring: Optional[str] = None
    parent_id: Optional[str] = None

class DependencyEdge(BaseModel):
    source_id: str  # Could be file rel_path or symbol_id (e.g. file_path:symbol_name)
    target_id: str
    raw_target: Optional[str] = None  # Original AST string before resolution
    type: str  # "import", "call", "inheritance", "composition", "reference"
    is_resolved: bool = False
    is_external: bool = False
    metadata: Dict[str, str] = {} # Optional context like line number
