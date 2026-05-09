import os
from typing import List, Optional, Dict, Any
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
        runtime_artifacts: Optional[List[RuntimeArtifact]] = None
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
            
            return template.render(
                mode=mode.value,
                task=query.task,
                warnings=warnings,
                runtime_diagnostics=runtime_content,
                active_file=active_file_content,
                related_context="\n\n".join(related_sections),
                rules=self._build_rules(mode)
            )
        except Exception as e:
            print(f"PROMPT RENDERING ERROR: {e}")
            # Fallback to a very basic render if Jinja fails
            return f"ERROR RENDERING PROMPT: {e}\nTask: {query.task}"

    def _build_rules(self, mode: PromptMode) -> str:
        base_rules = [
            "You are a deterministic code modification engine.",
            "STRICT RULES:",
            "* Output ONLY a valid unified diff patch.",
            "* Do NOT include conversational text or markdown outside the diff.",
            "* Preserve exact existing styles, imports, and framework conventions."
        ]
        
        if mode == PromptMode.REFACTOR:
            base_rules.append("* Focus strictly on structural improvements without changing business logic.")
        elif mode == PromptMode.BUGFIX:
            base_rules.append("* Prioritize minimal, targeted surgical changes to resolve the issue.")
            
        return "\n".join(base_rules)

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
