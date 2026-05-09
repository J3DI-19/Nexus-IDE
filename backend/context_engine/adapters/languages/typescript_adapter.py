import re
from typing import List, Set, Dict, Optional
from ..base import LanguageAdapter
from ...models.symbol import Symbol, DependencyEdge

class TypeScriptAdapter(LanguageAdapter):
    def get_supported_extensions(self) -> Set[str]:
        return {".ts", ".tsx"}

    def can_handle(self, rel_path: str) -> bool:
        ext = rel_path.lower()
        return ext.endswith(".ts") or ext.endswith(".tsx")

    def extract_symbols(self, content: str, file_path: str) -> List[Symbol]:
        symbols = []
        lines = content.splitlines()
        
        # Regex patterns for TS/JS
        class_pattern = re.compile(r'(?:export\s+)?(?:abstract\s+)?class\s+(\w+)')
        interface_pattern = re.compile(r'(?:export\s+)?interface\s+(\w+)')
        function_pattern = re.compile(r'(?:export\s+)?(?:async\s+)?function\s+(\w+)')
        const_func_pattern = re.compile(r'(?:export\s+)?const\s+(\w+)(?::\s*[\w\.]+)?\s*=\s*(?:async\s*)?\(.*?\)\s*(?::\s*[\w\.]+)?\s*=>')
        hook_pattern = re.compile(r'const\s+\[(\w+),\s*\w+\]\s*=\s*use\w+\(')
        method_pattern = re.compile(r'^\s*(?:async\s+)?(?:public|private|protected|static\s+)?(\w+)\s*\(.*?\)\s*\{')

        current_class = None
        
        for i, line in enumerate(lines):
            line_num = i + 1
            
            # Class detection
            class_match = class_pattern.search(line)
            if class_match:
                current_class = class_match.group(1)
                end_line = self._find_block_end(lines, i)
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
                end_line = self._find_block_end(lines, i)
                symbols.append(Symbol(
                    name=interface_match.group(1),
                    type="interface",
                    start_line=line_num,
                    end_line=end_line
                ))
                continue

            # Function detection
            func_match = function_pattern.search(line) or const_func_pattern.search(line)
            if func_match:
                end_line = self._find_block_end(lines, i)
                symbols.append(Symbol(
                    name=func_match.group(1),
                    type="function",
                    start_line=line_num,
                    end_line=end_line
                ))
                continue

            # Hook detection
            hook_match = hook_pattern.search(line)
            if hook_match:
                symbols.append(Symbol(
                    name=hook_match.group(1),
                    type="hook",
                    start_line=line_num,
                    end_line=line_num
                ))
                continue

            # Method detection
            if current_class:
                method_match = method_pattern.search(line)
                if method_match:
                    name = method_match.group(1)
                    if name not in {"if", "for", "while", "switch", "catch"}:
                        end_line = self._find_block_end(lines, i)
                        symbols.append(Symbol(
                            name=name,
                            type="method",
                            start_line=line_num,
                            end_line=end_line,
                            parent_id=current_class
                        ))

        return symbols

    def _find_block_end(self, lines: List[str], start_idx: int) -> int:
        """Finds the closing brace for a block starting at start_idx."""
        brace_count = 0
        found_first_brace = False
        
        for i in range(start_idx, len(lines)):
            line = lines[i]
            # Strip comments and strings for better accuracy (simplified)
            clean_line = re.sub(r'//.*|/\*.*?\*/|\'[^\']*\'|"[^"]*"|`[^`]*`', '', line)
            
            brace_count += clean_line.count('{')
            if not found_first_brace and '{' in clean_line:
                found_first_brace = True
            
            brace_count -= clean_line.count('}')
            
            if found_first_brace and brace_count <= 0:
                return i + 1
        
        return start_idx + 1

    def extract_dependencies(self, content: str, file_path: str) -> List[DependencyEdge]:
        edges = []
        lines = content.splitlines()

        # Import patterns
        # import { A, B } from './module'
        # import A from './module'
        # import * as A from './module'
        import_pattern = re.compile(r'import\s+(?:\{?[\s\w,]*\}?|[\w\s\*]+as\s+\w+)?\s*from\s*[\'"](.*?)[\'"]')
        
        # Inheritance
        extends_pattern = re.compile(r'class\s+(\w+)\s+extends\s+(\w+)')
        implements_pattern = re.compile(r'class\s+(\w+)\s+implements\s+([\w\s,]+)')

        # Calls
        call_pattern = re.compile(r'(\w+)\s*\(')

        current_symbol = None

        for i, line in enumerate(lines):
            line_num = i + 1
            
            # Imports
            import_match = import_pattern.search(line)
            if import_match:
                target = import_match.group(1)
                edges.append(DependencyEdge(
                    source_id=file_path,
                    target_id=target,
                    raw_target=target,
                    type="import",
                    is_resolved=False
                ))

            # Inheritance
            extends_match = extends_pattern.search(line)
            if extends_match:
                target = extends_match.group(2)
                edges.append(DependencyEdge(
                    source_id=f"{file_path}:{extends_match.group(1)}",
                    target_id=target,
                    raw_target=target,
                    type="inheritance",
                    is_resolved=False
                ))

            # Calls (very naive, should ideally track current_symbol)
            # For now, let's just extract names that look like calls
            # To avoid noise, we'll only do this if we find a "defining" line
            if 'class' in line or 'function' in line:
                match = re.search(r'(?:class|function)\s+(\w+)', line)
                if match:
                    current_symbol = match.group(1)
            
            if current_symbol:
                calls = call_pattern.findall(line)
                for call in calls:
                    if call not in {"if", "for", "while", "switch", "catch", "function", "super", "this", current_symbol}:
                        edges.append(DependencyEdge(
                            source_id=f"{file_path}:{current_symbol}",
                            target_id=call,
                            raw_target=call,
                            type="call",
                            is_resolved=False,
                            metadata={"line": str(line_num)}
                        ))

        return edges
