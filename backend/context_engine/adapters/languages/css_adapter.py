import re
from typing import List, Set
from ..base import LanguageAdapter
from ...models.symbol import Symbol, DependencyEdge

class CSSAdapter(LanguageAdapter):
    def get_supported_extensions(self) -> Set[str]:
        return {".css", ".scss", ".less"}

    def can_handle(self, rel_path: str) -> bool:
        ext = rel_path.lower()
        return ext.endswith(".css") or ext.endswith(".scss") or ext.endswith(".less")

    def extract_symbols(self, content: str, file_path: str) -> List[Symbol]:
        symbols = []
        lines = content.splitlines()
        
        # Patterns for CSS selectors
        class_pattern = re.compile(r'\.([\w-]+)\s*\{')
        id_pattern = re.compile(r'#([\w-]+)\s*\{')
        media_pattern = re.compile(r'@media\s*(.*?)\s*\{')

        for i, line in enumerate(lines):
            line_num = i + 1
            
            # Extract Classes
            classes = class_pattern.findall(line)
            for cls in classes:
                symbols.append(Symbol(
                    name=f".{cls}",
                    type="class",
                    start_line=line_num,
                    end_line=line_num
                ))

            # Extract IDs
            ids = id_pattern.findall(line)
            for id_val in ids:
                symbols.append(Symbol(
                    name=f"#{id_val}",
                    type="id",
                    start_line=line_num,
                    end_line=line_num
                ))

            # Extract Media Queries
            media_match = media_pattern.search(line)
            if media_match:
                symbols.append(Symbol(
                    name=f"@media {media_match.group(1)}",
                    type="media_query",
                    start_line=line_num,
                    end_line=line_num
                ))

        return symbols

    def extract_dependencies(self, content: str, file_path: str) -> List[DependencyEdge]:
        edges = []
        # CSS imports
        import_pattern = re.compile(r'@import\s+["\'](.*?)["\']')
        
        lines = content.splitlines()
        for i, line in enumerate(lines):
            import_match = import_pattern.search(line)
            if import_match:
                edges.append(DependencyEdge(
                    source_id=file_path,
                    target_id=import_match.group(1),
                    type="import"
                ))
                
        return edges
