from abc import ABC, abstractmethod
from typing import List, Optional
from .models import RetrievalQuery, ContextCandidate, ScoreComponent
from ..index.manager import IndexManager
from ..runtime.analyzer import RuntimeAnalyzer
from . import scorers

class RetrievalStrategy(ABC):
    @abstractmethod
    def execute(self, query: RetrievalQuery, index: IndexManager, runtime: Optional[RuntimeAnalyzer] = None) -> List[ContextCandidate]:
        pass

class DefaultDeterministicStrategy(RetrievalStrategy):
    """
    Legacy File-Centric Strategy.
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
            
            s_intent = scorers.score_modification_intent(query, metadata, index)
            if s_intent: breakdown.append(s_intent)
            
            s_hub = scorers.score_hub_penalty(query, metadata, index)
            if s_hub: breakdown.append(s_hub)
            
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
                
                # Pick the best path from breakdown for explainability
                best_path = []
                for comp in sorted(breakdown, key=lambda x: x.points, reverse=True):
                    if comp.path:
                        best_path = comp.path
                        break

                candidates.append(ContextCandidate(
                    file_metadata=metadata,
                    score=total_score,
                    score_breakdown=breakdown,
                    matched_symbols=[s.name for s in index.get_symbols_for_file(rel_path)],
                    matched_artifacts=[a.artifact_type for a in artifacts],
                    relationship_path=best_path
                ))
        
        # Rank by score descending
        candidates.sort(key=lambda x: x.score, reverse=True)
        return candidates

from .symbol_scorers import SymbolScorer

class SymbolCentricStrategy(RetrievalStrategy):
    """
    Phase 8B: Symbol-Centric Strategy.
    Scores symbols individually, then aggregates them to file-level.
    """
    def execute(self, query: RetrievalQuery, index: IndexManager, runtime: Optional[RuntimeAnalyzer] = None) -> List[ContextCandidate]:
        candidates = []
        sym_scorer = SymbolScorer(index)
        
        for rel_path, metadata in index.files.items():
            if rel_path == query.active_file:
                continue
            
            symbols = index.get_symbols_for_file(rel_path)
            
            # 1. High-Precision Symbol Scoring
            all_symbol_breakdowns = []
            for sym in symbols:
                sym_breakdown = sym_scorer.score_symbol(query, sym, rel_path, runtime)
                if sym_breakdown:
                    all_symbol_breakdowns.append((sym.name, sym_breakdown))
            
            # 2. File-Level Architectural Scoring
            file_breakdown = []
            
            # MODE BIAS: Adjust base scores based on task intent
            if query.mode == "feature":
                # Features often happen in models or utilities
                if metadata.classification in {"model", "utility"}:
                    file_breakdown.append(ScoreComponent(factor="Feature Intent Bias", points=20.0, reason="Logic layer prioritized for feature tasks"))
            elif query.mode == "refactor":
                # Refactors target utilities and shared abstractions
                if metadata.classification == "utility":
                    file_breakdown.append(ScoreComponent(factor="Refactor Intent Bias", points=25.0, reason="Shared utilities prioritized for refactoring"))

            s_prox = scorers.score_proximity(query, metadata)
            if s_prox: file_breakdown.append(s_prox)
            
            s_class = scorers.score_classification(query, metadata)
            if s_class: file_breakdown.append(s_class)
            
            s_intent = scorers.score_modification_intent(query, metadata, index)
            if s_intent: file_breakdown.append(s_intent)
            
            s_hub = scorers.score_hub_penalty(query, metadata, index)
            if s_hub: file_breakdown.append(s_hub)
            
            s_fw = scorers.score_framework_artifacts(query, metadata, index)
            if s_fw: file_breakdown.append(s_fw)

            s_cfg = scorers.score_config_relevance(query, metadata, index)
            if s_cfg: file_breakdown.append(s_cfg)
            
            s_cpp = scorers.score_cpp_relationships(query, metadata, index)
            if s_cpp: file_breakdown.append(s_cpp)
            
            s_dep = scorers.score_dependencies(query, metadata, index)
            if s_dep: file_breakdown.append(s_dep)

            # 3. Aggregation Logic
            # Final Score = Max(Symbol Score) + File Architecture Score + Density Bonus
            # We prioritize the "best" symbol match as the primary anchor
            max_symbol_score = 0
            best_symbol_breakdown = []
            matched_sym_names = []
            
            for sym_name, s_breakdown in all_symbol_breakdowns:
                matched_sym_names.append(sym_name)
                total_sym = sum(c.points for c in s_breakdown)
                if total_sym > max_symbol_score:
                    max_symbol_score = total_sym
                    best_symbol_breakdown = s_breakdown

            # Density Bonus: +5.0 per additional matching symbol (max 15.0)
            density_bonus = min((len(all_symbol_breakdowns) - 1) * 5.0, 15.0) if len(all_symbol_breakdowns) > 1 else 0
            if density_bonus > 0:
                file_breakdown.append(ScoreComponent(
                    factor="Symbol Density",
                    points=density_bonus,
                    reason=f"File contains {len(all_symbol_breakdowns)} relevant symbols"
                ))

            total_score = max_symbol_score + sum(c.points for c in file_breakdown)
            
            if total_score > 0:
                full_breakdown = best_symbol_breakdown + file_breakdown
                artifacts = index.get_artifacts_for_file(rel_path)
                
                # Pick best path from ANY component
                best_path = []
                for comp in sorted(full_breakdown, key=lambda x: x.points, reverse=True):
                    if comp.path:
                        best_path = comp.path
                        break

                candidates.append(ContextCandidate(
                    file_metadata=metadata,
                    score=total_score,
                    score_breakdown=full_breakdown,
                    matched_symbols=matched_sym_names,
                    matched_artifacts=[a.artifact_type for a in artifacts],
                    relationship_path=best_path
                ))
            
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
