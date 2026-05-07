import re
from typing import List, Set
from ..base import LanguageAdapter
from ...models.symbol import Symbol, DependencyEdge

class XMLAdapter(LanguageAdapter):
    def get_supported_extensions(self) -> Set[str]:
        return {".xml"}

    def can_handle(self, rel_path: str) -> bool:
        return rel_path.lower().endswith(".xml")

    def extract_symbols(self, content: str, file_path: str) -> List[Symbol]:
        symbols = []
        lines = content.splitlines()
        
        # Patterns for Android/XML structural elements
        id_pattern = re.compile(r'android:id=["\']@\+id/(\w+)["\']')
        tag_pattern = re.compile(r'<([\w\.]+)')
        
        # Android Manifest patterns
        activity_pattern = re.compile(r'<activity.*?android:name=["\']([\w\.]+)["\']')
        permission_pattern = re.compile(r'<uses-permission.*?android:name=["\']([\w\.]+)["\']')

        for i, line in enumerate(lines):
            line_num = i + 1
            
            # Extract View IDs
            ids = id_pattern.findall(line)
            for id_val in ids:
                symbols.append(Symbol(
                    name=f"@id/{id_val}",
                    type="android_id",
                    start_line=line_num,
                    end_line=line_num
                ))

            # Extract Activities/Permissions in Manifest
            activity_match = activity_pattern.search(line)
            if activity_match:
                symbols.append(Symbol(
                    name=activity_match.group(1),
                    type="activity",
                    start_line=line_num,
                    end_line=line_num
                ))
            
            perm_match = permission_pattern.search(line)
            if perm_match:
                symbols.append(Symbol(
                    name=perm_match.group(1).split('.')[-1],
                    type="permission",
                    start_line=line_num,
                    end_line=line_num
                ))

            # Extract major structural tags
            tag_match = tag_pattern.search(line)
            if tag_match:
                tag_name = tag_match.group(1)
                if tag_name in {"LinearLayout", "RelativeLayout", "ConstraintLayout", "FrameLayout", "manifest", "application"}:
                    symbols.append(Symbol(
                        name=f"<{tag_name}>",
                        type="layout_root",
                        start_line=line_num,
                        end_line=line_num
                    ))

        return symbols

    def extract_dependencies(self, content: str, file_path: str) -> List[DependencyEdge]:
        edges = []
        lines = content.splitlines()

        # Layout includes
        include_pattern = re.compile(r'layout=["\']@layout/(\w+)["\']')
        # Context (links XML to Java/Kotlin class)
        context_pattern = re.compile(r'tools:context=["\']([\w\.]+)["\']')

        for i, line in enumerate(lines):
            line_num = i + 1
            
            # Layout includes
            include_match = include_pattern.search(line)
            if include_match:
                edges.append(DependencyEdge(
                    source_id=file_path,
                    target_id=f"layout/{include_match.group(1)}",
                    type="layout_include"
                ))

            # Context links
            context_match = context_pattern.search(line)
            if context_match:
                edges.append(DependencyEdge(
                    source_id=file_path,
                    target_id=context_match.group(1),
                    type="ui_context_link"
                ))
                
        return edges
