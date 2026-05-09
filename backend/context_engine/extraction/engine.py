from pathlib import Path
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

    def extract_context(self, active_file: Optional[str], candidates: List[ContextCandidate], mode: str = "feature", runtime: Optional[RuntimeAnalyzer] = None, full_file_overrides: Optional[List[str]] = None) -> ExtractionContext:
        """
        Orchestrates extraction for the active file and retrieved candidates.
        Uses semantic slicing by default.
        """
        context = ExtractionContext()
        overrides = set(full_file_overrides or [])

        # 1. Process Active File
        if active_file:
            is_override = active_file in overrides
            context.active_file = self._extract_single_file(
                active_file, 
                "Active File", 
                mode=mode, 
                max_full_lines=2000 if is_override else 300, 
                runtime=runtime,
                is_full_override=is_override
            )

        # 2. Process Candidates
        for cand in candidates:
            if active_file and cand.file_metadata.rel_path == active_file:
                continue
            
            is_override = cand.file_metadata.rel_path in overrides
            extracted = self._extract_single_file(
                cand.file_metadata.rel_path, 
                reason=f"Retrieved: {cand.score} pts",
                matched_symbols=cand.matched_symbols,
                mode=mode,
                max_full_lines=1000 if is_override else 100, 
                runtime=runtime,
                is_full_override=is_override
            )
            if extracted:
                context.related_files.append(extracted)

        return context

    def _extract_single_file(self, rel_path: str, reason: str, matched_symbols: List[str] = None, mode: str = "feature", max_full_lines: int = 100, runtime: Optional[RuntimeAnalyzer] = None, is_full_override: bool = False) -> Optional[ExtractedFile]:
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

        # If it's a full override, extract the whole file as a single slice immediately
        if is_full_override:
            full_slice = self.slicer.extract_full_file(rel_path, "Full File Override", max_lines=2000)
            if full_slice:
                full_slice.expansion_type = "full"
                extracted.slices.append(full_slice)
                return extracted

        # 1. Identify Anchors
        anchor_set = set(matched_symbols or [])
        runtime_symbols: Set[str] = set()
        if runtime:
            for art in runtime.get_active_artifacts():
                for frame in art.frames:
                    if rel_path in frame.file_path and frame.symbol_name:
                        runtime_symbols.add(frame.symbol_name)
        
        anchor_set.update(runtime_symbols)

        # Check file size
        abs_path = Path(self.root_path) / rel_path
        line_count = 0
        if abs_path.is_file():
            try:
                with open(abs_path, 'r', encoding='utf-8', errors='ignore') as f:
                    line_count = sum(1 for _ in f)
            except Exception: pass

        if line_count <= max_full_lines:
            full_slice = self.slicer.extract_full_file(rel_path, reason)
            if full_slice: extracted.slices.append(full_slice)
            return extracted

        # 2. Extract Artifacts (Always high priority)
        for art in artifacts:
            art_slice = self.slicer.extract_lines(rel_path, art.start_line, art.end_line, f"Framework Artifact: {art.artifact_type}")
            if art_slice:
                art_slice.expansion_type = "exact"
                extracted.slices.append(art_slice)

        # 3. Extract Anchors with Expansion
        for sym_name in anchor_set:
            sym = next((s for s in symbols if s.name == sym_name), None)
            if not sym: continue
            
            # Exact Match
            sym_slice = self.slicer.extract_symbol(rel_path, sym, f"Anchor: {sym_name}")
            if sym_slice:
                sym_slice.anchor_symbol = sym_name
                sym_slice.expansion_type = "exact"
                extracted.slices.append(sym_slice)

            # MODE-SPECIFIC SEMANTIC EXPANSION
            if mode == "refactor":
                # Refactor Mode: Expand to ALL callers/callees in the same file
                start_id = f"{rel_path}:{sym_name}"
                # Inbound (Callers)
                inbounds = self.traversal.traverse_inbound(start_id, max_depth=1)
                for path_result in inbounds:
                    caller_id = path_result.target_id
                    if caller_id.startswith(rel_path + ":"):
                        c_name = caller_id.split(':')[1]
                        c_sym = next((s for s in symbols if s.name == c_name), None)
                        if c_sym:
                            c_slice = self.slicer.extract_symbol(rel_path, c_sym, f"Caller of {sym_name}")
                            if c_slice:
                                c_slice.anchor_symbol = sym_name
                                c_slice.expansion_type = "dependency"
                                extracted.slices.append(c_slice)
            
            elif mode == "bugfix":
                # Bugfix Mode: Tight proximity (nearby lines/comments)
                # Slicer.extract_symbol already includes some padding
                pass 
                
            elif mode == "feature":
                # Feature Mode: Expand to related Types/Interfaces
                for other_sym in symbols:
                    if other_sym.type in {"class", "interface"} and other_sym.name != sym_name:
                        dist = min(abs(other_sym.start_line - sym.end_line), abs(sym.start_line - other_sym.end_line))
                        if dist < 30:
                            p_slice = self.slicer.extract_symbol(rel_path, other_sym, f"Context for {sym_name}")
                            if p_slice:
                                p_slice.anchor_symbol = sym_name
                                p_slice.expansion_type = "proximity"
                                extracted.slices.append(p_slice)
                            
        return extracted
