from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
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

class AssembleRequest(BaseModel):
    task: str
    active_file: str
    selected_files: List[str]
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
    Returns the currently active runtime artifacts.
    """
    artifacts = pipeline.runtime.get_active_artifacts()
    return {"artifacts": [a.dict() for a in artifacts]}

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
            active_file=request.file
        )
        candidates = pipeline.retrieval.retrieve(query)
        return {"candidates": [c.dict() for c in candidates]}
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
            active_file=request.active_file
        )
        mode = PromptMode(request.mode) if request.mode else PromptMode.FEATURE
        
        candidates = []
        for rel_path in request.selected_files:
            metadata = pipeline.index.get_file_metadata(rel_path)
            if metadata:
                artifacts = pipeline.index.get_artifacts_for_file(rel_path)
                candidates.append(ContextCandidate(
                    file_metadata=metadata,
                    score=100.0,
                    score_breakdown=[ScoreComponent(factor="User Selection", points=100.0, reason="Manually selected")],
                    matched_symbols=[s.name for s in pipeline.index.get_symbols_for_file(rel_path)],
                    matched_artifacts=[a.artifact_type for a in artifacts]
                ))
        
        context = pipeline.extraction.extract_context(query.active_file, candidates)
        
        # Also run impact analysis
        impact_result = None
        if query.active_file:
            impact_query = ImpactQuery(active_file=query.active_file, max_depth=3)
            impact_result = pipeline.impact.analyze(impact_query)
            
        prompt = pipeline.prompt_builder.build_prompt(query, context, impact=impact_result, mode=mode)
        return {"prompt": prompt}
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

@router.post("/prompt")
async def generate_prompt(request: PromptRequest):
    """Legacy prompt generation using templates and basic heuristics."""
    root = get_project_root()
    if not root:
        raise HTTPException(status_code=400, detail="Project root not set")

    if not request.file or not request.file.strip():
        raise HTTPException(status_code=400, detail="Path cannot be empty.")
    
    try:
        resolved_path = is_safe_path(root / request.file)
        if not resolved_path.is_file():
            raise HTTPException(status_code=404, detail=f"File not found: {request.file}")
        
        with open(resolved_path, "r", encoding="utf-8", errors="ignore") as f:
            full_content = f.read()
        
        all_files = fast_recursive_scan(str(root))
        
        safe_content = full_content.strip() or "Empty file"
        escaped_content = safe_content.replace("{", "{{").replace("}", "}}")
        
        language = detect_language(request.file)
        file_content_block = format_code_block(escaped_content, language)
        project_context = build_project_context(request.file, all_files)
        structure_section = build_structure_section(full_content, request.file)

        template = load_prompt_template()
        try:
            prompt = template.format(
                project_context=project_context,
                file_path=request.file,
                structure_section=structure_section,
                file_content_block=file_content_block,
                errors="No known runtime or compile errors.",
                goal=request.goal
            )
        except KeyError as e:
            raise HTTPException(status_code=500, detail=f"Template placeholder missing: {str(e)}")
        
        return {"prompt": prompt}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prompt generation failed: {str(e)}")
