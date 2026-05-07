import re
from typing import List, Set
from ..base import LanguageAdapter
from ...models.symbol import Symbol, DependencyEdge

class TOMLAdapter(LanguageAdapter):
    def get_supported_extensions(self) -> Set[str]:
        return {".toml"}

    def can_handle(self, rel_path: str) -> bool:
        return rel_path.lower().endswith(".toml")

    def extract_symbols(self, content: str, file_path: str) -> List[Symbol]:
        symbols = []
        lines = content.splitlines()
        
        # Section pattern: [section] or [section.subset]
        section_pattern = re.compile(r'^\s*\[+([\w\.-]+)\]+')

        for i, line in enumerate(lines):
            line_num = i + 1
            match = section_pattern.match(line)
            if match:
                symbols.append(Symbol(
                    name=match.group(1),
                    type="toml_section",
                    start_line=line_num,
                    end_line=line_num
                ))

        return symbols

    def extract_dependencies(self, content: str, file_path: str) -> List[DependencyEdge]:
        edges = []
        # Common dependencies in TOML (e.g. pyproject.toml, Cargo.toml)
        # Note: robust TOML parsing with regex is hard, but we can catch key = { ... } or key = "..."
        dep_pattern = re.compile(r'^(\w+)\s*=\s*(?:["\']|\{)')
        
        lines = content.splitlines()
        current_section = ""
        
        for i, line in enumerate(lines):
            sec_match = re.match(r'^\s*\[+([\w\.-]+)\]+', line)
            if sec_match:
                current_section = sec_match.group(1)
                continue
                
            if "dependencies" in current_section or "dev-dependencies" in current_section:
                dep_match = dep_pattern.match(line)
                if dep_match:
                    edges.append(DependencyEdge(
                        source_id=file_path,
                        target_id=dep_match.group(1),
                        type="external_dep"
                    ))

        return edges
