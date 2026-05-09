import os
from typing import List, Dict, Optional, Set
from ..models.symbol import DependencyEdge
from .manager import IndexManager

class GraphResolver:
    def __init__(self, index: IndexManager):
        self.index = index

    def resolve_graph(self):
        """
        Orchestrates the resolution of all edges in the index.
        """
        # Pass 1: Resolve Imports (File-to-File)
        self._resolve_imports()
        
        # Pass 2: Resolve Symbol Calls (Symbol-to-Symbol/File)
        self._resolve_symbol_calls()

    def _resolve_imports(self):
        for edge in self.index.edges:
            if edge.type == "import" and not edge.is_resolved and edge.raw_target:
                resolved_path = self._resolve_path(edge.source_id, edge.raw_target)
                if resolved_path:
                    edge.target_id = resolved_path
                    edge.is_resolved = True

    def _resolve_symbol_calls(self):
        # Build a map of file -> resolved imports for faster lookup
        file_imports = {}
        for edge in self.index.edges:
            if edge.type == "import" and edge.is_resolved:
                if edge.source_id not in file_imports:
                    file_imports[edge.source_id] = set()
                file_imports[edge.source_id].add(edge.target_id)

        for edge in self.index.edges:
            if edge.type in {"call", "inheritance"} and not edge.is_resolved and edge.raw_target:
                source_file = edge.source_id.split(':')[0]
                symbol_name = edge.raw_target
                
                # 1. Local Resolution
                local_symbols = self.index.get_symbols_for_file(source_file)
                if any(s.name == symbol_name for s in local_symbols):
                    edge.target_id = f"{source_file}:{symbol_name}"
                    edge.is_resolved = True
                    continue
                
                # 2. Import Resolution
                imports = file_imports.get(source_file, set())
                found = False
                for imp_file in imports:
                    imp_symbols = self.index.get_symbols_for_file(imp_file)
                    if any(s.name == symbol_name for s in imp_symbols):
                        edge.target_id = f"{imp_file}:{symbol_name}"
                        edge.is_resolved = True
                        found = True
                        break
                
                if found: continue
                
                # 3. Global Fallback (Last resort)
                global_file = self.index.get_file_for_symbol(symbol_name)
                if global_file:
                    edge.target_id = f"{global_file}:{symbol_name}"
                    edge.is_resolved = True

    def _resolve_path(self, source_file: str, raw_target: str) -> Optional[str]:
        """
        Resolves a raw import string to a canonical relative path.
        """
        if not raw_target:
            return None
            
        # Handle 'module.symbol'
        target_parts = raw_target.split('.')
        source_dir = os.path.dirname(source_file)
        
        # Build potential candidates
        for i in range(len(target_parts), 0, -1):
            potential_module = "/".join(target_parts[:i])
            
            candidates = []
            # 1. Relative to source
            candidates.append(os.path.join(source_dir, potential_module))
            
            # 2. Absolute from project root (or with varying prefixes)
            candidates.append(potential_module)
            
            # 3. Special case: if source_file starts with a prefix (like 'backend/'), 
            # try stripping it or adding it to target
            if '/' in source_file:
                prefix = source_file.split('/')[0]
                candidates.append(os.path.join(prefix, potential_module))

            # Try extensions
            final_candidates = []
            for cand in candidates:
                final_candidates.append(cand)
                for ext in [".py", ".ts", ".tsx", ".js", ".jsx"]:
                    final_candidates.append(cand + ext)
                    final_candidates.append(os.path.join(cand, "__init__.py"))

            for cand in final_candidates:
                norm_cand = os.path.normpath(cand).replace('\\', '/')
                # Strip leading './' if present
                if norm_cand.startswith('./'): norm_cand = norm_cand[2:]
                
                if norm_cand in self.index.files:
                    return norm_cand
        
        return None
