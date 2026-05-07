from typing import List, Dict, Optional
from .models import RetrievalQuery, ContextCandidate
from .strategies import RetrievalStrategy, DefaultDeterministicStrategy
from ..index.manager import IndexManager
from ..runtime.analyzer import RuntimeAnalyzer

class RetrievalEngine:
    def __init__(self, index: IndexManager):
        self.index = index
        self._strategies: Dict[str, RetrievalStrategy] = {
            "default": DefaultDeterministicStrategy()
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

# The engine is usually instantiated per project or as a singleton managing an index.
