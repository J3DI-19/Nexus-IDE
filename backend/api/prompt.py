from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict
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
        candidate_map = {
            cand.file_metadata.rel_path: cand
            for cand in (request.selected_candidates or [])
        }
        for rel_path in request.selected_files:
            if rel_path in candidate_map:
                candidates.append(candidate_map[rel_path])
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
        prompt = pipeline.prompt_builder.build_prompt(query, context, impact=impact_result, mode=mode, runtime_artifacts=runtime_artifacts)
        return {"prompt": prompt, "stats": _build_prompt_stats(prompt, context)}
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
