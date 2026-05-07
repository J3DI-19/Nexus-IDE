import re
from typing import List, Set, Dict, Optional
from ..base import LanguageAdapter
from ...models.symbol import Symbol, DependencyEdge

class CppAdapter(LanguageAdapter):
    def get_supported_extensions(self) -> Set[str]:
        return {".cpp", ".c", ".cc", ".cxx", ".h", ".hpp", ".hxx", ".hh"}

    def can_handle(self, rel_path: str) -> bool:
        ext = rel_path.lower().split('.')[-1]
        return f".{ext}" in self.get_supported_extensions()

    def extract_symbols(self, content: str, file_path: str) -> List[Symbol]:
        symbols = []
        lines = content.splitlines()
        
        # Regex patterns for C++
        namespace_pattern = re.compile(r'namespace\s+([\w\:]+)')
        class_pattern = re.compile(r'(?:class|struct)\s+(\w+)')
        template_pattern = re.compile(r'template\s*<.*?>')
        method_pattern = re.compile(r'(?:[\w\:\*&]+\s+)+(\w+)\s*\(.*?\)\s*(?:const)?\s*(?:\{|;)')
        enum_pattern = re.compile(r'enum\s+(?:class\s+)?(\w+)')
        macro_pattern = re.compile(r'#define\s+(\w+)')

        current_namespace = None
        current_container = None
        
        for i, line in enumerate(lines):
            line_num = i + 1
            
            # Macro detection (highest priority as it can appear anywhere)
            macro_match = macro_pattern.search(line)
            if macro_match:
                symbols.append(Symbol(
                    name=macro_match.group(1),
                    type="macro",
                    start_line=line_num,
                    end_line=line_num
                ))

            # Namespace detection
            ns_match = namespace_pattern.search(line)
            if ns_match:
                current_namespace = ns_match.group(1)
                symbols.append(Symbol(
                    name=current_namespace,
                    type="namespace",
                    start_line=line_num,
                    end_line=line_num
                ))
                continue

            # Class/Struct detection
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

            # Enum detection
            enum_match = enum_pattern.search(line)
            if enum_match:
                symbols.append(Symbol(
                    name=enum_match.group(1),
                    type="enum",
                    start_line=line_num,
                    end_line=line_num
                ))

            # Method/Function detection
            # Filter out common false positives like 'if', 'while', etc.
            method_match = method_pattern.search(line)
            if method_match:
                name = method_match.group(1)
                if name not in {"if", "for", "while", "switch", "catch", "return", "operator"}:
                    symbols.append(Symbol(
                        name=name,
                        type="function",
                        start_line=line_num,
                        end_line=line_num,
                        parent_id=current_container
                    ))

        return symbols

    def extract_dependencies(self, content: str, file_path: str) -> List[DependencyEdge]:
        edges = []
        lines = content.splitlines()

        # Include patterns
        include_pattern = re.compile(r'#include\s+["<](.*?)[">]')
        
        # Inheritance
        inheritance_pattern = re.compile(r'(?:class|struct)\s+(\w+)\s*:\s*(?:public|protected|private)?\s*([\w\s,\:]+)')

        # Calls
        call_pattern = re.compile(r'(\w+)\s*\(')

        current_symbol = None

        for i, line in enumerate(lines):
            line_num = i + 1
            
            # Includes
            include_match = include_pattern.search(line)
            if include_match:
                edges.append(DependencyEdge(
                    source_id=file_path,
                    target_id=include_match.group(1),
                    type="include"
                ))

            # Inheritance
            inh_match = inheritance_pattern.search(line)
            if inh_match:
                source = inh_match.group(1)
                targets = [t.strip().split()[-1] for t in inh_match.group(2).split(',')]
                for target in targets:
                    edges.append(DependencyEdge(
                        source_id=f"{file_path}:{source}",
                        target_id=target,
                        type="inheritance"
                    ))

            # Header/Source relationship
            # If we are in a .cpp file, we likely have a corresponding .h file
            if file_path.endswith((".cpp", ".c", ".cc", ".cxx")):
                base_name = file_path.rsplit('.', 1)[0]
                # This is a heuristic, the actual file might have a different extension or path
                # But it creates a link for the engine to explore.
                edges.append(DependencyEdge(
                    source_id=file_path,
                    target_id=f"{base_name}.h",
                    type="source_header_link"
                ))

            # Calls
            if '(' in line:
                # Naive symbol tracking for source file (not perfect without full AST)
                match = re.search(r'(?:class|struct)\s+(\w+)', line)
                if match:
                    current_symbol = match.group(1)
                else:
                    method_match = re.search(r'\s+(\w+)\s*\(', line)
                    if method_match:
                        current_symbol = method_match.group(1)
            
            if current_symbol:
                calls = call_pattern.findall(line)
                for call in calls:
                    if call not in {"if", "for", "while", "switch", "catch", "return", "sizeof", "alignof", "typeid", current_symbol}:
                        edges.append(DependencyEdge(
                            source_id=f"{file_path}:{current_symbol}",
                            target_id=call,
                            type="call",
                            metadata={"line": str(line_num)}
                        ))

        return edges
