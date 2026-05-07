from abc import ABC, abstractmethod
from typing import List, Optional
from .models import RetrievalQuery, ContextCandidate
from ..index.manager import IndexManager
from ..runtime.analyzer import RuntimeAnalyzer
from . import scorers

class RetrievalStrategy(ABC):
    @abstractmethod
    def execute(self, query: RetrievalQuery, index: IndexManager, runtime: Optional[RuntimeAnalyzer] = None) -> List[ContextCandidate]:
        pass

class DefaultDeterministicStrategy(RetrievalStrategy):
    """
    Combines proximity, classification, name similarity, and dependencies.
    """
    def execute(self, query: RetrievalQuery, index: IndexManager, runtime: Optional[RuntimeAnalyzer] = None) -> List[ContextCandidate]:
        candidates = []
        
        for rel_path, metadata in index.files.items():
            if rel_path == query.active_file:
                continue
                
            breakdown = []
            
            # Run scorers
            if runtime:
                s_runtime = scorers.score_runtime_relevance(query, metadata, runtime, index)
                if s_runtime: breakdown.append(s_runtime)

            s_prox = scorers.score_proximity(query, metadata)
            if s_prox: breakdown.append(s_prox)
            
            s_class = scorers.score_classification(query, metadata)
            if s_class: breakdown.append(s_class)
            
            s_name = scorers.score_name_similarity(query, metadata)
            if s_name: breakdown.append(s_name)
            
            s_fw = scorers.score_framework_artifacts(query, metadata, index)
            if s_fw: breakdown.append(s_fw)

            s_cfg = scorers.score_config_relevance(query, metadata, index)
            if s_cfg: breakdown.append(s_cfg)
            
            s_cpp = scorers.score_cpp_relationships(query, metadata, index)
            if s_cpp: breakdown.append(s_cpp)
            
            s_dep = scorers.score_dependencies(query, metadata, index)
            if s_dep: breakdown.append(s_dep)
            
            if breakdown:
                total_score = sum(c.points for c in breakdown)
                artifacts = index.get_artifacts_for_file(rel_path)
                candidates.append(ContextCandidate(
                    file_metadata=metadata,
                    score=total_score,
                    score_breakdown=breakdown,
                    matched_symbols=[s.name for s in index.get_symbols_for_file(rel_path)],
                    matched_artifacts=[a.artifact_type for a in artifacts]
                ))
        
        # Rank by score descending
        candidates.sort(key=lambda x: x.score, reverse=True)
        return candidates

class DependencyOnlyStrategy(RetrievalStrategy):
    """
    Strictly focuses on the import graph.
    """
    def execute(self, query: RetrievalQuery, index: IndexManager) -> List[ContextCandidate]:
        if not query.active_file:
            return []
            
        candidates = []
        active_deps = index.get_dependencies(query.active_file)
        dep_paths = {d.target_id for d in active_deps if d.type == "import"}
        
        for rel_path, metadata in index.files.items():
            # Check for matches in the import paths
            is_match = False
            for dp in dep_paths:
                if dp in rel_path or rel_path in dp:
                    is_match = True
                    break
            
            if is_match:
                comp = scorers.score_dependencies(query, metadata, index)
                breakdown = [comp] if comp else []
                candidates.append(ContextCandidate(
                    file_metadata=metadata,
                    score=comp.points if comp else 0,
                    score_breakdown=breakdown
                ))
        
        return candidates
