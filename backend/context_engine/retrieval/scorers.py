import os
import re
from typing import List, Optional
from .models import ScoreComponent, RetrievalQuery
from ..models.file import FileMetadata
from ..index.manager import IndexManager
from ..index.traversal import GraphTraversalEngine
from ..runtime.analyzer import RuntimeAnalyzer

QUERY_SYNONYMS = {
    "route": {"routing", "router", "routes"},
    "router": {"route", "routing", "routes"},
    "response": {"responses", "encoder", "encoders"},
    "schema": {"openapi", "model", "models", "params", "param"},
    "parameter": {"param", "params", "argument", "field"},
    "param": {"parameter", "params", "field"},
    "blueprint": {"blueprints", "scaffold", "register"},
    "context": {"ctx", "globals", "request"},
}

def _path_tokens(rel_path: str) -> List[str]:
    tokens: List[str] = []
    for part in re.split(r"[\\/._\-\:]+", rel_path):
        part = part.strip()
        if not part:
            continue
        # Keep both whole token and camel-case fragments to strengthen Android class-name alignment.
        tokens.append(part.lower())
        fragments = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)|\d+", part)
        for fragment in fragments:
            fragment = fragment.lower()
            if fragment and fragment not in tokens:
                tokens.append(fragment)
    return tokens

def _active_domain_tokens(active_file: Optional[str]) -> List[str]:
    if not active_file:
        return []
    weak = {
        "api", "route", "routes", "controller", "controllers",
        "src", "main", "java", "cs", "py", "ts", "tsx", "kt", "kts",
        "app", "com", "org", "net", "io", "example", "nexus",
        "activity", "fragment", "service", "receiver", "provider",
    }
    return [tok for tok in _path_tokens(active_file) if len(tok) > 3 and tok not in weak]

def _normalized_query_terms(task: str) -> List[str]:
    raw = task.lower().replace("-", " ").replace("_", " ").split()
    terms = set(raw)
    for token in raw:
        terms.update(QUERY_SYNONYMS.get(token, set()))
        for key, values in QUERY_SYNONYMS.items():
            if token in values:
                terms.add(key)
    return [term for term in terms if len(term) > 2]

def _is_framework_context(active_file: Optional[str], candidate_path: Optional[str] = None) -> bool:
    haystack = f"{(active_file or '').lower()} {(candidate_path or '').lower()}"
    markers = [
        "openapi/",
        "dependencies/",
        "security/",
        "sansio/",
        "json/",
        "applications.py",
        "blueprints.py",
        "wrappers.py",
        "ctx.py",
        "globals.py",
    ]
    return any(marker in haystack for marker in markers)


def _is_android_path(path: Optional[str]) -> bool:
    if not path:
        return False
    lower = path.lower()
    return any(
        marker in lower
        for marker in ["/src/main/", "/src/debug/", "/res/layout/", "androidmanifest.xml", "build.gradle", ".kt", ".java"]
    )


def _android_module_key(rel_path: str) -> str:
    normalized = rel_path.replace("\\", "/").strip("/")
    parts = normalized.split("/")
    if not parts:
        return ""
    if len(parts) >= 2 and parts[1] == "src":
        return parts[0]
    if normalized.endswith("build.gradle") or normalized.endswith("build.gradle.kts"):
        return parts[0] if len(parts) > 1 else "root"
    if "res/layout" in normalized:
        return parts[0]
    return parts[0]


def _layout_name_from_path(rel_path: str) -> str:
    normalized = rel_path.replace("\\", "/")
    name = os.path.basename(normalized)
    if not name.lower().endswith(".xml"):
        return ""
    return name[:-4]

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
    query_terms = set(_normalized_query_terms(query.task))
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
    task_words = set(_normalized_query_terms(query.task))
    file_name = os.path.basename(candidate.rel_path).lower()
    
    # Keep name matching as a light hint to avoid overfitting to generic names.
    weak_terms = {"service", "controller", "model", "route", "routes", "handler", "helper", "utils", "doc", "docs"}
    best_match = 0
    match_word = ""
    for word in task_words:
        if len(word) <= 3 or word in weak_terms:
            continue
        if word in file_name:
            best_match = 14.0
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
    query_terms = set(_normalized_query_terms(query.task))
    
    # Layer biasing
    if mode == "feature":
        # Features typically land in service/repository layers.
        path_lower = candidate.rel_path.lower()
        if "service" in path_lower or "repository" in path_lower:
            return ScoreComponent(factor="Intent Bias", points=24.0, reason="Service/data layer prioritized for feature development")
        if candidate.classification in {"utility", "model"}:
            return ScoreComponent(factor="Intent Bias", points=10.0, reason="Logic layer mildly prioritized for feature development")
    
    elif mode == "refactor" or "extract" in task_lower:
        # Refactors likely target validators, utils, or abstractions
        if "validator" in candidate.rel_path.lower() or candidate.classification == "utility":
            return ScoreComponent(factor="Intent Bias", points=30.0, reason="Abstraction/Utility layer prioritized for refactoring")
            
    # Symbol-level intent matching
    symbols = index.get_symbols_for_file(candidate.rel_path)
    for sym in symbols:
        sym_name_lower = sym.name.lower()
        # If task mentions a specific action (e.g. 'validate') and symbol matches
        extra_words: List[str] = []
        if query.mode == "feature" and _is_framework_context(query.active_file, candidate.rel_path):
            extra_words = ["route", "response", "schema", "param", "blueprint", "context"]
        for word in ["validate", "check", "parse", "process", "calculate", "save", "fetch", "render"] + extra_words:
            if (word in task_lower or word in query_terms) and word in sym_name_lower:
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
    is_mod = query.mode in {"feature", "bugfix", "refactor", "architecture"}
    task_lower = query.task.lower()
    targets_entry = any(word in task_lower for word in ["route", "endpoint", "api", "entry", "main", "controller"])
    
    if is_mod and not targets_entry:
        path_lower = candidate.rel_path.lower()
        basename = os.path.basename(path_lower)
        if (
            candidate.classification == "route"
            or basename in {"main.py", "main.ts", "main.tsx", "application.java", "program.cs"}
            or "router" in path_lower
            or "startup" in path_lower
            or "config" in path_lower
        ):
            # Dynamic penalty based on out-degree (hubs have high out-degree)
            deps = index.get_dependencies(candidate.rel_path)
            out_degree = len([d for d in deps if d.type != "import"]) # Generic calls
            
            penalty = -16.0 - (min(out_degree, 12) * 2.0)
            return ScoreComponent(
                factor="Hub Penalty",
                points=penalty,
                reason=f"Reduced priority for architectural hub in modification task (Out-degree: {out_degree})"
            )
            
    return None

def score_active_file_affinity(query: RetrievalQuery, candidate: FileMetadata) -> Optional[ScoreComponent]:
    """
    Biases toward files that share the active-file domain token (e.g. payment_* -> payment service).
    """
    if not query.active_file:
        return None

    active_base = os.path.basename(query.active_file).lower()
    candidate_path = candidate.rel_path.lower()

    base = active_base.replace(".tsx", "").replace(".ts", "").replace(".py", "").replace(".java", "").replace(".cs", "")
    domain_tokens = [t for t in base.replace("-", "_").split("_") if t and t not in {"api", "route", "routes", "controller"}]
    if not domain_tokens:
        # Fallback for framework-style package repos where domain tokens are weak.
        active_dir = os.path.dirname(query.active_file).lower()
        candidate_dir = os.path.dirname(candidate_path).lower()
        if active_dir and candidate_dir:
            active_root = active_dir.split("/")[0]
            cand_root = candidate_dir.split("/")[0]
            if active_dir == candidate_dir:
                return ScoreComponent(
                    factor="Module Affinity",
                    points=14.0,
                    reason="Candidate shares exact module directory with active file"
                )
            if active_root and active_root == cand_root:
                return ScoreComponent(
                    factor="Module Affinity",
                    points=9.0,
                    reason="Candidate shares top-level package neighborhood"
                )
        return None

    strong_tokens = [t for t in domain_tokens if len(t) > 3]
    if not strong_tokens:
        return None

    if any(tok in candidate_path for tok in strong_tokens):
        return ScoreComponent(
            factor="Active File Affinity",
            points=18.0,
            reason="Candidate path shares domain token with active file"
        )

    # Mild demotion for sibling layer files that do not match active domain token.
    if query.mode != "refactor" and any(seg in candidate_path for seg in ["service", "repository", "controller", "route"]):
        return ScoreComponent(
            factor="Domain Mismatch",
            points=-8.0,
            reason="Sibling layer candidate does not share active-file domain token"
        )

    return None

def score_framework_feature_intent(query: RetrievalQuery, candidate: FileMetadata, index: IndexManager) -> Optional[ScoreComponent]:
    """
    Framework-aware feature scorer for real repositories (FastAPI/Flask style structures).
    """
    if query.mode != "feature":
        return None

    terms = set(_normalized_query_terms(query.task))
    path = candidate.rel_path.lower()
    active_path = (query.active_file or "").lower()
    if not _is_framework_context(active_path, path):
        return None
    score = 0.0
    reasons: List[str] = []

    if any(term in terms for term in {"route", "router", "routing"}):
        if any(seg in path for seg in ["routing.py", "applications.py", "blueprints.py", "sansio/scaffold.py"]):
            score += 22.0
            reasons.append("routing/blueprint intent matched")
    if any(term in terms for term in {"response", "responses"}):
        if any(seg in path for seg in ["responses.py", "encoders.py", "wrappers.py", "helpers.py"]):
            score += 20.0
            reasons.append("response handling intent matched")
    if any(term in terms for term in {"schema", "openapi", "param", "params", "parameter"}):
        if any(seg in path for seg in ["openapi/utils.py", "params.py", "param_functions.py", "json/provider.py", "json/tag.py"]):
            score += 24.0
            reasons.append("schema/params intent matched")
    if any(term in terms for term in {"context", "request"}):
        if any(seg in path for seg in ["ctx.py", "globals.py", "app.py"]):
            score += 16.0
            reasons.append("context lifecycle intent matched")

    candidate_path_lower = candidate.rel_path.lower()
    # Avoid over-weighting Android layout XML by action-like view IDs (e.g. saveButton) at file-level intent.
    if "/res/layout/" in candidate_path_lower and candidate_path_lower.endswith(".xml"):
        symbols = []
    else:
        symbols = index.get_symbols_for_file(candidate.rel_path)
    for sym in symbols:
        sname = sym.name.lower()
        if any(term in sname for term in ["route", "router", "openapi", "schema", "param", "response", "blueprint", "context"]):
            score += 7.0
            reasons.append(f"symbol '{sym.name}' aligns with intent")
            break

    if score == 0.0:
        return None

    return ScoreComponent(
        factor="Framework Feature Intent",
        points=score,
        reason="; ".join(reasons)
    )

def score_docs_intent(query: RetrievalQuery, candidate: FileMetadata, index: IndexManager) -> Optional[ScoreComponent]:
    """
    Prioritizes service-doc generation paths for documentation-oriented tasks.
    """
    task_lower = query.task.lower()
    if query.mode != "architecture" and not any(word in task_lower for word in {"doc", "docs", "document", "documentation"}):
        return None

    path_lower = candidate.rel_path.lower()
    score = 0.0
    reasons: List[str] = []

    if "doc" in path_lower or "readme" in path_lower:
        score += 18.0
        reasons.append("documentation path")
    if "service" in path_lower:
        score += 8.0
        reasons.append("service-layer context")
    if "client" in path_lower and query.mode == "architecture":
        score -= 10.0
        reasons.append("client-layer deprioritized for system docs")

    symbols = index.get_symbols_for_file(candidate.rel_path)
    for sym in symbols:
        name = sym.name.lower()
        if any(k in name for k in ["doc", "render", "template", "summary", "generate"]):
            score += 10.0
            reasons.append(f"symbol '{sym.name}' indicates docs generation")
            break

    if score == 0:
        return None

    return ScoreComponent(
        factor="Docs Intent",
        points=score,
        reason="; ".join(reasons)
    )

def score_refactor_targets(query: RetrievalQuery, candidate: FileMetadata, index: IndexManager) -> Optional[ScoreComponent]:
    """
    Refactor-specific scorer that prefers validation/adapter/transform paths and symbols,
    while penalizing unrelated domain siblings.
    """
    if query.mode != "refactor" and "extract" not in query.task.lower():
        return None

    path_lower = candidate.rel_path.lower()
    score = 0.0
    reasons: List[str] = []

    strong_path_terms = ["validator", "validation", "adapter", "mapper", "transform", "normaliz", "helper", "util"]
    if any(term in path_lower for term in strong_path_terms):
        score += 26.0
        reasons.append("refactor-oriented path pattern")

    symbols = index.get_symbols_for_file(candidate.rel_path)
    strong_symbol_terms = ["validate", "normaliz", "map", "adapt", "transform", "extract", "helper"]
    for sym in symbols:
        s_name = sym.name.lower()
        if any(term in s_name for term in strong_symbol_terms):
            score += 20.0
            reasons.append(f"symbol '{sym.name}' matches refactor intent")
            break

    domain_tokens = _active_domain_tokens(query.active_file)
    if domain_tokens:
        if any(tok in path_lower for tok in domain_tokens):
            score += 12.0
            reasons.append("same-domain refactor candidate")
        elif any(seg in path_lower for seg in ["service", "repository", "controller"]):
            score -= 16.0
            reasons.append("generic sibling layer outside active domain")

    task_lower = query.task.lower()
    query_terms = set(_normalized_query_terms(query.task))
    if ("extract" in task_lower or "shared" in task_lower) and any(term in path_lower for term in ["builder", "template"]):
        score += 18.0
        reasons.append("abstraction builder/template target for extraction task")

    # Extra dampening for generic service collisions common in Java/C#
    base = os.path.basename(path_lower)
    if base.endswith("service.java") or base.endswith("service.cs"):
        if not any(tok in path_lower for tok in domain_tokens):
            score -= 10.0
            reasons.append("generic service collision penalty")
    if "validationutils" in base and domain_tokens and not any(tok in path_lower for tok in domain_tokens):
        score -= 14.0
        reasons.append("global validation utility deprioritized for domain-focused refactor")

    # Android-heavy refactors often encode a concrete domain (timer/alarm/receiver/etc).
    # Penalize generic helper/database targets that do not align with those domain terms.
    if _is_android_path(query.active_file) or _is_android_path(candidate.rel_path):
        generic_refactor_terms = {
            "refactor", "reusable", "shared", "helper", "remove", "duplicated",
            "code", "logic", "into", "scheduling", "schedule",
        }
        domain_terms = [
            term for term in query_terms
            if len(term) > 4 and term not in generic_refactor_terms
        ]
        if domain_terms:
            if not any(term in path_lower for term in domain_terms):
                if any(token in path_lower for token in ["database", "helper", "manager", "util", "adapter"]):
                    score -= 18.0
                    reasons.append("generic utility target without task-domain token alignment")
        if "database" in path_lower and "database" not in task_lower and "storage" not in task_lower:
            score -= 14.0
            reasons.append("database target deprioritized for non-storage refactor intent")

    if score == 0:
        return None

    return ScoreComponent(
        factor="Refactor Targeting",
        points=score,
        reason="; ".join(reasons)
    )

def score_framework_artifacts(query: RetrievalQuery, candidate: FileMetadata, index: IndexManager) -> Optional[ScoreComponent]:
    artifacts = index.get_artifacts_for_file(candidate.rel_path)
    if not artifacts:
        return None
        
    task_lower = query.task.lower()
    query_terms = set(_normalized_query_terms(query.task))
    
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

def score_domain_signal_balance(query: RetrievalQuery, candidate: FileMetadata, index: IndexManager) -> Optional[ScoreComponent]:
    """
    Reduces cross-domain noise for bugfix/feature and lightly boosts direct dependency links.
    """
    if query.mode not in {"bugfix", "feature"} or not query.active_file:
        return None

    candidate_path = candidate.rel_path.lower()
    domain_tokens = _active_domain_tokens(query.active_file)
    same_domain = any(tok in candidate_path for tok in domain_tokens) if domain_tokens else False

    has_runtime = False
    has_call_chain = False
    has_dependency = False
    for comp in [score_dependencies(query, candidate, index)]:
        if not comp:
            continue
        if comp.factor in {"Call Chain"}:
            has_call_chain = True
        if comp.factor in {"Direct Dependency", "Reverse Dependency"}:
            has_dependency = True
    has_signal = has_call_chain or has_dependency or has_runtime

    if any(seg in candidate_path for seg in ["service", "repository"]) and not same_domain and not has_signal:
        return ScoreComponent(
            factor="Cross-Domain Noise Penalty",
            points=-6.0,
            reason="Cross-domain sibling service/repository without dependency/runtime signal"
        )

    if has_signal and not same_domain:
        return ScoreComponent(
            factor="Direct Signal Boost",
            points=5.0,
            reason="Direct dependency/call signal present despite weak domain token match"
        )

    return None


def score_android_scope_alignment(query: RetrievalQuery, candidate: FileMetadata, index: IndexManager) -> Optional[ScoreComponent]:
    if not query.active_file:
        return None
    if not _is_android_path(query.active_file) and not _is_android_path(candidate.rel_path):
        return None
    if query.mode not in {"bugfix", "refactor"}:
        return None

    active_artifacts = index.get_artifacts_for_file(query.active_file)
    candidate_artifacts = index.get_artifacts_for_file(candidate.rel_path)
    active_layouts = {artifact.name for artifact in active_artifacts if artifact.artifact_type == "ANDROID_LAYOUT_LINK"}
    candidate_layouts = {artifact.name for artifact in candidate_artifacts if artifact.artifact_type == "ANDROID_LAYOUT"}

    if active_layouts and candidate_layouts:
        if active_layouts.intersection(candidate_layouts):
            layout_name = sorted(active_layouts.intersection(candidate_layouts))[0]
            return ScoreComponent(
                factor="Android Scope Alignment",
                points=14.0,
                reason=f"Candidate layout '{layout_name}' is directly referenced by active component",
            )
        return ScoreComponent(
            factor="Android Scope Alignment",
            points=-12.0,
            reason="Layout belongs to a different screen than the active component scope",
        )

    active_base = os.path.basename(query.active_file).lower()
    candidate_base = os.path.basename(candidate.rel_path).lower()
    active_tokens = {
        token for token in _path_tokens(active_base)
        if token and token not in {"activity", "fragment", "java", "kt", "xml"}
    }
    candidate_tokens = set(_path_tokens(candidate_base))
    shared = sorted(active_tokens.intersection(candidate_tokens))
    if shared:
        return ScoreComponent(
            factor="Android Scope Alignment",
            points=8.0,
            reason=f"Candidate shares active component domain token(s): {', '.join(shared[:3])}",
        )

    lower_path = candidate.rel_path.lower()
    if any(token in lower_path for token in ["database", "helper", "manager", "util"]):
        dependency_signal = score_dependencies(query, candidate, index)
        if dependency_signal is None:
            return ScoreComponent(
                factor="Android Scope Alignment",
                points=-8.0,
                reason="Generic helper/database candidate outside active Android screen scope",
            )
    return None


def score_android_module_locality(query: RetrievalQuery, candidate: FileMetadata) -> Optional[ScoreComponent]:
    if not _is_android_path(query.active_file) and not _is_android_path(candidate.rel_path):
        return None
    if not query.active_file:
        return None

    active_module = _android_module_key(query.active_file)
    candidate_module = _android_module_key(candidate.rel_path)
    if not active_module or not candidate_module:
        return None

    if active_module == candidate_module and query.active_file != candidate.rel_path:
        return ScoreComponent(
            factor="Android Module Locality",
            points=16.0,
            reason=f"Candidate shares Android module '{active_module}' with active file",
        )
    return None


def score_android_manifest_layout_proximity(query: RetrievalQuery, candidate: FileMetadata) -> Optional[ScoreComponent]:
    if not query.active_file:
        return None
    if not _is_android_path(query.active_file) and not _is_android_path(candidate.rel_path):
        return None

    active = query.active_file.lower()
    cand = candidate.rel_path.lower()
    active_is_manifest = active.endswith("androidmanifest.xml")
    active_is_layout = "/res/layout/" in active and active.endswith(".xml")
    cand_is_manifest = cand.endswith("androidmanifest.xml")
    cand_is_layout = "/res/layout/" in cand and cand.endswith(".xml")

    if (active_is_manifest and cand_is_layout) or (active_is_layout and cand_is_manifest):
        return ScoreComponent(
            factor="Android Manifest/Layout Proximity",
            points=12.0,
            reason="Manifest and layout files are often coupled in Android context assembly",
        )
    return None


def score_android_resource_bridge(query: RetrievalQuery, candidate: FileMetadata, index: IndexManager) -> Optional[ScoreComponent]:
    if not query.active_file:
        return None
    if not _is_android_path(query.active_file) and not _is_android_path(candidate.rel_path):
        return None

    active_artifacts = index.get_artifacts_for_file(query.active_file)
    candidate_artifacts = index.get_artifacts_for_file(candidate.rel_path)
    if not active_artifacts or not candidate_artifacts:
        return None

    active_layout_links = {artifact.name for artifact in active_artifacts if artifact.artifact_type == "ANDROID_LAYOUT_LINK"}
    candidate_layouts = {artifact.name for artifact in candidate_artifacts if artifact.artifact_type == "ANDROID_LAYOUT"}
    if active_layout_links and candidate_layouts and active_layout_links.intersection(candidate_layouts):
        layout_name = sorted(active_layout_links.intersection(candidate_layouts))[0]
        return ScoreComponent(
            factor="Android Resource Bridge",
            points=22.0,
            reason=f"Source references layout '{layout_name}' defined in candidate file",
        )

    active_ids = {artifact.name for artifact in active_artifacts if artifact.artifact_type == "ANDROID_VIEW_ID_USAGE"}
    candidate_ids = {artifact.name for artifact in candidate_artifacts if artifact.artifact_type == "ANDROID_VIEW_ID"}
    if active_ids and candidate_ids and active_ids.intersection(candidate_ids):
        element_id = sorted(active_ids.intersection(candidate_ids))[0]
        return ScoreComponent(
            factor="Android Resource Bridge",
            points=14.0,
            reason=f"Source references view id '{element_id}' declared in candidate layout",
        )
    return None


def score_android_contextual_signals(
    query: RetrievalQuery,
    candidate: FileMetadata,
    index: IndexManager,
    runtime: Optional[RuntimeAnalyzer] = None,
    android_context: Optional[dict] = None,
) -> List[ScoreComponent]:
    if not android_context:
        return []
    if not android_context.get("enabled") or not android_context.get("is_android_project"):
        return []

    components: List[ScoreComponent] = []
    active_file = query.active_file or ""
    candidate_path = candidate.rel_path

    active_module = android_context.get("active_module")
    if active_module:
        cand_module = _android_module_key(candidate_path)
        if cand_module == active_module and candidate_path != active_file:
            components.append(
                ScoreComponent(
                    factor="Android Retrieval Context",
                    points=8.0,
                    reason=f"Context module match: '{active_module}'",
                )
            )

    related_layouts = set(android_context.get("related_layouts", []))
    candidate_artifacts = index.get_artifacts_for_file(candidate_path)
    candidate_layouts = {a.name for a in candidate_artifacts if a.artifact_type == "ANDROID_LAYOUT"}
    if related_layouts and candidate_layouts and related_layouts.intersection(candidate_layouts):
        layout_name = sorted(related_layouts.intersection(candidate_layouts))[0]
        components.append(
            ScoreComponent(
                factor="Android Retrieval Context",
                points=12.0,
                reason=f"Layout bridge from retrieval context: '{layout_name}'",
            )
        )

    related_resources = set(android_context.get("related_resources", []))
    candidate_view_ids = {a.name for a in candidate_artifacts if a.artifact_type == "ANDROID_VIEW_ID"}
    if related_resources and candidate_view_ids and related_resources.intersection(candidate_view_ids):
        view_id = sorted(related_resources.intersection(candidate_view_ids))[0]
        components.append(
            ScoreComponent(
                factor="Android Retrieval Context",
                points=10.0,
                reason=f"Resource bridge from retrieval context: '{view_id}'",
            )
        )

    task_lower = (query.task or "").lower()
    lifecycle_terms = ["activity", "fragment", "service", "receiver", "provider"]
    if any(term in task_lower for term in lifecycle_terms):
        lifecycle_match = any(term in candidate_path.lower() for term in lifecycle_terms)
        if lifecycle_match:
            components.append(
                ScoreComponent(
                    factor="Android Retrieval Context",
                    points=6.0,
                    reason="Lifecycle keyword alignment between task and candidate path",
                )
            )

    runtime_tags = set(android_context.get("runtime_tags", []))
    if runtime_tags and runtime:
        runtime_match = score_android_runtime_match(query, candidate, runtime)
        if runtime_match:
            components.append(runtime_match)
        elif any(tag in {"aapt_resource_linking_failure", "manifest_merge_failure"} for tag in runtime_tags):
            if candidate_path.lower().endswith("androidmanifest.xml") or "/res/layout/" in candidate_path.lower():
                components.append(
                    ScoreComponent(
                        factor="Android Runtime Match",
                        points=7.0,
                        reason="Runtime context indicates manifest/resource issue",
                    )
                )

    integration_file_hints = {
        str(item).replace("\\", "/")
        for item in android_context.get("integration_file_hints", [])
        if item
    }
    if integration_file_hints:
        for hint in sorted(integration_file_hints):
            if hint in candidate_path or candidate_path.endswith(hint):
                components.append(
                    ScoreComponent(
                        factor="Android Integration Hint",
                        points=9.0,
                        reason=f"Optional integration signal maps to candidate file '{hint}'",
                    )
                )
                break

    integration_module_hints = {str(item) for item in android_context.get("integration_module_hints", []) if item}
    if integration_module_hints:
        cand_module = _android_module_key(candidate_path)
        if cand_module and cand_module in integration_module_hints:
            components.append(
                ScoreComponent(
                    factor="Android Integration Hint",
                    points=6.0,
                    reason=f"Optional integration signal maps to module '{cand_module}'",
                )
            )

    integration_tags = set(android_context.get("integration_tags", []))
    if integration_tags and any(tag.startswith("ci_") for tag in integration_tags):
        if candidate_path.lower().endswith("build.gradle") or candidate_path.lower().endswith("build.gradle.kts"):
            components.append(
                ScoreComponent(
                    factor="Android Integration Hint",
                    points=5.0,
                    reason="CI integration signals prioritize Gradle configuration paths",
                )
            )

    # Cap Android contextual bonus contribution
    total = 0.0
    capped: List[ScoreComponent] = []
    for component in sorted(components, key=lambda item: (-item.points, item.reason)):
        if total >= 24.0:
            break
        remaining = 24.0 - total
        points = min(component.points, remaining)
        capped.append(
            ScoreComponent(
                factor=component.factor,
                points=points,
                reason=component.reason,
                path=component.path,
            )
        )
        total += points
    return capped


def score_android_runtime_match(
    query: RetrievalQuery,
    candidate: FileMetadata,
    runtime: RuntimeAnalyzer,
) -> Optional[ScoreComponent]:
    candidate_path = candidate.rel_path.replace("\\", "/")
    candidate_module = _android_module_key(candidate_path)

    for signal in runtime.get_android_runtime_signals():
        signal_file = (signal.file or "").replace("\\", "/")
        if signal_file and (signal_file in candidate_path or candidate_path.endswith(signal_file)):
            return ScoreComponent(
                factor="Android Runtime Match",
                points=18.0 if signal.confidence == "high" else 12.0,
                reason=f"Runtime signal maps to file '{signal.file}' ({signal.category})",
            )
        if signal.module and candidate_module and signal.module == candidate_module:
            return ScoreComponent(
                factor="Android Runtime Match",
                points=10.0 if signal.confidence == "high" else 7.0,
                reason=f"Runtime signal maps to module '{signal.module}' ({signal.category})",
            )

    for failure in runtime.get_android_failure_contexts():
        if candidate_module and candidate_module in failure.implicated_modules:
            return ScoreComponent(
                factor="Android Runtime Match",
                points=8.0,
                reason=f"Failure context implicates module '{candidate_module}' ({failure.failure_kind})",
            )
    return None


