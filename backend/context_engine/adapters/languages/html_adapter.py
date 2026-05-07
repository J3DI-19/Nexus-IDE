import re
from typing import List, Set
from ..base import LanguageAdapter
from ...models.symbol import Symbol, DependencyEdge

class HTMLAdapter(LanguageAdapter):
    def get_supported_extensions(self) -> Set[str]:
        return {".html", ".htm"}

    def can_handle(self, rel_path: str) -> bool:
        ext = rel_path.lower()
        return ext.endswith(".html") or ext.endswith(".htm")

    def extract_symbols(self, content: str, file_path: str) -> List[Symbol]:
        symbols = []
        lines = content.splitlines()
        
        # Patterns for HTML structural elements
        id_pattern = re.compile(r'id=["\'](\w+)["\']')
        class_pattern = re.compile(r'class=["\']([\w\s-]+)["\']')
        tag_pattern = re.compile(r'<(\w+)')

        for i, line in enumerate(lines):
            line_num = i + 1
            
            # Extract IDs as symbols
            ids = id_pattern.findall(line)
            for id_val in ids:
                symbols.append(Symbol(
                    name=f"#{id_val}",
                    type="id",
                    start_line=line_num,
                    end_line=line_num
                ))

            # Extract major tags as structural symbols (e.g. main, nav, section, div if it has an id)
            tag_match = tag_pattern.search(line)
            if tag_match:
                tag_name = tag_match.group(1)
                if tag_name in {"main", "nav", "section", "article", "header", "footer", "form"}:
                    symbols.append(Symbol(
                        name=f"<{tag_name}>",
                        type="tag",
                        start_line=line_num,
                        end_line=line_num
                    ))

        return symbols

    def extract_dependencies(self, content: str, file_path: str) -> List[DependencyEdge]:
        edges = []
        lines = content.splitlines()

        # Link and Script patterns
        link_pattern = re.compile(r'<link.*?href=["\'](.*?)["\']')
        script_pattern = re.compile(r'<script.*?src=["\'](.*?)["\']')
        class_pattern = re.compile(r'class=["\']([\w\s-]+)["\']')

        for i, line in enumerate(lines):
            line_num = i + 1
            
            # CSS links
            link_match = link_pattern.search(line)
            if link_match:
                edges.append(DependencyEdge(
                    source_id=file_path,
                    target_id=link_match.group(1),
                    type="style_link"
                ))

            # JS scripts
            script_match = script_pattern.search(line)
            if script_match:
                edges.append(DependencyEdge(
                    source_id=file_path,
                    target_id=script_match.group(1),
                    type="script_link"
                ))
            
            # CSS Class dependencies (helps link to CSS files)
            classes = class_pattern.findall(line)
            for cls_line in classes:
                for cls in cls_line.split():
                    edges.append(DependencyEdge(
                        source_id=file_path,
                        target_id=f".{cls}",
                        type="ui_class_ref"
                    ))

        return edges
