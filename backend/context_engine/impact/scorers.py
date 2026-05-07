from typing import List, Optional, Dict, Set
from .models import ImpactCandidate, ImpactQuery, ScoreComponent
from ..index.manager import IndexManager
from ..index.traversal import GraphTraversalEngine, TraversalResult

class ImpactScorer:
    def __init__(self, index: IndexManager):
        self.index = index

    def score_traversal_depth(self, depth: int) -> ScoreComponent:
        # Closer depth = higher impact score
        points = max(10, 50 - (depth * 10))
        return ScoreComponent(
            factor="Traversal Depth",
            points=float(points),
            reason=f"Depth {depth} from changed source"
        )

    def score_framework_criticality(self, artifacts: List) -> Optional[ScoreComponent]:
        if not artifacts:
            return None
            
        types = set(a.artifact_type for a in artifacts)
        if "API_ROUTE" in types:
            return ScoreComponent(factor="Architectural Impact", points=40.0, reason="Impacts a public API Route")
        elif "REACT_COMPONENT" in types:
            return ScoreComponent(factor="Architectural Impact", points=30.0, reason="Impacts a UI Component")
        elif "MODEL" in types or "SCHEMA" in types:
            return ScoreComponent(factor="Architectural Impact", points=45.0, reason="Impacts Data Model/Schema")
            
        return ScoreComponent(factor="Architectural Impact", points=20.0, reason="Impacts framework artifacts")
