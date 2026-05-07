from typing import List, Optional, Set
from .models import ExtractedFile, ExtractionContext, CodeSlice
from .slicers import CodeSlicer
from ..retrieval.models import ContextCandidate
from ..index.manager import IndexManager
from ..index.traversal import GraphTraversalEngine
from ..runtime.analyzer import RuntimeAnalyzer

class ExtractionEngine:
    def __init__(self, root_path: str, index: IndexManager):
        self.root_path = root_path
        self.index = index
        self.slicer = CodeSlicer(root_path)
        self.traversal = GraphTraversalEngine(index)

    def extract_context(self, active_file: Optional[str], candidates: List[ContextCandidate], runtime: Optional[RuntimeAnalyzer] = None) -> ExtractionContext:
        """
        Orchestrates extraction for the active file and retrieved candidates.
        """
        context = ExtractionContext()

        # 1. Process Active File (High priority, usually full extraction or key symbols)
        if active_file:
            context.active_file = self._extract_single_file(active_file, "Active File", full=True, runtime=runtime)

        # 2. Process Candidates
        for cand in candidates:
            # We don't want to re-extract the active file if it was also a candidate
            if active_file and cand.file_metadata.rel_path == active_file:
                continue
            
            # Logic: If high score, extract more. If low score, just symbols.
            # Deterministic threshold for "Deep Extraction"
            deep_extract = cand.score >= 40.0
            
            extracted = self._extract_single_file(
                cand.file_metadata.rel_path, 
                reason=f"Retrieved: {cand.score} pts",
                full=deep_extract,
                runtime=runtime
            )
            if extracted:
                context.related_files.append(extracted)

        return context

    def _extract_single_file(self, rel_path: str, reason: str, full: bool = False, runtime: Optional[RuntimeAnalyzer] = None) -> Optional[ExtractedFile]:
        metadata = self.index.get_file_metadata(rel_path)
        if not metadata:
            return None

        symbols = self.index.get_symbols_for_file(rel_path)
        dependencies = self.index.get_dependencies(rel_path)
        artifacts = self.index.get_artifacts_for_file(rel_path)
        
        extracted = ExtractedFile(
            rel_path=rel_path,
            classification=metadata.classification,
            symbols=symbols,
            imports=[d.target_id for d in dependencies if d.type == "import"],
            artifacts=artifacts,
            reason=reason
        )

        runtime_symbols: Set[str] = set()
        runtime_lines: Set[int] = set()
        if runtime:
            for art in runtime.get_active_artifacts():
                for frame in art.frames:
                    if rel_path in frame.file_path: # Match file
                        if frame.symbol_name:
                            runtime_symbols.add(frame.symbol_name)
                        runtime_lines.add(frame.line_number)

        if full:
            # Extract full file content (with limits)
            full_slice = self.slicer.extract_full_file(rel_path, reason)
            if full_slice:
                extracted.slices.append(full_slice)
        else:
            # First prioritize artifacts
            for art in artifacts:
                art_slice = self.slicer.extract_lines(rel_path, art.start_line, art.end_line, f"Framework Artifact: {art.artifact_type} ({art.name})")
                if art_slice:
                    extracted.slices.append(art_slice)
            
            # Prioritize runtime-failed symbols
            for sym in symbols:
                if sym.name in runtime_symbols or (sym.start_line <= max(runtime_lines, default=-1) <= sym.end_line):
                    sym_slice = self.slicer.extract_symbol(rel_path, sym, reason + " [RUNTIME ERROR]")
                    if sym_slice:
                        extracted.slices.append(sym_slice)
                    
            # Then Relationship-Aware Extraction: Find symbols with inbound calls
            called_symbols = set()
            for sym in symbols:
                start_id = f"{rel_path}:{sym.name}"
                inbounds = self.traversal.traverse_inbound(start_id, max_depth=1)
                if inbounds:
                    called_symbols.add(sym.name)
            
            prioritized_symbols = [s for s in symbols if s.name in called_symbols and s.name not in [a.name for a in artifacts] and s.name not in runtime_symbols]
            if not prioritized_symbols and not artifacts and not runtime_symbols:
                prioritized_symbols = symbols[:3] # Fallback to first few

            for sym in prioritized_symbols:
                sym_slice = self.slicer.extract_symbol(rel_path, sym, reason + " [Called]")
                if sym_slice:
                    extracted.slices.append(sym_slice)

        return extracted
