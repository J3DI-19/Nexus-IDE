import re
from typing import List, Set
from ..base import LanguageAdapter
from ...models.symbol import Symbol, DependencyEdge

class YAMLAdapter(LanguageAdapter):
    def get_supported_extensions(self) -> Set[str]:
        return {".yaml", ".yml"}

    def can_handle(self, rel_path: str) -> bool:
        ext = rel_path.lower()
        return ext.endswith(".yaml") or ext.endswith(".yml")

    def extract_symbols(self, content: str, file_path: str) -> List[Symbol]:
        symbols = []
        lines = content.splitlines()
        
        # Regex for YAML keys (top-level or slightly indented)
        key_pattern = re.compile(r'^(\s*)(\w+):')

        for i, line in enumerate(lines):
            line_num = i + 1
            match = key_pattern.match(line)
            if match:
                indent = len(match.group(1))
                # Only track top-level or level-1 keys as symbols to avoid noise
                if indent <= 2:
                    symbols.append(Symbol(
                        name=match.group(2),
                        type="config_key",
                        start_line=line_num,
                        end_line=line_num
                    ))

        return symbols

    def extract_dependencies(self, content: str, file_path: str) -> List[DependencyEdge]:
        edges = []
        # Look for images, services, or imports in YAML (e.g. docker-compose, CI)
        image_pattern = re.compile(r'image:\s*([\w\./:-]+)')
        service_pattern = re.compile(r'service:\s*([\w-]+)')

        lines = content.splitlines()
        for i, line in enumerate(lines):
            img_match = image_pattern.search(line)
            if img_match:
                edges.append(DependencyEdge(
                    source_id=file_path,
                    target_id=img_match.group(1),
                    type="container_image"
                ))
            
            svc_match = service_pattern.search(line)
            if svc_match:
                edges.append(DependencyEdge(
                    source_id=file_path,
                    target_id=svc_match.group(1),
                    type="service_ref"
                ))

        return edges
