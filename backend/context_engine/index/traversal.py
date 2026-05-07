from typing import List, Dict, Set, Optional
from ..models.symbol import DependencyEdge
from .manager import IndexManager

class TraversalResult:
    def __init__(self, target_id: str, path: List[str], depth: int, edge_types: List[str]):
        self.target_id = target_id
        self.path = path
        self.depth = depth
        self.edge_types = edge_types

class GraphTraversalEngine:
    def __init__(self, index: IndexManager):
        self.index = index

    def traverse_outbound(self, start_id: str, max_depth: int = 3, allowed_types: Optional[Set[str]] = None) -> List[TraversalResult]:
        """
        Traverses outbound edges from a starting file or symbol.
        """
        results = []
        visited = set()
        queue = [(start_id, [start_id], 0, [])]

        while queue:
            current_id, path, depth, edge_types = queue.pop(0)
            
            if current_id in visited:
                continue
            visited.add(current_id)

            if depth > 0:
                results.append(TraversalResult(current_id, path, depth, edge_types))

            if depth < max_depth:
                # Find all edges where source is current_id
                # For symbols, source_id might be "file:symbol". We fallback to file-level tracking if needed.
                outbound_edges = [e for e in self.index.edges if e.source_id == current_id]
                
                for edge in outbound_edges:
                    if allowed_types and edge.type not in allowed_types:
                        continue
                    
                    queue.append((
                        edge.target_id,
                        path + [edge.target_id],
                        depth + 1,
                        edge_types + [edge.type]
                    ))

        return results

    def traverse_inbound(self, target_id: str, max_depth: int = 2) -> List[TraversalResult]:
        """
        Traverses inbound edges to find who calls/imports the target.
        """
        results = []
        visited = set()
        queue = [(target_id, [target_id], 0, [])]

        while queue:
            current_id, path, depth, edge_types = queue.pop(0)
            
            if current_id in visited:
                continue
            visited.add(current_id)

            if depth > 0:
                results.append(TraversalResult(current_id, path, depth, edge_types))

            if depth < max_depth:
                inbound_edges = [e for e in self.index.edges if e.target_id == current_id]
                for edge in inbound_edges:
                    queue.append((
                        edge.source_id,
                        path + [edge.source_id],
                        depth + 1,
                        edge_types + [edge.type]
                    ))

        return results
