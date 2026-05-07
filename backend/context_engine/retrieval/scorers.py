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
    
    # 1. Match File
    cand_name = os.path.basename(candidate.rel_path)
    for ref_file in referenced_files:
        if cand_name in ref_file or ref_file in candidate.rel_path:
            return ScoreComponent(
                factor="Runtime Failure",
                points=80.0,
                reason=f"File referenced in active stack trace: {ref_file}"
            )
            
    # 2. Match Symbols
    if referenced_symbols:
        candidate_symbols = index.get_symbols_for_file(candidate.rel_path)
        for sym in candidate_symbols:
            if sym.name in referenced_symbols:
                return ScoreComponent(
                    factor="Runtime Symbol Match",
                    points=90.0,
                    reason=f"Symbol '{sym.name}' found in active stack trace is defined in this file."
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
            points=20.0,
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
            return ScoreComponent(
                factor="Classification Match",
                points=30.0,
                reason=f"File category '{candidate.classification}' matches task keyword '{kw}'"
            )
    return None

def score_name_similarity(query: RetrievalQuery, candidate: FileMetadata) -> Optional[ScoreComponent]:
    task_words = set(query.task.lower().replace("_", " ").replace("-", " ").split())
    file_name = os.path.basename(candidate.rel_path).lower()
    
    for word in task_words:
        if len(word) > 3 and word in file_name:
            return ScoreComponent(
                factor="Name Similarity",
                points=15.0,
                reason=f"File name contains task keyword: '{word}'"
            )
    return None

def score_framework_artifacts(query: RetrievalQuery, candidate: FileMetadata, index: IndexManager) -> Optional[ScoreComponent]:
    artifacts = index.get_artifacts_for_file(candidate.rel_path)
    if not artifacts:
        return None
        
    task_lower = query.task.lower()
    
    for artifact in artifacts:
        if artifact.artifact_type.lower().replace("_", " ") in task_lower or artifact.name.lower() in task_lower:
            return ScoreComponent(
                factor="Framework Relevance",
                points=35.0,
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
                    points=10.0,
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
                    points=45.0,
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
                    points=55.0,
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
            points=70.0,
            reason=f"This is the corresponding header/source for the active file"
        )

    # 2. Includes
    edges = index.get_dependencies(query.active_file)
    for edge in edges:
        if edge.type == "include" and (edge.target_id in candidate.rel_path or candidate.rel_path in edge.target_id):
            return ScoreComponent(
                factor="C++ Include",
                points=45.0,
                reason=f"Active file includes this header"
            )

    return None

def score_dependencies(query: RetrievalQuery, candidate: FileMetadata, index: IndexManager) -> Optional[ScoreComponent]:
    if not query.active_file:
        return None
        
    # File-level direct imports
    active_deps = index.get_dependencies(query.active_file)
    for dep in active_deps:
        if dep.type == "import" and (dep.target_id in candidate.rel_path or candidate.rel_path in dep.target_id):
            return ScoreComponent(
                factor="Direct Dependency",
                points=50.0,
                reason=f"Directly imported by active file"
            )
            
    cand_deps = index.get_dependencies(candidate.rel_path)
    for dep in cand_deps:
        if dep.type == "import" and (dep.target_id in query.active_file or query.active_file in dep.target_id):
            return ScoreComponent(
                factor="Reverse Dependency",
                points=40.0,
                reason=f"This file imports the active file"
            )
            
    # Deep symbol call chain
    traversal = GraphTraversalEngine(index)
    # Check if active file symbols call candidate file symbols
    active_symbols = index.get_symbols_for_file(query.active_file)
    candidate_symbols = set([s.name for s in index.get_symbols_for_file(candidate.rel_path)])
    
    for sym in active_symbols:
        start_id = f"{query.active_file}:{sym.name}"
        paths = traversal.traverse_outbound(start_id, max_depth=2, allowed_types={"call", "async_call"})
        for path_result in paths:
            if path_result.target_id in candidate_symbols:
                return ScoreComponent(
                    factor="Call Chain",
                    points=60.0,
                    reason=f"Execution path found: {sym.name} calls {path_result.target_id}"
                )

    return None
