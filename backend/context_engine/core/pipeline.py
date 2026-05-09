import os
import time
from pathlib import Path
from typing import List, Optional

from .scanner import fast_recursive_scan, compute_file_hash
from .classifier import ProjectClassifier
from ..models.project import ProjectMetadata
from ..models.file import FileMetadata
from ..models.extraction import ExtractionResult
from ..adapters.registry import registry
from ..index.manager import IndexManager
from ..index.resolver import GraphResolver
from ..retrieval.engine import RetrievalEngine
from ..retrieval.models import RetrievalQuery, ContextCandidate
from ..extraction.engine import ExtractionEngine
from ..prompt_builder.engine import AdvancedPromptBuilder
from ..prompt_builder.models import PromptMode
from ..impact.analyzer import ImpactAnalyzer
from ..impact.models import ImpactQuery, ImpactResult
from ..runtime.analyzer import RuntimeAnalyzer

class ContextPipeline:
    def __init__(self):
        self.classifier = ProjectClassifier()
        self.index = IndexManager()
        self.retrieval = RetrievalEngine(self.index)
        self.impact = ImpactAnalyzer(self.index)
        self.runtime = RuntimeAnalyzer()
        self.extraction: Optional[ExtractionEngine] = None
        self.prompt_builder = AdvancedPromptBuilder()
        self.root_path: Optional[str] = None
        self.project_metadata: Optional[ProjectMetadata] = None

    def initialize_project(self, root_path: str) -> ProjectMetadata:
        """Full scan and initial indexing of the project."""
        self.root_path = root_path
        root = Path(root_path).resolve()
        all_files = fast_recursive_scan(str(root))
        
        self.project_metadata = self.classifier.detect_frameworks(root, all_files)
        
        # Reset index for full re-scan
        self.index.clear()
        self.runtime.clear()
        
        for rel_path in all_files:
            self._process_file(root, rel_path)
            
        # Initialize extraction engine with root_path
        self.extraction = ExtractionEngine(root_path, self.index)
        
        # 5. Graph Resolution (Stabilization Phase)
        resolver = GraphResolver(self.index)
        resolver.resolve_graph()
            
        return self.project_metadata

    def retrieve(self, query: RetrievalQuery) -> List[ContextCandidate]:
        """
        Executes retrieval and optionally populates semantic slices.
        """
        if not self.extraction:
            return []

        candidates = self.retrieval.retrieve(query, runtime=self.runtime)
        
        if query.include_slices:
            # Populate slices for each candidate
            for cand in candidates:
                extracted = self.extraction._extract_single_file(
                    cand.file_metadata.rel_path,
                    reason=f"Retrieved: {cand.score} pts",
                    matched_symbols=cand.matched_symbols,
                    runtime=self.runtime
                )
                if extracted:
                    cand.slices = extracted.slices
                    
        return candidates

    def assemble_prompt(self, query: RetrievalQuery, mode: PromptMode = PromptMode.FEATURE) -> str:
        """
        The main high-level method to go from intent to a finalized prompt.
        """
        if not self.extraction:
            return "Context Engine not initialized. Please open a project first."

        # 1. Retrieval (Pass Runtime)
        candidates = self.retrieve(query)
        
        # 2. Extraction (Already performed if include_slices was true, but assemble usually needs full context context)
        context = self.extraction.extract_context(query.active_file, candidates, runtime=self.runtime)
        
        # 3. Impact Analysis
        impact_result = None
        if query.active_file:
            impact_query = ImpactQuery(active_file=query.active_file, max_depth=3)
            impact_result = self.impact.analyze(impact_query)
        
        # 4. Assembly (Pass Runtime Artifacts)
        runtime_artifacts = self.runtime.get_active_artifacts()
        return self.prompt_builder.build_prompt(
            query, 
            context, 
            impact=impact_result, 
            mode=mode,
            runtime_artifacts=runtime_artifacts
        )

    def update_file(self, root_path: str, rel_path: str):
        """Selective re-indexing for a single file."""
        root = Path(root_path).resolve()
        self._process_file(root, rel_path)

    def _process_file(self, root: Path, rel_path: str):
        abs_path = root / rel_path
        if not abs_path.is_file():
            return

        # 1. Basic Telemetry
        mtime = os.path.getmtime(abs_path)
        file_hash = compute_file_hash(str(abs_path))
        
        # Check if already indexed and unchanged (Incremental foundation)
        existing = self.index.get_file_metadata(rel_path)
        if existing and existing.hash == file_hash:
            return

        # 2. Classification & Language detection
        classification = self.classifier.classify_file(rel_path)
        ext = os.path.splitext(rel_path)[1].lower()
        
        file_metadata = FileMetadata(
            rel_path=rel_path,
            hash=file_hash,
            last_modified=mtime,
            language=ext.replace(".", ""),
            classification=classification
        )

        # 3. Extraction via Adapter
        adapter = registry.get_adapter_for_file(rel_path)
        symbols = []
        edges = []
        artifacts = []
        
        if adapter:
            try:
                with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                symbols = adapter.extract_symbols(content, rel_path)
                edges = adapter.extract_dependencies(content, rel_path)
                
                framework_adapters = registry.get_framework_adapters_for_file(rel_path)
                for fw_adapter in framework_adapters:
                    artifacts.extend(fw_adapter.extract_artifacts(content, rel_path))
                    
            except Exception as e:
                print(f"[Pipeline] Extraction failed for {rel_path}: {e}")

        # 4. Update Index
        result = ExtractionResult(
            file_metadata=file_metadata,
            symbols=symbols,
            dependency_edges=edges,
            artifacts=artifacts
        )
        self.index.register_extraction_result(result)

# Global singleton
pipeline = ContextPipeline()
