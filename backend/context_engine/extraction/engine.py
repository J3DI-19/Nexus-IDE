from typing import Dict, List, Optional, Set
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
            active_metadata = self.index.get_file_metadata(active_file)
            active_symbols = self.index.get_symbols_for_file(active_file) if active_metadata else []
            context.active_file = self._extract_single_file(
                active_file, 
                "Active File", 
                matched_symbols=self._select_active_anchors(active_symbols, mode),
                mode=mode, 
                runtime=runtime,
                is_full_override=is_override,
                candidate_rank=0,
                confidence_score=999.0
            )

        # 2. Process Candidates
        for idx, cand in enumerate(candidates, start=1):
            if active_file and cand.file_metadata.rel_path == active_file:
                continue
            
            is_override = cand.file_metadata.rel_path in overrides
            extracted = self._extract_single_file(
                cand.file_metadata.rel_path, 
                reason=f"Retrieved: {cand.score:.1f} pts",
                matched_symbols=cand.matched_symbols,
                mode=mode,
                runtime=runtime,
                is_full_override=is_override,
                candidate_rank=idx,
                confidence_score=cand.score
            )
            if extracted:
                context.related_files.append(extracted)

        return context

    def _select_active_anchors(self, symbols: List, mode: str) -> List[str]:
        if not symbols:
            return []
        action_hints = {
            "feature": {"create", "add", "update", "process", "calculate", "save"},
            "refactor": {"validate", "check", "parse", "extract", "normalize"},
            "bugfix": {"login", "validate", "verify", "auth", "check", "fix"},
            "architecture": {"doc", "render", "generate", "summary"},
        }.get(mode, set())

        preferred = []
        if mode == "bugfix":
            method_first = []
            class_fallback = []
            for sym in symbols:
                name = sym.name.lower()
                if any(hint in name for hint in action_hints):
                    if sym.type in {"function", "method"}:
                        method_first.append(sym.name)
                    elif sym.type == "class":
                        class_fallback.append(sym.name)
            if method_first:
                return method_first[:2]
            if class_fallback:
                return class_fallback[:1]

        for sym in symbols:
            name = sym.name.lower()
            if any(hint in name for hint in action_hints):
                preferred.append(sym.name)
            if len(preferred) >= 2:
                break
        if preferred:
            return preferred

        return [sym.name for sym in symbols[:2]]

    def _augment_bugfix_anchors(self, symbols: List, anchor_set: Set[str]) -> Set[str]:
        if len(anchor_set) >= 2:
            return anchor_set
        bugfix_terms = {"login", "validate", "verify", "auth", "check", "credential", "token", "password"}
        for sym in symbols:
            s_name = sym.name.lower()
            if any(term in s_name for term in bugfix_terms):
                anchor_set.add(sym.name)
            if len(anchor_set) >= 2:
                break
        return anchor_set

    def _slice_span(self, code_slice: CodeSlice) -> int:
        return max(1, code_slice.end_line - code_slice.start_line + 1)

    def _merge_intervals(self, intervals: List[tuple[int, int]]) -> List[tuple[int, int]]:
        if not intervals:
            return []
        ordered = sorted(intervals, key=lambda pair: pair[0])
        merged = [ordered[0]]
        for start, end in ordered[1:]:
            prev_start, prev_end = merged[-1]
            if start <= prev_end + 1:
                merged[-1] = (prev_start, max(prev_end, end))
            else:
                merged.append((start, end))
        return merged

    def _file_line_count(self, rel_path: str) -> int:
        abs_path = self.slicer.root_path / rel_path
        if not abs_path.is_file():
            return 0
        try:
            with open(abs_path, "r", encoding="utf-8", errors="ignore") as handle:
                return sum(1 for _ in handle)
        except Exception:
            return 0

    def _clip_slice(self, code_slice: CodeSlice, max_span: int) -> CodeSlice:
        span = self._slice_span(code_slice)
        if span <= max_span:
            return code_slice
        clipped_end = code_slice.start_line + max_span - 1
        clipped_lines = code_slice.content.splitlines()[:max_span]
        code_slice.end_line = clipped_end
        code_slice.content = "\n".join(clipped_lines) + "\n... (clipped slice span)"
        return code_slice

    def _append_slice_unique(self, extracted: ExtractedFile, candidate_slice: Optional[CodeSlice], max_span: int) -> None:
        if not candidate_slice:
            return
        candidate_slice = self._clip_slice(candidate_slice, max_span=max_span)
        c_start, c_end = candidate_slice.start_line, candidate_slice.end_line
        for existing in extracted.slices:
            if existing.start_line == candidate_slice.start_line and existing.end_line == candidate_slice.end_line and existing.reason == candidate_slice.reason:
                return
            inter = max(0, min(existing.end_line, c_end) - max(existing.start_line, c_start) + 1)
            if inter <= 0:
                continue
            union = max(existing.end_line, c_end) - min(existing.start_line, c_start) + 1
            overlap_ratio = inter / union if union else 0.0
            # Suppress heavily overlapping slices of the same expansion type.
            if overlap_ratio >= 0.75 and existing.expansion_type == candidate_slice.expansion_type:
                return
        extracted.slices.append(candidate_slice)

    def _extract_anchor_window(self, rel_path: str, start_line: int, end_line: int, reason: str, max_span: int = 20) -> Optional[CodeSlice]:
        if end_line < start_line:
            end_line = start_line
        span = max(1, end_line - start_line + 1)
        if span >= max_span:
            center = start_line
            w_start = max(1, center - 2)
            w_end = w_start + max_span - 1
            return self.slicer.extract_lines(rel_path, w_start, w_end, reason)
        padded_start = max(1, start_line - 1)
        padded_end = padded_start + max_span - 1
        return self.slicer.extract_lines(rel_path, padded_start, max(padded_end, end_line), reason)

    def _compact_slices(self, extracted: ExtractedFile, max_slices: int) -> None:
        if len(extracted.slices) <= max_slices:
            return
        priority = {"exact": 0, "dependency": 1, "proximity": 2, "fallback": 3}
        extracted.slices.sort(key=lambda s: (priority.get(s.expansion_type, 9), self._slice_span(s)))
        extracted.slices = extracted.slices[:max_slices]

    def _build_slice_policy(
        self,
        mode: str,
        reason: str,
        confidence_score: float,
        candidate_rank: int,
        anchor_count: int
    ) -> Dict[str, float]:
        is_active = reason == "Active File"
        if mode == "refactor":
            base = {"slice_span": 18, "max_slices": 4 if is_active else 3, "soft_budget": 58 if is_active else 46, "hard_budget": 98 if is_active else 76, "coverage_guard": 0.62 if is_active else 0.56}
        elif mode == "bugfix":
            base = {"slice_span": 16, "max_slices": 4 if is_active else 3, "soft_budget": 50 if is_active else 38, "hard_budget": 86 if is_active else 66, "coverage_guard": 0.56 if is_active else 0.50}
        elif mode == "architecture":
            base = {"slice_span": 12, "max_slices": 3 if is_active else 1, "soft_budget": 34 if is_active else 16, "hard_budget": 62 if is_active else 34, "coverage_guard": 0.48 if is_active else 0.40}
        else:
            base = {"slice_span": 16, "max_slices": 4 if is_active else 3, "soft_budget": 50 if is_active else 38, "hard_budget": 86 if is_active else 66, "coverage_guard": 0.58 if is_active else 0.52}

        # Adaptive expansion for high-signal contexts to avoid under-contexting large bases.
        if confidence_score >= 100 or candidate_rank <= 2:
            base["soft_budget"] += 10
            base["hard_budget"] += 14
        if anchor_count >= 3:
            base["soft_budget"] += 8
            base["hard_budget"] += 10
            base["max_slices"] += 1
        if mode == "refactor":
            base["soft_budget"] += 6
            base["hard_budget"] += 8

        return base

    def _apply_line_budget(
        self,
        extracted: ExtractedFile,
        max_slices: int,
        soft_budget: int,
        hard_budget: int,
        total_lines: int,
        coverage_guard: float,
    ) -> None:
        if not extracted.slices:
            return
        priority = {"exact": 0, "dependency": 1, "proximity": 2, "fallback": 3}
        # Keep higher-priority and shorter slices first for dense, precise context.
        extracted.slices.sort(key=lambda s: (priority.get(s.expansion_type, 9), self._slice_span(s)))

        kept: List[CodeSlice] = []
        used = 0
        covered: List[tuple[int, int]] = []
        guard_lines = int(max(1, total_lines * coverage_guard)) if total_lines > 0 else 0
        for code_slice in extracted.slices:
            span = self._slice_span(code_slice)
            next_used = used + span
            critical = code_slice.expansion_type in {"exact", "dependency"}
            next_cov = covered + [(code_slice.start_line, code_slice.end_line)]
            next_cov_lines = sum(max(0, e - s + 1) for s, e in self._merge_intervals(next_cov)) if total_lines > 0 else 0
            if guard_lines and next_cov_lines > guard_lines:
                # Keep at least one strong anchor even if it exceeds the guard,
                # but avoid stacking additional slices that over-expand coverage.
                if kept:
                    continue
                if not critical:
                    continue
            if next_used <= soft_budget:
                kept.append(code_slice)
                used = next_used
                covered = next_cov
                continue
            if critical and next_used <= hard_budget:
                kept.append(code_slice)
                used = next_used
                covered = next_cov
                continue

        if not kept:
            kept = extracted.slices[:1]

        extracted.slices = kept[:max_slices]

    def _extract_single_file(
        self,
        rel_path: str,
        reason: str,
        matched_symbols: List[str] = None,
        mode: str = "feature",
        runtime: Optional[RuntimeAnalyzer] = None,
        is_full_override: bool = False,
        candidate_rank: int = 10,
        confidence_score: float = 0.0,
    ) -> Optional[ExtractedFile]:
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
        if mode == "bugfix":
            anchor_set = self._augment_bugfix_anchors(symbols, anchor_set)
        total_lines = self._file_line_count(rel_path)
        policy = self._build_slice_policy(
            mode=mode,
            reason=reason,
            confidence_score=confidence_score,
            candidate_rank=candidate_rank,
            anchor_count=len(anchor_set),
        )
        base_span = policy["slice_span"]

        # 2. Extract import region for orientation without dumping full files.
        import_slice = self.slicer.extract_imports(rel_path)
        if import_slice:
            include_imports = (reason == "Active File") or ((mode != "architecture") and (not anchor_set and not artifacts))
            if include_imports:
                import_slice.expansion_type = "dependency"
                self._append_slice_unique(extracted, import_slice, max_span=max(4, base_span // 3))

        # 3. Extract Artifacts (Always high priority)
        for art in artifacts:
            art_slice = self.slicer.extract_lines(rel_path, art.start_line, art.end_line, f"Framework Artifact: {art.artifact_type}")
            if art_slice:
                art_slice.expansion_type = "exact"
                self._append_slice_unique(extracted, art_slice, max_span=base_span + 6)

        # 4. Extract Anchors with Expansion
        bugfix_dependency_added = 0
        ordered_anchor_names = sorted(anchor_set, key=lambda n: 0 if next((s for s in symbols if s.name == n and s.type in {"function", "method"}), None) else 1)
        for sym_name in ordered_anchor_names:
            sym = next((s for s in symbols if s.name == sym_name), None)
            if not sym: continue
            
            # Exact Match
            sym_slice = self._extract_anchor_window(rel_path, sym.start_line, sym.end_line, f"Anchor: {sym_name}", max_span=base_span)
            if sym_slice:
                sym_slice.anchor_symbol = sym_name
                sym_slice.expansion_type = "exact"
                self._append_slice_unique(extracted, sym_slice, max_span=base_span)

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
                            c_slice = self._extract_anchor_window(rel_path, c_sym.start_line, c_sym.end_line, f"Caller of {sym_name}", max_span=max(12, base_span - 2))
                            if c_slice:
                                c_slice.anchor_symbol = sym_name
                                c_slice.expansion_type = "dependency"
                                self._append_slice_unique(extracted, c_slice, max_span=max(12, base_span - 2))
            
            elif mode == "bugfix":
                # Bugfix Mode: include one immediate inbound/outbound symbol dependency when anchors are sparse.
                if len(anchor_set) <= 2 and bugfix_dependency_added < 1:
                    start_id = f"{rel_path}:{sym_name}"
                    dep_paths = []
                    dep_paths.extend(self.traversal.traverse_inbound(start_id, max_depth=1))
                    dep_paths.extend(self.traversal.traverse_outbound(start_id, max_depth=1, allowed_types={"call", "async_call"}))
                    for dep in dep_paths[:1]:
                        dep_id = dep.target_id
                        if dep_id.startswith(rel_path + ":"):
                            dep_name = dep_id.split(":", 1)[1]
                            dep_sym = next((s for s in symbols if s.name == dep_name), None)
                            if dep_sym:
                                dep_slice = self._extract_anchor_window(
                                    rel_path, dep_sym.start_line, dep_sym.end_line, f"Dependency of {sym_name}", max_span=max(10, base_span - 4)
                                )
                                if dep_slice:
                                    dep_slice.anchor_symbol = sym_name
                                    dep_slice.expansion_type = "dependency"
                                    self._append_slice_unique(extracted, dep_slice, max_span=max(10, base_span - 4))
                                    bugfix_dependency_added += 1
                                    break
                
            elif mode == "feature":
                # Feature Mode: Expand to related Types/Interfaces
                for other_sym in symbols:
                    if other_sym.type in {"class", "interface"} and other_sym.name != sym_name:
                        dist = min(abs(other_sym.start_line - sym.end_line), abs(sym.start_line - other_sym.end_line))
                        if dist < 30:
                            p_slice = self._extract_anchor_window(rel_path, other_sym.start_line, other_sym.end_line, f"Context for {sym_name}", max_span=max(10, base_span - 6))
                            if p_slice:
                                p_slice.anchor_symbol = sym_name
                                p_slice.expansion_type = "proximity"
                                self._append_slice_unique(extracted, p_slice, max_span=max(10, base_span - 6))

        # 5. Fallback: keep non-empty context via targeted snippets, not full dump.
        if not extracted.slices:
            if symbols and not anchor_set and not artifacts:
                for sym in symbols[:2]:
                    fallback_slice = self._extract_anchor_window(
                        rel_path, sym.start_line, sym.end_line, "Fallback Symbol Context", max_span=44
                    )
                    if fallback_slice:
                        fallback_slice.expansion_type = "fallback"
                        self._append_slice_unique(extracted, fallback_slice, max_span=max(12, base_span - 4))
            elif not symbols and not anchor_set and not artifacts:
                top_slice = self.slicer.extract_lines(rel_path, 1, max(10, base_span - 6), "Fallback File Header")
                if top_slice:
                    top_slice.expansion_type = "fallback"
                    self._append_slice_unique(extracted, top_slice, max_span=max(10, base_span - 6))

        # Keep extraction concise but adaptive; allow extra slices/lines for high-signal files.
        self._compact_slices(extracted, max_slices=policy["max_slices"])
        self._apply_line_budget(
            extracted,
            max_slices=policy["max_slices"],
            soft_budget=int(policy["soft_budget"]),
            hard_budget=int(policy["hard_budget"]),
            total_lines=total_lines,
            coverage_guard=float(policy["coverage_guard"]),
        )

        return extracted
