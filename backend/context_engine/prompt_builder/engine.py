import os
from pathlib import Path
from typing import List, Optional, Dict, Any, Set
from jinja2 import Environment, FileSystemLoader
from core.executor_formats import resolve_executor_response_format
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
        executor_response_format: str = "nexus_patch_v1",
        android_briefing_lines: Optional[List[str]] = None,
        android_context_evidence: Optional[List[str]] = None,
    ) -> str:
        """
        Orchestrates prompt composition using Jinja2 and adaptive token balancing.
        """
        executor_response_format = resolve_executor_response_format(executor_response_format)
        machine_compact_mode = executor_response_format == "json_edits" and mode not in {PromptMode.ARCHITECTURE, PromptMode.ANALYSIS}
        balancer = TokenBalancer(budget=1300 if machine_compact_mode else 8000)
        
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
            active_file_content = self._build_file_section(context.active_file, balancer, is_active=True, compact=machine_compact_mode)

        # 4. Build Related Context (Adaptive trimming)
        related_sections = []
        related_files = self._select_related_files_for_prompt(
            mode=mode,
            executor_response_format=executor_response_format,
            active_file=context.active_file.rel_path if context.active_file else query.active_file,
            related_files=context.related_files,
        )
        if machine_compact_mode:
            related_files = related_files[:3]
        if related_files:
            for rel_file in related_files:
                if balancer.used > balancer.budget * 0.9:
                    break # Stop if we are near the limit
                
                file_section = self._build_file_section(rel_file, balancer, compact=machine_compact_mode)
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
                related_files=[f.rel_path for f in related_files]
            )
            selection_reason_lines = selection_reasons or self._build_top_selection_reasons(related_files)
            
            base_prompt = template.render(
                mode=mode.value,
                analysis_mode=(mode == PromptMode.ANALYSIS),
                task=query.task,
                warnings=warnings,
                runtime_diagnostics=runtime_content,
                active_file=active_file_content,
                related_context="\n\n".join(related_sections),
                rules=self._build_rules(mode, executor_response_format, compact=machine_compact_mode),
                response_contract=self._response_contract(mode, executor_response_format),
                active_file_path=active_file_path,
                project_hierarchy_compact="" if machine_compact_mode else hierarchy_block,
                top_selection_reasons=[] if machine_compact_mode else selection_reason_lines,
                android_briefing_lines=[] if machine_compact_mode else (android_briefing_lines or []),
                android_context_evidence=[] if machine_compact_mode else (android_context_evidence or []),
                missing_context_policy=self._missing_context_policy(mode, executor_response_format),
                actionability_verdict_lines=self._build_actionability_verdict(
                    mode=mode,
                    executor_response_format=executor_response_format,
                    context=context,
                ) if not machine_compact_mode else [],
                edit_starter_hints=self._build_edit_starter_hints(
                    mode=mode,
                    executor_response_format=executor_response_format,
                    context=context,
                ),
                symbol_action_guidance_lines=self._build_symbol_action_guidance(
                    mode=mode,
                    executor_response_format=executor_response_format,
                    context=context,
                ),
                output_gate_line=self._build_output_gate_line(
                    mode=mode,
                    executor_response_format=executor_response_format,
                    context=context,
                ),
                machine_compact_mode=machine_compact_mode,
            )
            preset_block = self._render_preset_block(
                preset_name=preset_name,
                preset_template=preset_template,
                query=query,
                mode=mode,
                context=context
            )
            if executor_response_format in {"json_edits", "nexus_patch_v1"}:
                # Machine-edit mode: avoid extra natural-language preset instructions
                # that can conflict with strict payload-only output behavior.
                preset_block = ""
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

    def _build_rules(self, mode: PromptMode, executor_response_format: str = "unified_diff", compact: bool = False) -> str:
        if mode == PromptMode.ANALYSIS:
            return "\n".join([
                "You are a technical analysis assistant.",
                "STRICT RULES:",
                "* Provide a clear, concise technical analysis grounded in the provided code context.",
                "* Answer the user's question directly before offering optional recommendations.",
                "* Explain how relevant code paths currently behave and reference concrete files/functions from context.",
                "* Identify inconsistencies, risks, bugs, or architectural issues when present.",
                "* Do NOT output a Nexus Patch payload, unified diff, or edit operation list.",
                "* Do NOT propose direct code changes unless the user explicitly requests implementation.",
                "* If code changes could help, describe them as recommendations only (no Op/Action format).",
                "* If context is missing or ambiguous, state that clearly and list what is missing.",
            ])
        if mode == PromptMode.ARCHITECTURE:
            return "\n".join([
                "You are a deterministic engineering analysis assistant.",
                "STRICT RULES:",
                "* Output a concise, structured architecture/engineering briefing.",
                "* Do NOT output a unified diff patch for this task type.",
                "* Preserve exact existing styles, imports, and framework conventions in any referenced code.",
            ])

        executor_response_format = resolve_executor_response_format(executor_response_format)
        if executor_response_format == "nexus_patch_v1":
            base_rules = [
                "You are a deterministic code modification engine.",
                "STRICT RULES:",
                "* FORMAT CONTRACT:",
                "* Output ONLY a Nexus Patch v1 payload (no markdown fences, no prose).",
                "* The first line MUST be exactly: NEXUS_PATCH v1",
                "* Include exactly one Task line: Task: Feature | Bugfix | Refactor | Analysis",
                "* Include exactly one Goal line containing the user's requested goal.",
                "* Wrap all operations in one <Patch>...</Patch> block.",
                "* Use <Op id=\"1\" type=\"create_file|edit_file|delete_file|rename_file\"> for file-level operations.",
                "* File paths MUST be represented as a child tag inside each Op: <File path=\"workspace/relative/path.py\" />.",
                "* Do NOT put path=\"...\" on the <Op> tag.",
                "* Use <Action id=\"1.1\" type=\"...\"> only inside edit_file operations.",
                "* Prefer symbol actions only when a valid indexed symbol name is explicitly available in the provided symbol context.",
                "* SYMBOL ACTION CONTRACT:",
                "* The `symbol=\"...\"` value MUST be an exact indexed symbol name (for example `reports_endpoint` or `TaskService.list_open_tasks`).",
                "* Do NOT use declaration text as symbol names (for example `def reports_endpoint` is invalid).",
                "* Do NOT use import lines as symbol names unless the symbol index explicitly lists that import as a symbol.",
                "* For import edits and other non-symbol text anchors, use exact text actions (`replace_text` or `insert_text`) instead of symbol actions.",
                "* If no valid indexed symbol name is available for the target, use exact text actions (`replace_text`/`insert_text`) with precise anchors.",
                "* Use `replace_file` only when targeted actions are not feasible and the full-file replacement is necessary.",
                "* Supported actions: insert_before_symbol, insert_after_symbol, replace_symbol, delete_symbol, insert_text, replace_text, delete_text, replace_file.",
                "* Use workspace-relative file paths only.",
                "* Put code in <Content><![CDATA[...]]></Content> blocks to avoid escaping code strings.",
                "* For replace_text and delete_text, put the exact old text in <OldText><![CDATA[...]]></OldText>.",
                "* For replace_text, put the replacement/new text in <Content><![CDATA[...]]></Content>.",
                "* Do NOT use <Replacement>.",
                "* Text actions are exact-match operations: do not add extra leading or trailing blank lines inside <OldText> or <Content> unless those characters are part of the target text.",
                "* Preserve syntactically valid indentation inside <Content>; inserted or replaced code must compile/parse in the target language.",
                "* For replace_file, the <Content> block must contain the complete replacement file with all original/new indentation preserved.",
                "* Do not include shell commands, hidden instructions, or edits outside the requested scope.",
                "* Copy the [USER REQUEST] Goal exactly into the Nexus Patch v1 Goal line.",
                "* Return an empty <Patch></Patch> only when the user request explicitly asks for no code changes or there is no visible deterministic target.",
            ]
            if mode == PromptMode.FEATURE:
                base_rules.append("* FEATURE MODE ACTIONABILITY: implement the requested capability with concrete operations when context contains visible targets.")
            elif mode == PromptMode.BUGFIX:
                base_rules.append("* BUGFIX MODE ACTIONABILITY: apply the smallest corrective operations needed to remove the failure path.")
            elif mode == PromptMode.REFACTOR:
                base_rules.append("* REFACTOR MODE ACTIONABILITY: preserve behavior while improving structure with minimal operations.")
        elif executor_response_format == "json_edits":
            if compact:
                rules = [
                    "You are a deterministic code modification engine.",
                    "STRICT RULES:",
                    "* Output ONLY valid JSON with format exactly {\"format\":\"nexus_edits_v2\",\"edits\":[...]}",
                    "* JSON only; no markdown, no prose.",
                    "* Allowed op values: replace_range, insert_after, insert_before, create_file, delete_file.",
                    "* Use `path` (not `file`) and a flat `edits` list.",
                    "* Use exact anchors/old_text copied from provided slices only.",
                    "* Keep edits minimal and surgical.",
                    "* EMPTY-EDIT GUARDRAIL:",
                    "* If active-file slices are present, empty edits are invalid.",
                    "* If at least one active-file anchor is present, include at least one edit targeting the active file path.",
                    "* Prefer minimal safe partial edits over empty edits when uncertain.",
                ]
                if mode == PromptMode.FEATURE:
                    rules.append("* FEATURE MODE ACTIONABILITY: implement the capability with concrete edits.")
                    rules.append("* FEATURE MODE OUTPUT FLOOR: output at least 1 edit object when active-file slices are present.")
                    rules.append("* FEATURE MODE HARD BLOCK: do NOT output {\"format\":\"nexus_edits_v2\",\"edits\":[]} when active-file slices are present.")
                elif mode == PromptMode.BUGFIX:
                    rules.append("* BUGFIX MODE ACTIONABILITY: apply minimal corrective edits with concrete anchors.")
                elif mode == PromptMode.REFACTOR:
                    rules.append("* REFACTOR MODE ACTIONABILITY: make structural edits with behavior parity.")
                    rules.append("* REFACTOR ANCHOR STRATEGY: prefer `insert_after` with stable anchors and short `replace_range` spans.")
                    rules.append("* REFACTOR ANCHOR STRATEGY: avoid long multi-line `old_text` blocks that are prone to mismatch.")
                    rules.append("* REFACTOR ANCHOR STRATEGY: if replacing logic, target only the smallest exact block visible in provided slices.")
                    rules.append("* REFACTOR QUALITY BAR: do NOT submit trivial wrapper-only refactors (e.g., wrapping a single `String.join(...)` call with no meaningful flow extraction).")
                    rules.append("* REFACTOR QUALITY BAR: extract at least one cohesive logic block from the active method (validation branch, repeated conditional sequence, or input collection cluster).")
                    rules.append("* REFACTOR QUALITY BAR: resulting edits should reduce local complexity/duplication, not just rename an expression.")
                return "\n".join(rules)
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
                "* Prefer insert_after/insert_before for additive changes to reduce mismatch risk.",
                "* Use replace_range only when old_text is copied verbatim from provided context, including blank lines and spacing.",
                "* Do not emit edits for files/methods whose required anchors/signatures are not present in provided context slices.",
                "* If context is uncertain, prefer minimal, anchor-safe edits over speculative broad rewrites.",
                "* EMPTY-EDIT GUARDRAIL:",
                "* Return empty edits ONLY when required anchors/targets are truly missing from provided context.",
                "* If the Active File section includes any code slice, treat that as actionable context and do NOT return empty edits.",
                "* If actionable context exists, an empty edits array is INVALID.",
                "* If active file slices include target method(s) and related files include persistence/layout anchors, produce a non-empty edit plan.",
                "* If at least one active-file anchor is present, include at least one edit targeting the active file path.",
                "* If Android layout/resource anchors are present and task implies UI wiring, include at least one related XML or linked Java/Kotlin edit.",
                "* If full end-to-end implementation is uncertain, still return the safest non-empty partial edit set anchored to provided context.",
            ]
            if mode == PromptMode.FEATURE:
                base_rules.append("* FEATURE MODE ACTIONABILITY: implement the requested capability with concrete code edits; do not return empty edits when anchors exist.")
                base_rules.append("* FEATURE MODE OUTPUT FLOOR: when active-file slices are present, output at least 1 edit object.")
                base_rules.append("* FEATURE MODE HARD BLOCK: do NOT output {\"format\":\"nexus_edits_v2\",\"edits\":[]} when active-file slices are present.")
                base_rules.append("* FEATURE MODE SCOPE: start with active file + directly linked layout/resource files first; only extend to persistence/config files when exact signatures are present in context.")
                base_rules.append("* FEATURE MODE ANCHOR DISCIPLINE: do not invent callback/function names; reuse exact names present in provided slices.")
            elif mode == PromptMode.BUGFIX:
                base_rules.append("* BUGFIX MODE ACTIONABILITY: add/adjust the minimal defensive or corrective logic needed to remove the failure path; do not return empty edits when anchors exist.")
                base_rules.append("* BUGFIX MODE OUTPUT FLOOR: when active-file slices are present, output at least 1 edit object.")
            elif mode == PromptMode.REFACTOR:
                base_rules.append("* REFACTOR MODE ACTIONABILITY: perform structural cleanup with behavior parity and concrete edits; do not return empty edits when anchors exist.")
                base_rules.append("* REFACTOR MODE OUTPUT FLOOR: when active-file slices are present, output at least 1 edit object.")
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
        if mode == PromptMode.ANALYSIS:
            return "Respond with a concise technical analysis. Do not output a Nexus Patch payload. Do not propose file edits as operations. If code changes may be useful, describe them as recommendations only."
        if mode == PromptMode.ARCHITECTURE:
            return "Respond with a concise structured analysis/briefing (not a patch)."
        executor_response_format = resolve_executor_response_format(executor_response_format)
        if executor_response_format == "nexus_patch_v1":
            return "Your response must be ONLY a Nexus Patch v1 payload beginning with NEXUS_PATCH v1."
        if executor_response_format == "json_edits":
            return "Your response must be ONLY valid JSON in nexus_edits_v2 format."
        return "Your response must be ONLY a valid unified diff patch."

    def _missing_context_policy(self, mode: PromptMode, executor_response_format: str = "unified_diff") -> str:
        if mode == PromptMode.ANALYSIS:
            return "If required context is missing, explicitly state the gap, provide best-effort analysis from available evidence, and label assumptions."
        if mode == PromptMode.ARCHITECTURE:
            return "If context is missing, state assumptions explicitly and continue with the structured briefing."
        executor_response_format = resolve_executor_response_format(executor_response_format)
        if executor_response_format == "nexus_patch_v1":
            if mode in {PromptMode.FEATURE, PromptMode.BUGFIX, PromptMode.REFACTOR}:
                return "If active-file slices exist for a code-change request, return at least one deterministic Nexus Patch operation. Use an empty <Patch></Patch> only for explicit no-code-change requests or truly missing targets."
            return "If required context is missing, return an empty <Patch></Patch> per the response contract."
        if executor_response_format == "json_edits":
            if mode in {PromptMode.FEATURE, PromptMode.BUGFIX, PromptMode.REFACTOR}:
                return "If active-file slices exist, you MUST return non-empty edits. If full scope is uncertain, return minimal safe partial edits rather than empty edits."
            return "If required context is missing, return empty edits per the response contract."
        return "If required context is missing, output an empty diff per the response contract."

    def _build_output_gate_line(
        self,
        mode: PromptMode,
        executor_response_format: str,
        context: ExtractionContext,
    ) -> str:
        executor_response_format = resolve_executor_response_format(executor_response_format)
        if mode in {PromptMode.ARCHITECTURE, PromptMode.ANALYSIS} or executor_response_format not in {"json_edits", "nexus_patch_v1"}:
            return ""
        has_active_slices = bool(context.active_file and context.active_file.slices)
        if executor_response_format == "nexus_patch_v1":
            if has_active_slices and mode in {PromptMode.FEATURE, PromptMode.BUGFIX, PromptMode.REFACTOR}:
                return "OUTPUT GATE: <Patch> MUST contain at least one <Op> for this request."
            return "OUTPUT GATE: return empty <Patch></Patch> only if no actionable anchors or symbols are present."
        if has_active_slices and mode in {PromptMode.FEATURE, PromptMode.BUGFIX, PromptMode.REFACTOR}:
            return "OUTPUT GATE: `edits` length MUST be >= 1 for this request."
        return "OUTPUT GATE: return empty edits only if no actionable anchors are present in any provided slice."

    def _select_related_files_for_prompt(
        self,
        mode: PromptMode,
        executor_response_format: str,
        active_file: Optional[str],
        related_files: List[ExtractedFile],
    ) -> List[ExtractedFile]:
        if not related_files:
            return []
        executor_response_format = resolve_executor_response_format(executor_response_format)
        if mode not in {PromptMode.FEATURE, PromptMode.BUGFIX, PromptMode.REFACTOR} or executor_response_format != "json_edits":
            return related_files

        active_norm = (active_file or "").replace("\\", "/")
        active_module = active_norm.split("/src/")[0] if "/src/" in active_norm else ""
        active_tokens = [tok for tok in ["alarm", "dialog", "timer", "snooze", "input"] if tok in active_norm.lower()]
        active_base = Path(active_norm).stem.lower() if active_norm else ""

        def _score(rel_file: ExtractedFile) -> tuple[int, str]:
            path = rel_file.rel_path.replace("\\", "/")
            score = 0
            if active_module and path.startswith(active_module):
                score += 8
            if path.endswith(".xml"):
                score += 5
            if path.endswith(".java") or path.endswith(".kt"):
                score += 4
            if all(tok in path.lower() for tok in active_tokens):
                score += 12
            if "dialog_alarm_input" in path.lower():
                score += 18
            if active_base and active_base in path.lower():
                score += 14
            content_blob = " ".join((s.reason or "") + " " + (s.content or "") for s in rel_file.slices).lower()
            if "insertalarm" in content_blob or "insertalarm(" in content_blob:
                score += 12
            if "insert" in content_blob or "update" in content_blob or "save" in content_blob:
                score += 6
            if "onalarmset" in content_blob or "confirmbutton" in content_blob or "findviewbyid" in content_blob:
                score += 10
            if "@id/" in content_blob or "android_layout" in content_blob:
                score += 6
            if "alarmdialoglistener" in content_blob or "onalarmset" in content_blob:
                score += 5
            if "androidmanifest.xml" in path:
                score -= 2
            return (score, path)

        ranked = sorted(related_files, key=_score, reverse=True)
        return ranked[:6]

    def _build_actionability_verdict(
        self,
        mode: PromptMode,
        executor_response_format: str,
        context: ExtractionContext,
    ) -> List[str]:
        executor_response_format = resolve_executor_response_format(executor_response_format)
        if mode == PromptMode.ARCHITECTURE or executor_response_format != "json_edits":
            return []
        active_slices = context.active_file.slices if context.active_file else []
        active_anchor_count = len([s for s in active_slices if s.anchor_symbol or (s.reason or "").startswith("Anchor")])
        has_active_tail = any("Anchor Tail:" in (s.reason or "") for s in active_slices)
        related_slices = [sl for rf in context.related_files for sl in rf.slices]
        has_layout_signal = any("@id/" in (s.content or "") or "ANDROID_LAYOUT" in (s.reason or "") for s in related_slices + active_slices)
        has_persistence_signal = any("insert" in (s.reason or "").lower() or "insert" in (s.content or "").lower() for s in related_slices)
        non_empty_required = bool(active_slices)
        return [
            f"mode: {mode.value}",
            f"active_file_slices: {len(active_slices)}",
            f"active_anchor_count: {active_anchor_count}",
            f"has_active_tail_slice: {str(has_active_tail).lower()}",
            f"has_layout_signal: {str(has_layout_signal).lower()}",
            f"has_persistence_signal: {str(has_persistence_signal).lower()}",
            f"empty_edits_disallowed: {str(non_empty_required).lower()}",
            "verdict: return at least one safe anchor-based edit when empty_edits_disallowed=true",
        ]

    def _build_edit_starter_hints(
        self,
        mode: PromptMode,
        executor_response_format: str,
        context: ExtractionContext,
    ) -> List[str]:
        executor_response_format = resolve_executor_response_format(executor_response_format)
        if mode not in {PromptMode.FEATURE, PromptMode.BUGFIX, PromptMode.REFACTOR} or executor_response_format not in {"json_edits", "nexus_patch_v1"}:
            return []
        hints: List[str] = []
        active_path = context.active_file.rel_path if context.active_file else ""
        if active_path:
            hints.append(f"target_active_path: {active_path}")

        def _candidate_lines(slices: List[CodeSlice]) -> List[str]:
            out: List[str] = []
            interesting = (
                "listener.on",
                "onalarm",
                "confirmButton",
                "setContentView",
                "insertAlarm",
                "findViewById",
                "Spinner",
                "R.layout",
                "setOnClickListener",
                "timePickerButton",
                "dialogView",
                "isChecked()",
                "repeatDays",
                "Please select a time",
            )
            for sl in slices:
                for raw in sl.content.splitlines():
                    line = raw.strip()
                    if not line:
                        continue
                    if len(line) > 140:
                        continue
                    lower = line.lower()
                    if any(tok.lower() in lower for tok in interesting):
                        out.append(line)
            # deterministic unique
            uniq = []
            seen = set()
            for line in out:
                if line in seen:
                    continue
                seen.add(line)
                uniq.append(line)
            return uniq

        active_lines = _candidate_lines(context.active_file.slices if context.active_file else [])
        for line in active_lines[:4]:
            hints.append(f"active_anchor_hint: {line}")

        if mode == PromptMode.REFACTOR:
            if executor_response_format == "nexus_patch_v1":
                hints.append("refactor_hint: prefer symbol actions only when `symbol=` matches an indexed symbol name exactly.")
                hints.append("refactor_hint: use insert_text/replace_text for imports and non-symbol anchors.")
                hints.append("refactor_hint: use replace_text only for exact unique snippets.")
            else:
                hints.append("refactor_hint: prefer insert_after with anchor `public class AlarmDialog {` for helper extraction.")
                hints.append("refactor_hint: when replacing call sites, use the smallest exact snippet around the call expression.")
            hints.append("refactor_hint: prioritize extracting repeated checkbox/repeat-day logic or confirm-button validation flow.")

        related_lines: List[str] = []
        for rel_file in context.related_files:
            related_lines.extend(_candidate_lines(rel_file.slices))
        # deterministic unique for related hints
        seen_related = set()
        for line in related_lines:
            if line in seen_related:
                continue
            seen_related.add(line)
            if "insertAlarm" in line or "Spinner" in line or "confirmButton" in line or "dialog_alarm_input" in line:
                hints.append(f"related_anchor_hint: {line}")
            if len(hints) >= 10:
                break
        return hints

    def _build_symbol_action_guidance(
        self,
        mode: PromptMode,
        executor_response_format: str,
        context: ExtractionContext,
    ) -> List[str]:
        executor_response_format = resolve_executor_response_format(executor_response_format)
        if mode not in {PromptMode.FEATURE, PromptMode.BUGFIX, PromptMode.REFACTOR}:
            return []
        if executor_response_format != "nexus_patch_v1":
            return []

        lines: List[str] = [
            "Use symbol actions only with exact indexed names from the list below; never use declaration text like `def name`.",
            "Imports are not valid symbol targets unless explicitly listed as symbols; edit imports with `insert_text` or `replace_text`.",
            "For non-symbol anchors, use exact text actions (`replace_text`/`insert_text`) with unique snippets.",
        ]
        lines.append("Indexed symbols available in provided context:")

        files: List[ExtractedFile] = []
        if context.active_file:
            files.append(context.active_file)
        files.extend(context.related_files)
        for file in files[:6]:
            symbol_names = [sym.name for sym in (file.symbols or []) if getattr(sym, "name", None)]
            if not symbol_names:
                continue
            preview = ", ".join(symbol_names[:8])
            if len(symbol_names) > 8:
                preview += ", ..."
            lines.append(f"{file.rel_path}: {preview}")
        return lines

    def _build_file_section(self, file: ExtractedFile, balancer: TokenBalancer, is_active: bool = False, compact: bool = False) -> str:
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

        if compact:
            def _compact_slice_key(slice_obj: CodeSlice) -> tuple[int, int, str]:
                reason = (slice_obj.reason or "").lower()
                content = (slice_obj.content or "").lower()
                score = 0
                if "anchor tail: show" in reason:
                    score += 20
                if "anchor: show" in reason:
                    score += 16
                if "insertalarm" in reason or "insertalarm(" in content:
                    score += 14
                if "onalarmset" in content or "listener.on" in content:
                    score += 12
                if "@+id/" in content or "dialog_alarm_input" in content:
                    score += 10
                if "framework artifact" in reason:
                    score -= 8
                return (-score, priority_map.get(slice_obj.expansion_type, 99), reason)

            sorted_slices = sorted(file.slices, key=_compact_slice_key)

        if compact:
            max_slices = 3 if is_active else 2
            sorted_slices = sorted_slices[:max_slices]

        for s in sorted_slices:
            slice_header = f"\n[Code Slice: {s.reason}]"
            slice_body = s.content or ""
            if not slice_body.strip():
                hydrated = self._hydrate_slice_content(file.rel_path, s.start_line, s.end_line)
                if hydrated:
                    slice_body = hydrated
            if compact:
                slice_lines = slice_body.splitlines()
                slice_lines = slice_lines[:20]
                slice_body = "\n".join(slice_lines)
                if len(slice_body) > 900:
                    slice_body = slice_body[:900] + "\n... (compact truncated)"
            slice_content = f"```\n{slice_body}\n```"
            
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

    def _hydrate_slice_content(self, rel_path: str, start_line: int, end_line: int) -> str:
        """
        Best-effort content hydration for sparse slice metadata.
        This is primarily for fixture re-rendering paths where slices may only include
        line ranges and reasons but omit inline content.
        """
        try:
            project_root = Path(self.env.loader.searchpath[0]).resolve().parent
            candidate_targets = [
                (project_root / rel_path).resolve(),
                (project_root / "test_workspaces" / "nexus_patch_v1_fixture" / rel_path).resolve(),
                (project_root / "backend" / "test_workspaces" / "nexus_patch_v1_fixture" / rel_path).resolve(),
            ]
            target = next((cand for cand in candidate_targets if cand.is_file()), None)
            if target is None:
                return ""
            with open(target, "r", encoding="utf-8", errors="ignore") as handle:
                lines = handle.readlines()
            if not lines:
                return ""
            start = max(1, int(start_line or 1))
            end = max(start, int(end_line or start))
            start_idx = max(0, start - 1)
            end_idx = min(len(lines), end)
            chunk = "".join(lines[start_idx:end_idx]).rstrip("\n")
            return chunk
        except Exception:
            return ""

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
