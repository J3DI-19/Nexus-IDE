from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Tuple
import json
from pathlib import Path
import os
from utils.security import get_project_root, is_safe_path
from context_engine.core.scanner import fast_recursive_scan
from context_engine.core.pipeline import pipeline
from context_engine.retrieval.models import RetrievalQuery, ContextCandidate, ScoreComponent
from context_engine.impact.models import ImpactQuery
from context_engine.prompt_builder.models import PromptMode
from utils.prompt_utils import (
    load_prompt_template,
    detect_language,
    build_project_context,
    build_structure_section,
    format_code_block
)

router = APIRouter()

class PromptRequest(BaseModel):
    file: str
    goal: str
    include_slices: bool = False
    mode: Optional[str] = "feature"

class AssembleRequest(BaseModel):
    task: str
    active_file: str
    selected_files: List[str]
    selected_candidates: Optional[List[ContextCandidate]] = None
    selected_slices: Optional[Dict[str, List[int]]] = None # File path -> List of slice indices
    full_file_overrides: Optional[List[str]] = None # List of file paths to include entirely
    mode: Optional[str] = "feature"
    selected_preset_id: Optional[str] = None

class ImpactRequest(BaseModel):
    active_file: str

class RuntimeLogRequest(BaseModel):
    log: str

def _ensure_context_ready():
    if not pipeline.extraction:
        raise HTTPException(
            status_code=409,
            detail="Context engine is not initialized. Open a project folder first."
        )

def _estimate_tokens(text: str) -> int:
    return max(1, round(len(text) / 4)) if text else 0

def _build_prompt_stats(prompt: str, context) -> Dict[str, int]:
    files = []
    if context.active_file:
        files.append(context.active_file)
    files.extend(context.related_files)

    context_lines = 0
    for file in files:
        for slice_item in file.slices:
            context_lines += len(slice_item.content.splitlines())

    return {
        "files": len(files),
        "context_lines": context_lines,
        "prompt_tokens": _estimate_tokens(prompt)
    }

def _build_selection_reason_lines(candidates: List[ContextCandidate], selected_files: List[str], limit: int = 8) -> List[str]:
    by_path = {cand.file_metadata.rel_path: cand for cand in candidates}
    lines: List[str] = []
    for rel_path in selected_files:
        cand = by_path.get(rel_path)
        if not cand:
            continue
        top = sorted(cand.score_breakdown, key=lambda item: item.points, reverse=True)[:2]
        factors = ", ".join(f"{comp.factor}({comp.points:.1f})" for comp in top) if top else "manual selection"
        lines.append(f"{rel_path}: score={cand.score:.1f}; factors={factors}")
        if len(lines) >= limit:
            break
    return lines

def _build_selection_reason_lines_with_sources(
    candidates: List[ContextCandidate],
    selected_files: List[str],
    selection_sources: Dict[str, str],
    limit: int = 8
) -> List[str]:
    by_path = {cand.file_metadata.rel_path: cand for cand in candidates}
    lines: List[str] = []
    for rel_path in selected_files:
        cand = by_path.get(rel_path)
        if not cand:
            continue
        top = sorted(cand.score_breakdown, key=lambda item: item.points, reverse=True)[:2]
        factors = ", ".join(f"{comp.factor}({comp.points:.1f})" for comp in top) if top else "manual selection"
        source = selection_sources.get(rel_path, "auto")
        lines.append(f"{rel_path}: source={source}; score={cand.score:.1f}; factors={factors}")
        if len(lines) >= limit:
            break
    return lines

def _validate_prompt_quality(
    prompt: str,
    mode: PromptMode,
    stats: Dict[str, int],
    active_slice_reasons: List[str],
    selection_reasons: List[str],
    executor_response_format: str = "nexus_edits_v2",
) -> Tuple[int, List[Dict[str, str]], List[Dict[str, str]]]:
    checks: List[Dict[str, str]] = []
    warnings: List[Dict[str, str]] = []
    score = 100
    def add_check(name: str, passed: bool, detail: str, severity: str = "medium"):
        nonlocal score
        checks.append({"name": name, "pass": passed, "detail": detail, "severity": severity})
        if not passed:
            score -= 20 if severity == "high" else 10
    add_check("required_sections", all(s in prompt for s in ["### [SYSTEM RULES]", "### [PROJECT CONTEXT]", "### [TASK]"]), "Core sections must exist", "high")
    if mode == PromptMode.ARCHITECTURE:
        add_check("mode_contract", "structured analysis/briefing" in prompt and "ONLY a valid unified diff patch" not in prompt, "Architecture mode must use briefing contract", "high")
    elif executor_response_format == "nexus_edits_v2":
        add_check("mode_contract", "nexus_edits_v2" in prompt and "Output ONLY valid JSON" in prompt, "Patch modes must enforce nexus_edits_v2 contract", "high")
    else:
        add_check("mode_contract", "ONLY a valid unified diff patch" in prompt, "Patch modes must enforce unified diff contract", "high")
    tokens = stats.get("prompt_tokens", 0)
    add_check("token_budget", 150 <= tokens <= 8500, f"Prompt tokens within expected range ({tokens})", "medium")
    add_check("anchor_quality", bool(active_slice_reasons), "Active file should contain at least one slice", "medium")
    add_check("rationale_completeness", bool(selection_reasons), "Selection rationale should be present", "low")
    return max(0, min(100, score)), checks, warnings

def _prompt_settings_path() -> Path:
    appdata = os.getenv("APPDATA")
    if appdata:
        return Path(appdata) / "NexusIDE" / "config" / "prompt_settings.json"
    return Path.home() / ".nexuside" / "config" / "prompt_settings.json"


def _load_prompt_preset(selected_preset_id: Optional[str]) -> Dict[str, str]:
    settings_path = _prompt_settings_path()
    if not settings_path.exists():
        settings_path = get_project_root() / "backend" / "config" / "prompt_settings.json"
    if not settings_path.exists():
        settings_path = get_project_root() / "backend" / "backend" / "config" / "prompt_settings.json"
    if not settings_path.exists():
        return {"executor_response_format": "nexus_edits_v2"}
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        presets = data.get("presets", [])
        target_id = selected_preset_id or data.get("selected_preset_id")
        if not target_id:
            return {"executor_response_format": str(data.get("executor_response_format", "nexus_edits_v2"))}
        preset = next((p for p in presets if p.get("id") == target_id), None)
        if not preset:
            return {"executor_response_format": str(data.get("executor_response_format", "nexus_edits_v2"))}
        return {
            "id": str(preset.get("id", "")),
            "name": str(preset.get("name", "")),
            "template": str(preset.get("template", "")),
            "executor_response_format": str(data.get("executor_response_format", "nexus_edits_v2")),
        }
    except Exception:
        return {"executor_response_format": "nexus_edits_v2"}

@router.get("/context/status")
async def get_context_status():
    """
    Returns lightweight readiness information for the Context Engine.
    """
    symbol_count = sum(len(symbols) for symbols in pipeline.index.symbols.values())
    artifact_count = sum(len(artifacts) for artifacts in pipeline.index.artifacts.values())

    return {
        "initialized": pipeline.extraction is not None,
        "root": pipeline.root_path,
        "files": len(pipeline.index.files),
        "symbols": symbol_count,
        "artifacts": artifact_count,
        "frameworks": pipeline.project_metadata.frameworks_detected if pipeline.project_metadata else []
    }

@router.post("/context/initialize")
async def initialize_context_engine():
    """
    Initializes or refreshes the Context Engine index for the current project root.
    """
    root = get_project_root()
    if not root:
        raise HTTPException(status_code=400, detail="Project root not set")

    try:
        metadata = pipeline.initialize_project(str(root))
        symbol_count = sum(len(symbols) for symbols in pipeline.index.symbols.values())
        artifact_count = sum(len(artifacts) for artifacts in pipeline.index.artifacts.values())

        return {
            "status": "initialized",
            "root": pipeline.root_path,
            "files": len(pipeline.index.files),
            "symbols": symbol_count,
            "artifacts": artifact_count,
            "frameworks": metadata.frameworks_detected
        }
    except Exception as e:
        print(f"CONTEXT INIT ERROR: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/context/symbols")
async def list_context_symbols():
    """
    Returns indexed symbols for workspace search.
    """
    _ensure_context_ready()

    items = []
    for rel_path, symbols in pipeline.index.symbols.items():
        for symbol in symbols:
            items.append({
                "name": symbol.name,
                "type": symbol.type,
                "file": rel_path,
                "start_line": symbol.start_line,
                "end_line": symbol.end_line,
                "parent": symbol.parent_id
            })

    return {"symbols": items}

@router.post("/context/runtime")
async def ingest_runtime_log(request: RuntimeLogRequest):
    """
    Ingests raw execution logs for runtime intelligence.
    """
    try:
        artifact = pipeline.runtime.ingest_log(request.log)
        return {"status": "success", "artifact": artifact.dict() if artifact else None}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/context/runtime")
async def get_runtime_artifacts():
    """
    Returns the currently active runtime artifacts, execution chains, and hot symbols.
    """
    artifacts = pipeline.runtime.get_active_artifacts()
    chains = pipeline.runtime.get_execution_chains()
    hot_symbols = pipeline.runtime.get_hot_symbols()
    return {
        "artifacts": [a.dict() for a in artifacts],
        "execution_chains": chains,
        "hot_symbols": hot_symbols
    }

@router.post("/context/runtime/clear")
async def clear_runtime():
    pipeline.runtime.clear()
    return {"status": "cleared"}

@router.post("/context/impact")
async def analyze_impact(request: ImpactRequest):
    """
    Returns downstream impact analysis for a file change.
    """
    try:
        _ensure_context_ready()
        query = ImpactQuery(
            active_file=request.active_file,
            max_depth=3
        )
        result = pipeline.impact.analyze(query)
        return {"candidates": [c.dict() for c in result.candidates]}
    except Exception as e:
        print(f"IMPACT ERROR: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/context/retrieve")
async def retrieve_context(request: PromptRequest):
    """
    Returns raw retrieval candidates for interactive review.
    """
    try:
        _ensure_context_ready()
        query = RetrievalQuery(
            task=request.goal,
            active_file=request.file,
            mode=request.mode or "feature",
            include_slices=request.include_slices
        )
        candidates = pipeline.retrieve(query)
        return {
            "candidates": [c.dict() for c in candidates],
            "score_units": "points",
            "auto_select_threshold": 40
        }
    except Exception as e:
        print(f"RETRIEVAL ERROR: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/context/assemble")
async def assemble_context(request: AssembleRequest):
    """
    Assembles a prompt based on explicit user selections.
    """
    try:
        _ensure_context_ready()
        query = RetrievalQuery(
            task=request.task,
            active_file=request.active_file,
            mode=request.mode or "feature"
        )
        mode = PromptMode(request.mode) if request.mode else PromptMode.FEATURE
        
        candidates = []
        selection_sources: Dict[str, str] = {}
        user_forced_files: List[str] = []
        candidate_map = {
            cand.file_metadata.rel_path: cand
            for cand in (request.selected_candidates or [])
        }
        for rel_path in request.selected_files:
            if rel_path in candidate_map:
                candidates.append(candidate_map[rel_path])
                selection_sources[rel_path] = "auto_selected"
                continue

            metadata = pipeline.index.get_file_metadata(rel_path)
            if not metadata:
                continue

            artifacts = pipeline.index.get_artifacts_for_file(rel_path)
            symbols = pipeline.index.get_symbols_for_file(rel_path)
            candidates.append(ContextCandidate(
                file_metadata=metadata,
                score=0.0,
                score_breakdown=[ScoreComponent(
                    factor="Manual Selection",
                    points=0.0,
                    reason="Selected manually outside the current retrieval result set"
                )],
                matched_symbols=[s.name for s in symbols],
                matched_artifacts=[a.artifact_type for a in artifacts]
            ))
            selection_sources[rel_path] = "user_forced"
            user_forced_files.append(rel_path)
        
        context = pipeline.extraction.extract_context(
            query.active_file, 
            candidates, 
            mode=mode.value, 
            runtime=pipeline.runtime,
            full_file_overrides=request.full_file_overrides
        )
        
        # SLICE FILTERING: Prune extraction context based on user's surgical selection
        # Skip pruning for files in full_file_overrides
        overrides = set(request.full_file_overrides or [])
        
        if request.selected_slices:
            if context.active_file and context.active_file.rel_path in request.selected_slices:
                if context.active_file.rel_path not in overrides:
                    indices = set(request.selected_slices[context.active_file.rel_path])
                    context.active_file.slices = [s for i, s in enumerate(context.active_file.slices) if i in indices]
            
            for rel_file in context.related_files:
                if rel_file.rel_path in request.selected_slices:
                    if rel_file.rel_path not in overrides:
                        indices = set(request.selected_slices[rel_file.rel_path])
                        rel_file.slices = [s for i, s in enumerate(rel_file.slices) if i in indices]

        # Also run impact analysis
        impact_result = None
        if query.active_file:
            impact_query = ImpactQuery(active_file=query.active_file, max_depth=3)
            impact_result = pipeline.impact.analyze(impact_query)
            
        runtime_artifacts = pipeline.runtime.get_active_artifacts()
        selected_preset = _load_prompt_preset(request.selected_preset_id)
        executor_response_format = selected_preset.get("executor_response_format", "nexus_edits_v2")
        selection_reason_lines = _build_selection_reason_lines_with_sources(candidates, request.selected_files, selection_sources)
        prompt = pipeline.prompt_builder.build_prompt(
            query,
            context,
            impact=impact_result,
            mode=mode,
            runtime_artifacts=runtime_artifacts,
            preset_name=selected_preset.get("name"),
            preset_template=selected_preset.get("template"),
            selection_reasons=selection_reason_lines,
            executor_response_format=executor_response_format,
        )
        stats = _build_prompt_stats(prompt, context)
        active_reasons = [s.reason for s in (context.active_file.slices if context.active_file else [])]
        quality_score, quality_checks, warnings = _validate_prompt_quality(prompt, mode, stats, active_reasons, selection_reason_lines, executor_response_format)

        low_auto = [c.file_metadata.rel_path for c in candidates if c.score < 15 and selection_sources.get(c.file_metadata.rel_path) == "auto_selected"]
        low_forced = [c.file_metadata.rel_path for c in candidates if c.score < 15 and selection_sources.get(c.file_metadata.rel_path) == "user_forced"]
        for path in low_auto:
            warnings.append({"code": "low_signal_auto_selected", "message": "Low-signal auto-selected file.", "file": path, "source": "auto_selected"})
        for path in low_forced:
            warnings.append({"code": "low_signal_user_forced", "message": "Low-signal user-forced file preserved.", "file": path, "source": "user_forced"})

        fallback_applied = False
        if quality_score < 70 and low_auto:
            fallback_applied = True
            filtered_candidates = [c for c in candidates if not (selection_sources.get(c.file_metadata.rel_path) == "auto_selected" and c.score < 15)]
            fallback_context = pipeline.extraction.extract_context(
                query.active_file,
                filtered_candidates,
                mode=mode.value,
                runtime=pipeline.runtime,
                full_file_overrides=request.full_file_overrides,
            )
            fallback_prompt = pipeline.prompt_builder.build_prompt(
                query,
                fallback_context,
                impact=impact_result,
                mode=mode,
                runtime_artifacts=runtime_artifacts,
                preset_name=selected_preset.get("name"),
                preset_template=selected_preset.get("template"),
                selection_reasons=_build_selection_reason_lines_with_sources(filtered_candidates, request.selected_files, selection_sources),
                executor_response_format=executor_response_format,
            )
            fallback_stats = _build_prompt_stats(fallback_prompt, fallback_context)
            fallback_active = [s.reason for s in (fallback_context.active_file.slices if fallback_context.active_file else [])]
            fallback_score, fallback_checks, fallback_warnings = _validate_prompt_quality(
                fallback_prompt, mode, fallback_stats, fallback_active, selection_reason_lines, executor_response_format
            )
            if fallback_score >= quality_score:
                prompt = fallback_prompt
                context = fallback_context
                stats = fallback_stats
                quality_score = fallback_score
                quality_checks = fallback_checks
                warnings.extend(fallback_warnings)

        return {
            "prompt": prompt,
            "stats": stats,
            "quality_score": quality_score,
            "quality_checks": quality_checks,
            "warnings": warnings,
            "fallback_applied": fallback_applied,
            "user_forced_files": user_forced_files,
        }
    except Exception as e:
        print(f"ASSEMBLY ERROR: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/prompt/v2")
async def generate_prompt_v2(request: PromptRequest):
    """
    Experimental high-fidelity prompt generation using the Context Engine.
    """
    try:
        query = RetrievalQuery(
            task=request.goal,
            active_file=request.file
        )
        prompt = pipeline.assemble_prompt(query)
        return {"prompt": prompt}
    except Exception as e:
        print(f"PROMPT V2 ERROR: {e}")
        raise HTTPException(status_code=500, detail=f"Context Engine failed: {str(e)}")
