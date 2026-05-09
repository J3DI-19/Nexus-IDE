from typing import List, Dict, Optional, Any
from .models import RetrievalQuery, ContextCandidate
from .strategies import RetrievalStrategy, DefaultDeterministicStrategy, SymbolCentricStrategy
from ..index.manager import IndexManager
from ..runtime.analyzer import RuntimeAnalyzer

class RetrievalEngine:
    def __init__(self, index: IndexManager):
        self.index = index
        self._strategies: Dict[str, RetrievalStrategy] = {
            "default": SymbolCentricStrategy(),
            "symbol": SymbolCentricStrategy(),
            "legacy": DefaultDeterministicStrategy()
        }

    def register_strategy(self, name: str, strategy: RetrievalStrategy):
        self._strategies[name] = strategy

    def retrieve(self, query: RetrievalQuery, strategy_name: str = "default", limit: int = 10, runtime: Optional[RuntimeAnalyzer] = None) -> List[ContextCandidate]:
        """
        Executes deterministic retrieval based on the chosen strategy.
        """
        strategy = self._strategies.get(strategy_name, self._strategies["default"])
        results = strategy.execute(query, self.index, runtime=runtime)
        
        # Return top N results
        return results[:limit]

    def retrieve_compare(self, query: RetrievalQuery, limit: int = 5, runtime: Optional[RuntimeAnalyzer] = None) -> Dict[str, Any]:
        """
        Runs both File-Centric and Symbol-Centric strategies and compares results.
        Used for Phase 8B validation.
        """
        file_results = self.retrieve(query, strategy_name="default", limit=limit, runtime=runtime)
        symbol_results = self.retrieve(query, strategy_name="symbol", limit=limit, runtime=runtime)
        
        comparison = {
            "query": query.task,
            "active_file": query.active_file,
            "file_centric": [
                {"path": c.file_metadata.rel_path, "score": c.score} 
                for c in file_results
            ],
            "symbol_centric": [
                {"path": c.file_metadata.rel_path, "score": c.score} 
                for c in symbol_results
            ],
            "divergence": self._calculate_divergence(file_results, symbol_results)
        }
        return comparison

    def _calculate_divergence(self, list_a: List[ContextCandidate], list_b: List[ContextCandidate]) -> float:
        set_a = {c.file_metadata.rel_path for c in list_a}
        set_b = {c.file_metadata.rel_path for c in list_b}
        if not set_a and not set_b: return 0.0
        intersection = set_a.intersection(set_b)
        union = set_a.union(set_b)
        return 1.0 - (len(intersection) / len(union))

# The engine is usually instantiated per project or as a singleton managing an index.
