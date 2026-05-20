from typing import List, Dict, Optional, Any
from pathlib import Path
from .models import RetrievalQuery, ContextCandidate
from .strategies import RetrievalStrategy, DefaultDeterministicStrategy, SymbolCentricStrategy
from ..index.manager import IndexManager
from ..runtime.analyzer import RuntimeAnalyzer
from ..android.retrieval import build_android_retrieval_context
from ..android.summary_service import get_android_summary

class RetrievalEngine:
    def __init__(self, index: IndexManager):
        self.index = index
        self.root_path: Optional[str] = None
        self._strategies: Dict[str, RetrievalStrategy] = {
            "default": SymbolCentricStrategy(),
            "symbol": SymbolCentricStrategy(),
            "legacy": DefaultDeterministicStrategy()
        }

    def register_strategy(self, name: str, strategy: RetrievalStrategy):
        self._strategies[name] = strategy

    def set_root_path(self, root_path: str):
        self.root_path = root_path

    def retrieve(
        self,
        query: RetrievalQuery,
        strategy_name: str = "default",
        limit: int = 10,
        runtime: Optional[RuntimeAnalyzer] = None,
        android_context: Optional[dict] = None,
    ) -> List[ContextCandidate]:
        """
        Executes deterministic retrieval based on the chosen strategy.
        """
        strategy = self._strategies.get(strategy_name, self._strategies["default"])
        effective_android_context = android_context or self._resolve_android_context(query, runtime)
        results = strategy.execute(query, self.index, runtime=runtime, android_context=effective_android_context)
        
        # Return top N results
        return results[:limit]

    def retrieve_compare(self, query: RetrievalQuery, limit: int = 5, runtime: Optional[RuntimeAnalyzer] = None) -> Dict[str, Any]:
        """
        Runs both File-Centric and Symbol-Centric strategies and compares results.
        Used for Phase 8B validation.
        """
        android_context = self._resolve_android_context(query, runtime)
        file_results = self.retrieve(query, strategy_name="default", limit=limit, runtime=runtime, android_context=android_context)
        symbol_results = self.retrieve(query, strategy_name="symbol", limit=limit, runtime=runtime, android_context=android_context)
        
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

    def _resolve_android_context(self, query: RetrievalQuery, runtime: Optional[RuntimeAnalyzer]) -> Optional[dict]:
        if not query.active_file:
            return None

        if query.android_context:
            return query.android_context

        summary = None
        if self.root_path:
            try:
                summary = get_android_summary(Path(self.root_path), runtime_analyzer=runtime)
            except Exception:
                summary = None

        if summary:
            context = build_android_retrieval_context(
                query=query,
                index=self.index,
                runtime=runtime,
                manifests=summary.manifests,
                relationships=summary.relationships,
                modules=summary.modules,
                integration_signals=summary.integrations.signals,
                enabled=summary.enabled,
                is_android_project=summary.is_android_project,
            )
            if hasattr(context, "model_dump"):
                return context.model_dump()
            return context.dict()

        context = build_android_retrieval_context(
            query=query,
            index=self.index,
            runtime=runtime,
            manifests=[],
            relationships=[],
            modules=[],
            integration_signals=[],
            enabled=False,
            is_android_project=False,
        )
        if hasattr(context, "model_dump"):
            return context.model_dump()
        return context.dict()

# The engine is usually instantiated per project or as a singleton managing an index.
