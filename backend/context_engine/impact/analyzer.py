from typing import List, Dict, Set
from .models import ImpactQuery, ImpactCandidate, ImpactResult
from .scorers import ImpactScorer
from ..index.manager import IndexManager
from ..index.traversal import GraphTraversalEngine

class ImpactAnalyzer:
    def __init__(self, index: IndexManager):
        self.index = index
        self.traversal = GraphTraversalEngine(index)
        self.scorer = ImpactScorer(index)

    def analyze(self, query: ImpactQuery) -> ImpactResult:
        """
        Analyzes downstream dependencies to deterministically find the impact of a change.
        We traverse INBOUND edges because we want to know who depends on the changed file/symbols.
        """
        candidates_map: Dict[str, ImpactCandidate] = {}
        
        # 1. Determine starting nodes
        start_nodes = []
        if query.changed_symbols:
            start_nodes = [f"{query.active_file}:{sym}" for sym in query.changed_symbols]
        else:
            # Fallback to file level
            start_nodes = [query.active_file]
            
        # 2. Traverse inbound dependencies
        for start_id in start_nodes:
            inbound_paths = self.traversal.traverse_inbound(start_id, max_depth=query.max_depth)
            
            for path_result in inbound_paths:
                # Path result target_id might be a file_path or file_path:symbol
                # For impact, we group by file
                target_file = path_result.target_id.split(':')[0]
                
                # Skip the active file itself
                if target_file == query.active_file:
                    continue
                    
                metadata = self.index.get_file_metadata(target_file)
                if not metadata:
                    continue
                    
                # Initialize candidate if not exists
                if target_file not in candidates_map:
                    candidates_map[target_file] = ImpactCandidate(
                        file_metadata=metadata,
                        impact_score=0.0,
                        score_breakdown=[],
                        relationship_path=path_result.path,
                        relationship_types=path_result.edge_types,
                        traversal_depth=path_result.depth,
                        affected_symbols=[],
                        affected_artifacts=self.index.get_artifacts_for_file(target_file)
                    )
                
                cand = candidates_map[target_file]
                
                # We update the deepest traversal to closest
                cand.traversal_depth = min(cand.traversal_depth, path_result.depth)
                
                # Track affected symbol if specific
                if ':' in path_result.target_id:
                    sym_name = path_result.target_id.split(':')[1]
                    if sym_name not in cand.affected_symbols:
                        cand.affected_symbols.append(sym_name)

        # 3. Score and rank candidates
        for rel_path, cand in candidates_map.items():
            breakdown = []
            
            # Score Depth
            depth_score = self.scorer.score_traversal_depth(cand.traversal_depth)
            breakdown.append(depth_score)
            
            # Score Architectural Impact
            arch_score = self.scorer.score_framework_criticality(cand.affected_artifacts)
            if arch_score:
                breakdown.append(arch_score)
                
            # Total score
            cand.impact_score = sum(c.points for c in breakdown)
            cand.score_breakdown = breakdown
            
        # Filter and sort
        sorted_candidates = sorted(candidates_map.values(), key=lambda c: c.impact_score, reverse=True)
        
        return ImpactResult(
            query=query,
            candidates=sorted_candidates
        )
