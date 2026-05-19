import os
from typing import List, Optional, Dict
from .models import ScoreComponent, RetrievalQuery
from ..models.file import FileMetadata
from ..models.symbol import Symbol
from ..index.manager import IndexManager
from ..runtime.analyzer import RuntimeAnalyzer

QUERY_SYNONYMS = {
    "route": {"routing", "router", "routes"},
    "response": {"responses", "encoder", "encoders"},
    "schema": {"openapi", "model", "models", "params", "param"},
    "parameter": {"param", "params", "field"},
    "blueprint": {"blueprints", "scaffold", "register"},
    "context": {"ctx", "globals", "request"},
}

def _normalized_query_terms(task: str) -> List[str]:
    raw = task.lower().replace("-", " ").replace("_", " ").split()
    terms = set(raw)
    for token in raw:
        terms.update(QUERY_SYNONYMS.get(token, set()))
        for key, values in QUERY_SYNONYMS.items():
            if token in values:
                terms.add(key)
    return [term for term in terms if len(term) > 2]

class SymbolScorer:
    def __init__(self, index: IndexManager):
        self.index = index

    def score_symbol(self, query: RetrievalQuery, symbol: Symbol, file_path: str, runtime: Optional[RuntimeAnalyzer] = None) -> List[ScoreComponent]:
        """
        Calculates high-precision scores for an individual symbol.
        """
        breakdown = []
        
        # 1. Runtime Relevance
        if runtime:
            s_runtime = self._score_runtime(symbol, file_path, runtime)
            if s_runtime: breakdown.append(s_runtime)
            
            # Ownership: Does this symbol call a failing symbol?
            s_owner = self._score_ownership(symbol, file_path, runtime)
            if s_owner: breakdown.append(s_owner)
            
        # 2. Name Similarity
        s_name = self._score_name(query, symbol)
        if s_name: breakdown.append(s_name)
        
        # 3. Task Intent
        s_intent = self._score_intent(query, symbol)
        if s_intent: breakdown.append(s_intent)
        
        return breakdown

    def _score_runtime(self, symbol: Symbol, file_path: str, runtime: RuntimeAnalyzer) -> Optional[ScoreComponent]:
        referenced_symbols = runtime.get_referenced_symbols()
        execution_chains = runtime.get_execution_chains()
        
        # Match exact qualified ID in execution chain
        qualified_id = f"{file_path}:{symbol.name}"
        for chain in execution_chains:
            for i, node in enumerate(chain):
                if node == qualified_id:
                    points = 70.0 - (i * 5.0)
                    return ScoreComponent(
                        factor="Symbol Runtime Match",
                        points=max(50.0, points),
                        reason=f"Symbol is in the active execution chain (Position {i})",
                        path=chain[:i+1]
                    )
        
        # Match symbol name in stack trace (Fallback)
        if symbol.name in referenced_symbols:
            return ScoreComponent(
                factor="Symbol Stack Trace Match",
                points=65.0,
                reason=f"Symbol found in active stack trace"
            )
            
        return None

    def _score_ownership(self, symbol: Symbol, file_path: str, runtime: RuntimeAnalyzer) -> Optional[ScoreComponent]:
        """
        Scores symbols that call into known failing symbols (the 'owners' of the bug context).
        """
        execution_chains = runtime.get_execution_chains()
        qualified_id = f"{file_path}:{symbol.name}"
        
        for chain in execution_chains:
            for i, node in enumerate(chain):
                # If a node exists downstream in the chain, this symbol 'owns' the call
                if node == qualified_id and i < len(chain) - 1:
                    # The distance to the failure determines the priority
                    failure_dist = len(chain) - 1 - i
                    points = 55.0 - (failure_dist * 10.0)
                    return ScoreComponent(
                        factor="Symbol Ownership",
                        points=max(25.0, points),
                        reason=f"Symbol calls failing code (Distance: {failure_dist})",
                        path=chain[i:]
                    )
        return None

    def _score_name(self, query: RetrievalQuery, symbol: Symbol) -> Optional[ScoreComponent]:
        task_words = set(_normalized_query_terms(query.task))
        sym_name_lower = symbol.name.lower()
        weak_terms = {"service", "controller", "model", "route", "routes", "handler", "helper", "utils", "doc", "docs"}
        
        for word in task_words:
            if len(word) <= 3 or word in weak_terms:
                continue
            if word in sym_name_lower:
                return ScoreComponent(
                    factor="Symbol Name Similarity",
                    points=18.0,
                    reason=f"Symbol name contains task keyword: '{word}'"
                )
        return None

    def _score_intent(self, query: RetrievalQuery, symbol: Symbol) -> Optional[ScoreComponent]:
        task_lower = query.task.lower()
        query_terms = set(_normalized_query_terms(query.task))
        sym_name_lower = symbol.name.lower()
        
        # Action-based intent matching
        actions = ["validate", "check", "parse", "process", "calculate", "save", "fetch", "render", "handle", "map", "transform", "normalize", "extract"]
        for action in actions:
            if (action in task_lower or action in query_terms) and action in sym_name_lower:
                weight = 42.0 if query.mode == "refactor" and action in {"validate", "parse", "map", "transform", "normalize", "extract"} else 35.0
                return ScoreComponent(
                    factor="Symbol Intent Match",
                    points=weight,
                    reason=f"Symbol matches action '{action}' in task"
                )
        return None
