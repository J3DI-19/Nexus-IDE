from typing import List, Optional
from ..extraction.models import ExtractionContext, ExtractedFile, CodeSlice
from ..retrieval.models import RetrievalQuery
from ..impact.models import ImpactResult
from ..runtime.models import RuntimeArtifact
from .models import PromptContext, PromptSection, PromptWarning, PromptMode

class AdvancedPromptBuilder:
    def __init__(self):
        pass

    def build_prompt(
        self, 
        query: RetrievalQuery, 
        context: ExtractionContext, 
        impact: Optional[ImpactResult] = None,
        mode: PromptMode = PromptMode.FEATURE,
        runtime_artifacts: Optional[List[RuntimeArtifact]] = None
    ) -> str:
        """
        Compiles an elite engineering briefing based on the mode and context.
        """
        prompt_ctx = PromptContext(mode=mode, task=query.task)
        
        # 1. System Rules (Always Order 0)
        prompt_ctx.sections.append(PromptSection(
            title="System Rules",
            content=self._build_rules(mode),
            order=0
        ))
        
        # 2. Runtime Diagnostics (Order 5)
        if runtime_artifacts:
            diag_content = []
            for art in runtime_artifacts:
                diag_content.append(f"FAILURE TYPE: {art.artifact_type.upper()}")
                diag_content.append(f"MESSAGE: {art.message}")
                if art.frames:
                    diag_content.append("STACK TRACE:")
                    for frame in art.frames[:5]: # Limit frames
                        diag_content.append(f"  - {frame.file_path}:{frame.line_number} in {frame.symbol_name or '?'}")
            
            prompt_ctx.sections.append(PromptSection(
                title="Runtime Diagnostics",
                content="\n".join(diag_content),
                order=5
            ))

        # 3. Extract Warnings from Impact Analysis
        if impact and impact.candidates:
            for cand in impact.candidates:
                if cand.impact_score > 30.0:
                    severity = "HIGH" if cand.impact_score > 60 else "MEDIUM"
                    artifacts = ", ".join([a.artifact_type for a in cand.affected_artifacts])
                    msg = f"Downstream impact detected on {artifacts or cand.file_metadata.classification}."
                    if cand.affected_symbols:
                        msg += f" Specifically affects: {', '.join(cand.affected_symbols)}."
                        
                    prompt_ctx.warnings.append(PromptWarning(
                        severity=severity,
                        affected_path=cand.file_metadata.rel_path,
                        message=msg
                    ))

        # 3. Active File Context (Order 10)
        if context.active_file:
            prompt_ctx.sections.append(PromptSection(
                title="Active Execution Context",
                content=self._build_file_section(context.active_file, is_active=True),
                order=10
            ))

        # 4. Related Context / Execution Chains (Order 20)
        if context.related_files:
            related_content = []
            for rel_file in context.related_files:
                related_content.append(self._build_file_section(rel_file))
            
            prompt_ctx.sections.append(PromptSection(
                title="Architectural Dependencies",
                content="\n\n".join(related_content),
                order=20
            ))
            
        return prompt_ctx.render()

    def _build_rules(self, mode: PromptMode) -> str:
        base_rules = (
            "You are a deterministic code modification engine.\n"
            "STRICT RULES:\n"
            "* Output ONLY a valid unified diff patch.\n"
            "* Do NOT include conversational text, greetings, or markdown outside the diff.\n"
            "* Preserve exact existing styles, imports, and framework conventions.\n"
        )
        
        if mode == PromptMode.REFACTOR:
            base_rules += "* Focus strictly on structural improvements without changing business logic.\n"
        elif mode == PromptMode.BUGFIX:
            base_rules += "* Prioritize minimal, targeted surgical changes to resolve the issue.\n"
            
        return base_rules

    def _build_file_section(self, file: ExtractedFile, is_active: bool = False) -> str:
        lines = [f"File: `{file.rel_path}`"]
        lines.append(f"Role: {file.classification.upper()}")
        lines.append(f"Retrieval Reason: {file.reason}")
        
        if file.artifacts:
            artifact_strs = [f"{a.artifact_type}({a.name})" for a in file.artifacts]
            lines.append(f"Architecture: {', '.join(artifact_strs)}")

        if file.slices:
            for s in file.slices:
                lines.append(f"\n[Code Slice: {s.reason} | Lines {s.start_line}-{s.end_line}]")
                lines.append("```")
                lines.append(s.content)
                lines.append("```")
        
        return "\n".join(lines)
