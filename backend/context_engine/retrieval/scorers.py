import os
from typing import List, Optional
from .models import ScoreComponent, RetrievalQuery
from ..models.file import FileMetadata
from ..index.manager import IndexManager
from ..index.traversal import GraphTraversalEngine
from ..runtime.analyzer import RuntimeAnalyzer

def score_runtime_relevance(query: RetrievalQuery, candidate: FileMetadata, runtime: RuntimeAnalyzer, index: IndexManager) -> Optional[ScoreComponent]:
    referenced_files = runtime.get_referenced_files()
    referenced_symbols = runtime.get_referenced_symbols()
    execution_chains = runtime.get_execution_chains()
    
    # 1. Match Exact Symbol in Execution Chain
    for chain in execution_chains:
        for i, node in enumerate(chain):
            if ':' in node:
                file_part, sym_name = node.split(':', 1)
                if file_part in candidate.rel_path or candidate.rel_path in file_part:
                    # NORMALIZED: Reduced max points from 95 to 70
                    points = 70.0 - (i * 5.0)
                    return ScoreComponent(
                        factor="Execution Chain Match",
                        points=max(50.0, points),
                        reason=f"Symbol '{sym_name}' is in the active execution chain (Position {i}).",
                        path=chain[:i+1]
                    )

    # 2. Match File in Execution Chain
    for chain in execution_chains:
        for i, node in enumerate(chain):
            file_part = node.split(':')[0]
            if file_part in candidate.rel_path or candidate.rel_path in file_part:
                return ScoreComponent(
                    factor="Runtime File Match",
                    points=60.0 - (i * 5.0),
                    reason=f"File is part of the active execution chain (Position {i}).",
                    path=chain[:i+1]
                )

    # 3. Match Symbols (Fallback)
    if referenced_symbols:
        candidate_symbols = index.get_symbols_for_file(candidate.rel_path)
        for sym in candidate_symbols:
            if sym.name in referenced_symbols:
                return ScoreComponent(
                    factor="Runtime Symbol Match",
                    points=65.0,
                    reason=f"Symbol '{sym.name}' found in active stack trace is defined in this file."
                )

    # 4. Match File (Fallback)
    cand_name = os.path.basename(candidate.rel_path)
    for ref_file in referenced_files:
        if cand_name in ref_file or ref_file in candidate.rel_path:
            return ScoreComponent(
                factor="Runtime Failure",
                points=55.0,
                reason=f"File referenced in active stack trace: {ref_file}"
            )

    return None

def score_proximity(query: RetrievalQuery, candidate: FileMetadata) -> Optional[ScoreComponent]:
    if not query.active_file:
        return None
    
    active_dir = os.path.dirname(query.active_file)
    cand_dir = os.path.dirname(candidate.rel_path)
    
    if active_dir == cand_dir and query.active_file != candidate.rel_path:
        return ScoreComponent(
            factor="Proximity",
            points=15.0,
            reason=f"Located in the same directory: {active_dir}"
        )
    return None

def score_classification(query: RetrievalQuery, candidate: FileMetadata) -> Optional[ScoreComponent]:
    task_lower = query.task.lower()
    mapping = {
        "route": ["api", "route", "endpoint", "controller", "request"],
        "model": ["db", "database", "model", "schema", "table", "entity"],
        "ui": ["component", "view", "page", "css", "style", "frontend"],
        "utility": ["util", "helper", "common", "shared", "tool"],
        "config": ["env", "config", "settings", "setup"]
    }
    
    keywords = mapping.get(candidate.classification, [])
    for kw in keywords:
        if kw in task_lower:
            # NORMALIZED: Reduced from 30 to 15
            return ScoreComponent(
                factor="Classification Match",
                points=15.0,
                reason=f"File category '{candidate.classification}' matches task keyword '{kw}'"
            )
    return None

def score_name_similarity(query: RetrievalQuery, candidate: FileMetadata) -> Optional[ScoreComponent]:
    task_words = set(query.task.lower().replace("_", " ").replace("-", " ").split())
    file_name = os.path.basename(candidate.rel_path).lower()
    
    # BOOSTED: Increased from 15 to 40
    best_match = 0
    match_word = ""
    for word in task_words:
        if len(word) > 3 and word in file_name:
            best_match = 40.0
            match_word = word
            break
    
    if best_match > 0:
        return ScoreComponent(
            factor="Name Similarity",
            points=best_match,
            reason=f"File name contains task keyword: '{match_word}'"
        )
    return None

def score_modification_intent(query: RetrievalQuery, candidate: FileMetadata, index: IndexManager) -> Optional[ScoreComponent]:
    """
    Intelligent intent-aware scorer that biases toward likely modification layers.
    Treats mappings as soft biases.
    """
    mode = query.mode
    task_lower = query.task.lower()
    
    # Layer biasing
    if mode == "feature":
        # Features likely happen in services/logic
        if candidate.classification in {"utility", "model"}:
            return ScoreComponent(factor="Intent Bias", points=25.0, reason="Logic layer prioritized for feature development")
    
    elif mode == "refactor" or "extract" in task_lower:
        # Refactors likely target validators, utils, or abstractions
        if "validator" in candidate.rel_path.lower() or candidate.classification == "utility":
            return ScoreComponent(factor="Intent Bias", points=30.0, reason="Abstraction/Utility layer prioritized for refactoring")
            
    # Symbol-level intent matching
    symbols = index.get_symbols_for_file(candidate.rel_path)
    for sym in symbols:
        sym_name_lower = sym.name.lower()
        # If task mentions a specific action (e.g. 'validate') and symbol matches
        for word in ["validate", "check", "parse", "process", "calculate", "save", "fetch"]:
            if word in task_lower and word in sym_name_lower:
                return ScoreComponent(
                    factor="Symbol Intent Match", 
                    points=35.0, 
                    reason=f"Symbol '{sym.name}' matches action '{word}' in task"
                )
                
    return None

def score_hub_penalty(query: RetrievalQuery, candidate: FileMetadata, index: IndexManager) -> Optional[ScoreComponent]:
    """
    Applies a dynamic penalty to graph hubs (routes, main) for modification tasks.
    """
    # Only penalize if it's a modification task and not explicitly targeting entry logic
    is_mod = query.mode in {"feature", "bugfix", "refactor"}
    task_lower = query.task.lower()
    targets_entry = any(word in task_lower for word in ["route", "endpoint", "api", "entry", "main", "controller"])
    
    if is_mod and not targets_entry:
        if candidate.classification == "route" or os.path.basename(candidate.rel_path) == "main.py":
            # Dynamic penalty based on out-degree (hubs have high out-degree)
            deps = index.get_dependencies(candidate.rel_path)
            out_degree = len([d for d in deps if d.type != "import"]) # Generic calls
            
            penalty = -10.0 - (min(out_degree, 10) * 2.0)
            return ScoreComponent(
                factor="Hub Penalty",
                points=penalty,
                reason=f"Reduced priority for architectural hub in modification task (Out-degree: {out_degree})"
            )
            
    return None

def score_framework_artifacts(query: RetrievalQuery, candidate: FileMetadata, index: IndexManager) -> Optional[ScoreComponent]:
    artifacts = index.get_artifacts_for_file(candidate.rel_path)
    if not artifacts:
        return None
        
    task_lower = query.task.lower()
    
    for artifact in artifacts:
        if artifact.artifact_type.lower().replace("_", " ") in task_lower or artifact.name.lower() in task_lower:
            # NORMALIZED: Reduced from 35 to 20
            return ScoreComponent(
                factor="Framework Relevance",
                points=20.0,
                reason=f"Matches framework artifact: {artifact.artifact_type} ({artifact.name})"
            )
            
    if query.active_file:
        active_artifacts = index.get_artifacts_for_file(query.active_file)
        if active_artifacts and artifacts:
            cand_types = set(a.artifact_type for a in artifacts)
            active_types = set(a.artifact_type for a in active_artifacts)
            if cand_types.intersection(active_types):
                 return ScoreComponent(
                    factor="Shared Architecture",
                    points=5.0,
                    reason=f"Shares framework architecture layer"
                )

    return None

def score_config_relevance(query: RetrievalQuery, candidate: FileMetadata, index: IndexManager) -> Optional[ScoreComponent]:
    if not query.active_file:
        return None
        
    cand_is_config = candidate.classification == "config"
    active_meta = index.get_file_metadata(query.active_file)
    active_is_config = active_meta.classification == "config" if active_meta else False

    # If candidate is a config and active is a source file, check if config refers to active
    if cand_is_config and not active_is_config:
        edges = index.get_dependencies(candidate.rel_path)
        active_name = os.path.basename(query.active_file)
        for edge in edges:
            if active_name in edge.target_id or edge.target_id in query.active_file:
                return ScoreComponent(
                    factor="Config Reference",
                    points=25.0,
                    reason=f"Config file '{candidate.rel_path}' references active file"
                )

    # If active is a config and candidate is a source file
    if active_is_config and not cand_is_config:
         edges = index.get_dependencies(query.active_file)
         cand_name = os.path.basename(candidate.rel_path)
         for edge in edges:
            if cand_name in edge.target_id or edge.target_id in candidate.rel_path:
                return ScoreComponent(
                    factor="Config Target",
                    points=30.0,
                    reason=f"Active config references this file"
                )

    return None

def score_cpp_relationships(query: RetrievalQuery, candidate: FileMetadata, index: IndexManager) -> Optional[ScoreComponent]:
    if not query.active_file:
        return None
        
    active_ext = query.active_file.lower().split('.')[-1]
    cand_ext = candidate.rel_path.lower().split('.')[-1]
    
    cpp_exts = {"cpp", "c", "cc", "cxx", "h", "hpp", "hxx", "hh"}
    if active_ext not in cpp_exts or cand_ext not in cpp_exts:
        return None

    # 1. Header/Source Pair
    active_base = query.active_file.rsplit('.', 1)[0]
    cand_base = candidate.rel_path.rsplit('.', 1)[0]
    if active_base == cand_base:
        return ScoreComponent(
            factor="C++ Header/Source Pair",
            points=50.0,
            reason=f"This is the corresponding header/source for the active file"
        )

    # 2. Includes
    edges = index.get_dependencies(query.active_file)
    for edge in edges:
        if edge.type == "include" and (edge.target_id in candidate.rel_path or candidate.rel_path in edge.target_id):
            return ScoreComponent(
                factor="C++ Include",
                points=30.0,
                reason=f"Active file includes this header"
            )

    return None

def score_dependencies(query: RetrievalQuery, candidate: FileMetadata, index: IndexManager) -> Optional[ScoreComponent]:
    if not query.active_file:
        return None
        
    best_component: Optional[ScoreComponent] = None
    
    # 1. File-level direct imports
    active_deps = index.get_dependencies(query.active_file)
    for dep in active_deps:
        if dep.type == "import" and (dep.target_id in candidate.rel_path or candidate.rel_path in dep.target_id):
            comp = ScoreComponent(
                factor="Direct Dependency",
                points=30.0,
                reason=f"Directly imported by active file",
                path=[query.active_file, candidate.rel_path]
            )
            if not best_component or comp.points > best_component.points:
                best_component = comp
            
    # 2. Reverse Dependency
    cand_deps = index.get_dependencies(candidate.rel_path)
    for dep in cand_deps:
        if dep.type == "import" and (dep.target_id in query.active_file or query.active_file in dep.target_id):
            comp = ScoreComponent(
                factor="Reverse Dependency",
                points=25.0,
                reason=f"This file imports the active file",
                path=[candidate.rel_path, query.active_file]
            )
            if not best_component or comp.points > best_component.points:
                best_component = comp
            
    # 3. Deep symbol call chain
    traversal = GraphTraversalEngine(index)
    active_symbols = index.get_symbols_for_file(query.active_file)
    
    for sym in active_symbols:
        start_id = f"{query.active_file}:{sym.name}"
        paths = traversal.traverse_outbound(start_id, max_depth=2, allowed_types={"call", "async_call"})
        for path_result in paths:
            target_id = path_result.target_id
            target_file = target_id.split(':')[0]
            
            if target_file == candidate.rel_path:
                comp = ScoreComponent(
                    factor="Call Chain",
                    points=35.0,
                    reason=f"Execution path found: {sym.name} calls {target_id.split(':')[-1]}",
                    path=path_result.path
                )
                if not best_component or comp.points > best_component.points:
                    best_component = comp

    return best_component
