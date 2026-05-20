import re
from typing import List, Set, Dict, Optional
from ..base import LanguageAdapter
from ...models.symbol import Symbol, DependencyEdge

class JavaAdapter(LanguageAdapter):
    def get_supported_extensions(self) -> Set[str]:
        return {".java"}

    def can_handle(self, rel_path: str) -> bool:
        return rel_path.lower().endswith(".java")

    def extract_symbols(self, content: str, file_path: str) -> List[Symbol]:
        symbols = []
        lines = content.splitlines()
        
        # Regex patterns for Java
        class_pattern = re.compile(r'(?:public|protected|private|static\s+)?(?:abstract\s+)?class\s+(\w+)')
        interface_pattern = re.compile(r'(?:public|protected|private|static\s+)?interface\s+(\w+)')
        method_pattern = re.compile(
            r'^\s*(?:public|protected|private)?\s*(?:static\s+)?(?:final\s+)?(?:synchronized\s+)?'
            r'(?:[\w<>\[\],?]+\s+)+(\w+)\s*\([^;]*\)\s*(?:throws\s+[\w\.,\s]+)?\s*(?:\{)?\s*$'
        )
        constructor_pattern = re.compile(
            r'^\s*(?:public|protected|private)\s+(\w+)\s*\([^;]*\)\s*(?:throws\s+[\w\.,\s]+)?\s*(?:\{)?\s*$'
        )
        annotation_pattern = re.compile(r'@(\w+)(?:\(.*?\))?')

        current_class = None
        
        for i, line in enumerate(lines):
            line_num = i + 1
            
            # Class detection
            class_match = class_pattern.search(line)
            if class_match:
                current_class = class_match.group(1)
                end_line = self._find_block_end(lines, i) if "{" in line else line_num
                symbols.append(Symbol(
                    name=current_class,
                    type="class",
                    start_line=line_num,
                    end_line=end_line
                ))
                continue

            # Interface detection
            interface_match = interface_pattern.search(line)
            if interface_match:
                end_line = self._find_block_end(lines, i) if "{" in line else line_num
                symbols.append(Symbol(
                    name=interface_match.group(1),
                    type="interface",
                    start_line=line_num,
                    end_line=end_line
                ))
                continue

            # Method detection
            method_match = method_pattern.search(line)
            constructor_match = constructor_pattern.search(line)
            if method_match or constructor_match:
                name = (method_match or constructor_match).group(1)
                if name not in {"if", "for", "while", "switch", "catch", "new", "return"}:
                    end_line = self._find_block_end(lines, i)
                    symbols.append(Symbol(
                        name=name,
                        type="method",
                        start_line=line_num,
                        end_line=end_line,
                        parent_id=current_class
                    ))
            
            # Annotation detection (as metadata or symbols)
            # For simplicity, we just note them if they are on their own line
            anno_match = annotation_pattern.search(line)
            if anno_match:
                symbols.append(Symbol(
                    name=anno_match.group(1),
                    type="annotation",
                    start_line=line_num,
                    end_line=line_num
                ))

        return symbols

    def _find_block_end(self, lines: List[str], start_idx: int) -> int:
        """
        Finds the closing brace line for a Java block starting at start_idx.
        Best-effort deterministic parser with lightweight comment/string stripping.
        """
        brace_count = 0
        found_open = False
        for i in range(start_idx, len(lines)):
            line = lines[i]
            clean = re.sub(r'//.*', '', line)
            clean = re.sub(r'"[^"\\\\]*(?:\\\\.[^"\\\\]*)*"', '""', clean)
            clean = re.sub(r"'[^'\\\\]*(?:\\\\.[^'\\\\]*)*'", "''", clean)
            opens = clean.count('{')
            closes = clean.count('}')
            if opens > 0:
                found_open = True
            brace_count += opens
            brace_count -= closes
            if found_open and brace_count <= 0:
                return i + 1
        return start_idx + 1

    def extract_dependencies(self, content: str, file_path: str) -> List[DependencyEdge]:
        edges = []
        lines = content.splitlines()

        # Import patterns
        import_pattern = re.compile(r'import\s+([\w\.]+);')
        
        # Inheritance
        extends_pattern = re.compile(r'class\s+(\w+)\s+extends\s+([\w\.]+)')
        implements_pattern = re.compile(r'class\s+(\w+)\s+implements\s+([\w\s\.,]+)')

        # Calls
        call_pattern = re.compile(r'(\w+)\s*\(')

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
            if extends_match:
                edges.append(DependencyEdge(
                    source_id=f"{file_path}:{extends_match.group(1)}",
                    target_id=extends_match.group(2),
                    type="inheritance"
                ))

            # Calls
            if 'class' in line or '(' in line:
                match = re.search(r'(?:class|interface)\s+(\w+)', line)
                if match:
                    current_symbol = match.group(1)
                else:
                    method_match = re.search(r'\s+(\w+)\s*\(', line)
                    if method_match:
                        current_symbol = method_match.group(1)
            
            if current_symbol:
                calls = call_pattern.findall(line)
                for call in calls:
                    if call not in {"if", "for", "while", "switch", "catch", "super", "this", "new", "return", current_symbol}:
                        edges.append(DependencyEdge(
                            source_id=f"{file_path}:{current_symbol}",
                            target_id=call,
                            type="call",
                            metadata={"line": str(line_num)}
                        ))

        return edges
