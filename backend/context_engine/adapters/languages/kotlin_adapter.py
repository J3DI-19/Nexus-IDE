import re
from typing import List, Set, Dict, Optional
from ..base import LanguageAdapter
from ...models.symbol import Symbol, DependencyEdge

class KotlinAdapter(LanguageAdapter):
    def get_supported_extensions(self) -> Set[str]:
        return {".kt", ".kts"}

    def can_handle(self, rel_path: str) -> bool:
        ext = rel_path.lower()
        return ext.endswith(".kt") or ext.endswith(".kts")

    def extract_symbols(self, content: str, file_path: str) -> List[Symbol]:
        symbols = []
        lines = content.splitlines()
        
        # Regex patterns for Kotlin
        class_pattern = re.compile(r'(?:open|abstract|sealed|data\s+)?class\s+(\w+)')
        object_pattern = re.compile(r'(?:companion\s+)?object\s+(\w+)?')
        interface_pattern = re.compile(r'interface\s+(\w+)')
        function_pattern = re.compile(r'(?:suspend\s+)?fun\s+(\w+)')

        current_container = None
        
        for i, line in enumerate(lines):
            line_num = i + 1
            
            # Class detection
            class_match = class_pattern.search(line)
            if class_match:
                current_container = class_match.group(1)
                symbols.append(Symbol(
                    name=current_container,
                    type="class",
                    start_line=line_num,
                    end_line=line_num
                ))
                continue

            # Object detection
            obj_match = object_pattern.search(line)
            if obj_match:
                name = obj_match.group(1) or "Companion"
                symbols.append(Symbol(
                    name=name,
                    type="object",
                    start_line=line_num,
                    end_line=line_num
                ))
                continue

            # Interface detection
            interface_match = interface_pattern.search(line)
            if interface_match:
                symbols.append(Symbol(
                    name=interface_match.group(1),
                    type="interface",
                    start_line=line_num,
                    end_line=line_num
                ))
                continue

            # Function detection
            func_match = function_pattern.search(line)
            if func_match:
                name = func_match.group(1)
                symbols.append(Symbol(
                    name=name,
                    type="function",
                    start_line=line_num,
                    end_line=line_num,
                    parent_id=current_container if current_container else None
                ))

        return symbols

    def extract_dependencies(self, content: str, file_path: str) -> List[DependencyEdge]:
        edges = []
        lines = content.splitlines()

        # Import patterns
        import_pattern = re.compile(r'import\s+([\w\.]+)')
        
        # Inheritance
        extends_pattern = re.compile(r'class\s+(\w+)\s*(?::\s*([\w\.\(\)]+))?')

        # Calls
        call_pattern = re.compile(r'(\w+)\s*[\(\{]')

        current_symbol = None

        for i, line in enumerate(lines):
            line_num = i + 1
            
            # Imports
            import_match = import_pattern.search(line)
            if import_match:
                edges.append(DependencyEdge(
                    source_id=file_path,
                    target_id=import_match.group(1),
                    type="import"
                ))

            # Inheritance
            extends_match = extends_pattern.search(line)
            if extends_match and extends_match.group(2):
                base = extends_match.group(2).split('(')[0].strip()
                edges.append(DependencyEdge(
                    source_id=f"{file_path}:{extends_match.group(1)}",
                    target_id=base,
                    type="inheritance"
                ))

            # Calls
            if 'class' in line or 'fun' in line:
                match = re.search(r'(?:class|fun|object|interface)\s+(\w+)', line)
                if match:
                    current_symbol = match.group(1)
            
            if current_symbol:
                calls = call_pattern.findall(line)
                for call in calls:
                    if call not in {"if", "for", "while", "when", "catch", "super", "this", "fun", "return", current_symbol}:
                        edges.append(DependencyEdge(
                            source_id=f"{file_path}:{current_symbol}",
                            target_id=call,
                            type="call",
                            metadata={"line": str(line_num)}
                        ))

        return edges
