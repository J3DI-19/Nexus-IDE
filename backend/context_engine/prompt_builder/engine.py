import os
from pathlib import Path
from typing import List, Optional, Dict, Any, Set
from jinja2 import Environment, FileSystemLoader
from ..extraction.models import ExtractionContext, ExtractedFile, CodeSlice
from ..retrieval.models import RetrievalQuery
from ..impact.models import ImpactResult
from ..runtime.models import RuntimeArtifact
from .models import PromptContext, PromptSection, PromptWarning, PromptMode

class TokenBalancer:
    """
    Heuristic-based token budget manager. 
    1 token ~= 4 characters for English code.
    """
    def __init__(self, budget: int = 6000):
        self.budget = budget
        self.used = 0

    def has_budget(self, text: str) -> bool:
        return self.used + (len(text) // 4) < self.budget

    def add(self, text: str):
        self.used += (len(text) // 4)

class AdvancedPromptBuilder:
    def __init__(self):
        template_dir = os.path.join(os.path.dirname(__file__), "../../../templates")
        self.env = Environment(loader=FileSystemLoader(template_dir))

    def build_prompt(
        self, 
        query: RetrievalQuery, 
        context: ExtractionContext, 
        impact: Optional[ImpactResult] = None,
        mode: PromptMode = PromptMode.FEATURE,
        runtime_artifacts: Optional[List[RuntimeArtifact]] = None,
        preset_name: Optional[str] = None,
        preset_template: Optional[str] = None,
        selection_reasons: Optional[List[str]] = None,
        executor_response_format: str = "unified_diff",
    ) -> str:
        """
        Orchestrates prompt composition using Jinja2 and adaptive token balancing.
        """
        balancer = TokenBalancer(budget=8000)
        
        # 1. Build Warnings (High priority, always included)
        warnings = []
        if impact and impact.candidates:
            for cand in impact.candidates:
                if cand.impact_score > 30.0:
                    severity = "HIGH" if cand.impact_score > 60 else "MEDIUM"
                    artifacts = ", ".join([a.artifact_type for a in cand.affected_artifacts])
                    msg = f"Downstream impact detected on {artifacts or cand.file_metadata.classification}."
                    if cand.affected_symbols:
                        msg += f" Specifically affects: {', '.join(cand.affected_symbols)}."
                    
                    w = PromptWarning(severity=severity, affected_path=cand.file_metadata.rel_path, message=msg)
                    warnings.append(w)
                    balancer.add(w.message)

        # 2. Build Runtime Diagnostics (High priority)
        runtime_content = ""
        if runtime_artifacts:
            diag_lines = []
            for art in runtime_artifacts:
                diag_lines.append(f"FAILURE: {art.artifact_type.upper()} - {art.message}")
                if art.frames:
                    for frame in art.frames[:3]:
                        diag_lines.append(f"  at {frame.file_path}:{frame.line_number} ({frame.symbol_name or '?'})")
            runtime_content = "\n".join(diag_lines)
            balancer.add(runtime_content)

        # 3. Build Active File (Highest priority code)
        active_file_content = ""
        if context.active_file:
            active_file_content = self._build_file_section(context.active_file, balancer, is_active=True)

        # 4. Build Related Context (Adaptive trimming)
        related_sections = []
        if context.related_files:
            # Sort related files by reason/score (implicitly sorted by retrieval)
            for rel_file in context.related_files:
                if balancer.used > balancer.budget * 0.9:
                    break # Stop if we are near the limit
                
                file_section = self._build_file_section(rel_file, balancer)
                if file_section:
                    related_sections.append(file_section)

        # 5. Render via Jinja2
        try:
            # Try to find mode-specific template, fallback to PromptTemplateV1.jinja
            template_name = f"{mode.value}.jinja" 
            if not os.path.exists(os.path.join(self.env.loader.searchpath[0], template_name)):
                template_name = "PromptTemplateV1.jinja"
                
            template = self.env.get_template(template_name)
            active_file_path = context.active_file.rel_path if context.active_file else query.active_file
            hierarchy_block = self._build_project_hierarchy_compact(
                active_file=active_file_path,
                related_files=[f.rel_path for f in context.related_files]
            )
            selection_reason_lines = selection_reasons or self._build_top_selection_reasons(context.related_files)
            
            base_prompt = template.render(
                mode=mode.value,
                task=query.task,
                warnings=warnings,
                runtime_diagnostics=runtime_content,
                active_file=active_file_content,
                related_context="\n\n".join(related_sections),
                rules=self._build_rules(mode, executor_response_format),
                response_contract=self._response_contract(mode, executor_response_format),
                active_file_path=active_file_path,
                project_hierarchy_compact=hierarchy_block,
                top_selection_reasons=selection_reason_lines,
            )
            preset_block = self._render_preset_block(
                preset_name=preset_name,
                preset_template=preset_template,
                query=query,
                mode=mode,
                context=context
            )
            return f"{preset_block}\n\n{base_prompt}" if preset_block else base_prompt
        except Exception as e:
            print(f"PROMPT RENDERING ERROR: {e}")
            # Fallback to a very basic render if Jinja fails
            return f"ERROR RENDERING PROMPT: {e}\nTask: {query.task}"

    def _render_preset_block(
        self,
        preset_name: Optional[str],
        preset_template: Optional[str],
        query: RetrievalQuery,
        mode: PromptMode,
        context: ExtractionContext
    ) -> str:
        template_text = (preset_template or "").strip()
        if not template_text:
            return ""
        active_file_path = context.active_file.rel_path if context.active_file else query.active_file
        try:
            rendered = Environment().from_string(template_text).render(
                goal=query.task,
                task=query.task,
                mode=mode.value,
                active_file=active_file_path
            ).strip()
        except Exception:
            rendered = template_text
        if not rendered:
            return ""
        if preset_name:
            return f"[Prompt Preset: {preset_name}]\n{rendered}"
        return rendered

    def _build_rules(self, mode: PromptMode, executor_response_format: str = "unified_diff") -> str:
        if mode == PromptMode.ARCHITECTURE:
            return "\n".join([
                "You are a deterministic engineering analysis assistant.",
                "STRICT RULES:",
                "* Output a concise, structured architecture/engineering briefing.",
                "* Do NOT output a unified diff patch for this task type.",
                "* Preserve exact existing styles, imports, and framework conventions in any referenced code.",
            ])

        if executor_response_format == "nexus_edits_v2":
            base_rules = [
                "You are a deterministic code modification engine.",
                "STRICT RULES:",
                "* FORMAT CONTRACT:",
                "* Output ONLY valid JSON (no markdown fences, no prose).",
                "* Response format MUST be exactly: {\"format\":\"nexus_edits_v2\",\"edits\":[...]}",
                "* Each edit MUST be a flat object with keys: path, op, and operation-specific fields.",
                "* Allowed op values: replace_range, insert_after, insert_before, create_file, delete_file.",
                "* Use `path` (NOT `file`) and a flat `edits` list (NO nested `ops`).",
                "* For replace_range: include old_text and new_text.",
                "* For insert_after/insert_before: include anchor_text and new_text.",
                "* For create_file: include new_text.",
                "* For delete_file: include only path + op.",
                "* Escape all JSON strings correctly (quotes as \\\" and newlines as \\n).",
                "* INTENT CONTRACT:",
                "* Enforce exact operator/token semantics from the task; do not substitute near-equivalent symbols.",
                "* Example: when adding squaring in calculator flows, use literal `^2` in menu text and branch condition.",
                "* EDIT STRATEGY CONTRACT:",
                "* Keep edits minimal and surgical; avoid unrelated rewrites.",
                "* For high-risk transformations (rename/API/import/config), preserve exact surrounding context in anchors/old_text.",
                "* Preserve exact existing styles, imports, and framework conventions.",
                "* If context is uncertain, return empty edits instead of speculative edits.",
                "* If required context is missing or uncertain, return: {\"format\":\"nexus_edits_v2\",\"edits\":[]}.",
            ]
        else:
            base_rules = [
                "You are a deterministic code modification engine.",
                "STRICT RULES:",
                "* FORMAT CONTRACT:",
                "* Output ONLY a valid unified diff patch.",
                "* Do NOT include conversational text or markdown outside the diff.",
                "* INTENT CONTRACT:",
                "* Enforce exact operator/token semantics from the task; do not substitute near-equivalent symbols.",
                "* Example: when adding squaring in calculator flows, use literal `^2` in menu text and branch condition.",
                "* EDIT STRATEGY CONTRACT:",
                "* Keep edits minimal and surgical; avoid unrelated rewrites.",
                "* For high-risk transformations (rename/API/import/config), preserve exact surrounding context.",
                "* Preserve exact existing styles, imports, and framework conventions.",
                "* Patch format MUST include standard unified diff markers ('---', '+++', '@@').",
                "* If context is uncertain, output an empty diff instead of speculative edits.",
                "* If a safe patch cannot be produced from provided context, output an empty diff."
            ]
        
        if mode == PromptMode.REFACTOR:
            base_rules.append("* Focus strictly on structural improvements without changing business logic.")
        elif mode == PromptMode.BUGFIX:
            base_rules.append("* Prioritize minimal, targeted surgical changes to resolve the issue.")
            
        return "\n".join(base_rules)

    def _response_contract(self, mode: PromptMode, executor_response_format: str = "unified_diff") -> str:
        if mode == PromptMode.ARCHITECTURE:
            return "Respond with a concise structured analysis/briefing (not a patch)."
        if executor_response_format == "nexus_edits_v2":
            return "Your response must be ONLY valid JSON in nexus_edits_v2 format."
        return "Your response must be ONLY a valid unified diff patch."

    def _build_file_section(self, file: ExtractedFile, balancer: TokenBalancer, is_active: bool = False) -> str:
        header = f"File: `{file.rel_path}` ({file.classification.upper()})"
        if not balancer.has_budget(header):
            return ""
        
        lines = [header]
        balancer.add(header)
        
        if file.artifacts:
            art_str = f"Architecture: " + ", ".join([f"{a.artifact_type}({a.name})" for a in file.artifacts])
            lines.append(art_str)
            balancer.add(art_str)

        # Add slices with budget check
        # Prioritize slices: exact > dependency > runtime > proximity
        priority_map = {"exact": 0, "dependency": 1, "runtime": 2, "proximity": 3}
        sorted_slices = sorted(file.slices, key=lambda s: priority_map.get(s.expansion_type, 99))

        for s in sorted_slices:
            slice_header = f"\n[Code Slice: {s.reason}]"
            slice_content = f"```\n{s.content}\n```"
            
            if balancer.has_budget(slice_header + slice_content):
                lines.append(slice_header)
                lines.append(slice_content)
                balancer.add(slice_header + slice_content)
            elif is_active:
                # For active file, try to at least include a truncated version
                truncated = s.content[:500] + "\n... (truncated for budget)"
                lines.append(slice_header)
                lines.append(f"```\n{truncated}\n```")
                balancer.add(slice_header + truncated)
            else:
                # For related files, skip the slice if no budget
                lines.append(f"\n[Code Slice: {s.reason} | OMITTED DUE TO TOKEN BUDGET]")
        
        return "\n".join(lines)

    def _build_top_selection_reasons(self, related_files: List[ExtractedFile], limit: int = 8) -> List[str]:
        reasons: List[str] = []
        for rel_file in related_files[:limit]:
            reason_text = rel_file.reason or ""
            reasons.append(f"{rel_file.rel_path}: {reason_text}")
        return reasons

    def _build_project_hierarchy_compact(self, active_file: Optional[str], related_files: List[str], max_lines: int = 40) -> str:
        paths: Set[str] = set()
        if active_file:
            paths.add(active_file)
        paths.update(related_files or [])
        if not paths:
            return ""

        root = Path(self.env.loader.searchpath[0]).resolve().parent
        tree: Dict[str, Any] = {}
        for rel in sorted(paths):
            normalized = rel.replace("\\", "/").strip("/")
            if not normalized:
                continue
            parts = normalized.split("/")[:3]
            node = tree
            for part in parts:
                node = node.setdefault(part, {})

        lines: List[str] = [str(root.name)]

        def walk(node: Dict[str, Any], prefix: str = ""):
            for idx, key in enumerate(sorted(node.keys())):
                is_last = idx == len(node) - 1
                connector = "└── " if is_last else "├── "
                lines.append(f"{prefix}{connector}{key}")
                if len(lines) >= max_lines:
                    return
                next_prefix = f"{prefix}{'    ' if is_last else '│   '}"
                walk(node[key], next_prefix)
                if len(lines) >= max_lines:
                    return

        walk(tree)
        if len(lines) >= max_lines:
            lines.append("... (truncated)")

        markers = []
        if active_file:
            markers.append(f"* active: {active_file}")
        markers.extend([f"* related: {path}" for path in related_files[:6]])
        return "\n".join(lines + [""] + markers)
