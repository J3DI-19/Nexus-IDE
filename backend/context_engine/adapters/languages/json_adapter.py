import re
import json
from typing import List, Set
from ..base import LanguageAdapter
from ...models.symbol import Symbol, DependencyEdge

class JSONAdapter(LanguageAdapter):
    def get_supported_extensions(self) -> Set[str]:
        return {".json"}

    def can_handle(self, rel_path: str) -> bool:
        return rel_path.lower().endswith(".json")

    def extract_symbols(self, content: str, file_path: str) -> List[Symbol]:
        symbols = []
        try:
            data = json.loads(content)
            # Extract high-level keys as symbols
            for key in data.keys():
                symbols.append(Symbol(
                    name=key,
                    type="config_section",
                    start_line=1, # JSON parsing doesn't easily give line numbers per key
                    end_line=1
                ))
            
            # Special handling for package.json
            if file_path.endswith("package.json"):
                if "name" in data:
                    symbols.append(Symbol(
                        name=data["name"],
                        type="project_name",
                        start_line=1,
                        end_line=1
                    ))
        except Exception:
            pass
        return symbols

    def extract_dependencies(self, content: str, file_path: str) -> List[DependencyEdge]:
        edges = []
        try:
            data = json.loads(content)
            
            # Extract dependencies (package.json style)
            for dep_type in ["dependencies", "devDependencies", "peerDependencies"]:
                if dep_type in data:
                    for pkg in data[dep_type].keys():
                        edges.append(DependencyEdge(
                            source_id=file_path,
                            target_id=pkg,
                            type="external_dep"
                        ))
            
            # Extract scripts
            if "scripts" in data:
                for script in data["scripts"].keys():
                    edges.append(DependencyEdge(
                        source_id=file_path,
                        target_id=script,
                        type="build_script"
                    ))
        except Exception:
            pass
        return edges
