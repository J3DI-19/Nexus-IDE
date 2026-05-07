import re
from typing import List, Set, Dict, Optional
from ..base import LanguageAdapter
from ...models.symbol import Symbol, DependencyEdge

class CSharpAdapter(LanguageAdapter):
    def get_supported_extensions(self) -> Set[str]:
        return {".cs"}

    def can_handle(self, rel_path: str) -> bool:
        return rel_path.lower().endswith(".cs")

    def extract_symbols(self, content: str, file_path: str) -> List[Symbol]:
        symbols = []
        lines = content.splitlines()
        
        # Regex patterns for C#
        namespace_pattern = re.compile(r'namespace\s+([\w\.]+)')
        class_pattern = re.compile(r'(?:public|private|internal|protected|static|partial|abstract|sealed\s+)*(?:class|interface|struct|enum)\s+(\w+)')
        method_pattern = re.compile(r'(?:public|private|internal|protected|static|async|virtual|override|abstract\s+)+(?:[\w<>\[\],]+\s+)+(\w+)\s*\(.*?\)\s*(?:where\s+.*?)?\s*\{')
        property_pattern = re.compile(r'(?:public|private|internal|protected|static\s+)+(?:[\w<>\[\],]+\s+)+(\w+)\s*\{\s*(?:get|set)')
        delegate_pattern = re.compile(r'(?:public|private|internal|protected|static\s+)*delegate\s+(?:[\w<>\[\],]+\s+)+(\w+)\s*\(.*?\);')
        event_pattern = re.compile(r'(?:public|private|internal|protected|static\s+)*event\s+(?:[\w<>\[\],]+\s+)+(\w+);')
        attribute_pattern = re.compile(r'\[(\w+)(?:\(.*?\))?\]')

        current_namespace = None
        current_container = None
        
        for i, line in enumerate(lines):
            line_num = i + 1
            
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

            # Class/Interface/Struct/Enum detection
            class_match = class_pattern.search(line)
            if class_match:
                current_container = class_match.group(1)
                symbols.append(Symbol(
                    name=current_container,
                    type="class", # generalized
                    start_line=line_num,
                    end_line=line_num
                ))
                continue

            # Method detection
            method_match = method_pattern.search(line)
            if method_match:
                name = method_match.group(1)
                if name not in {"if", "for", "while", "switch", "catch", "new", "return", "using", "lock"}:
                    symbols.append(Symbol(
                        name=name,
                        type="method",
                        start_line=line_num,
                        end_line=line_num,
                        parent_id=current_container
                    ))
            
            # Property detection
            prop_match = property_pattern.search(line)
            if prop_match:
                symbols.append(Symbol(
                    name=prop_match.group(1),
                    type="property",
                    start_line=line_num,
                    end_line=line_num,
                    parent_id=current_container
                ))

            # Delegate detection
            delegate_match = delegate_pattern.search(line)
            if delegate_match:
                symbols.append(Symbol(
                    name=delegate_match.group(1),
                    type="delegate",
                    start_line=line_num,
                    end_line=line_num,
                    parent_id=current_container
                ))

            # Event detection
            event_match = event_pattern.search(line)
            if event_match:
                symbols.append(Symbol(
                    name=event_match.group(1),
                    type="event",
                    start_line=line_num,
                    end_line=line_num,
                    parent_id=current_container
                ))
            
            # Attribute detection
            attr_match = attribute_pattern.search(line)
            if attr_match:
                symbols.append(Symbol(
                    name=attr_match.group(1),
                    type="attribute",
                    start_line=line_num,
                    end_line=line_num
                ))

        return symbols

    def extract_dependencies(self, content: str, file_path: str) -> List[DependencyEdge]:
        edges = []
        lines = content.splitlines()

        # Using patterns
        using_pattern = re.compile(r'using\s+([\w\.]+);')
        
        # Inheritance
        inheritance_pattern = re.compile(r'(?:class|interface|struct)\s+(\w+)\s*:\s*([\w\s,\.]+)')

        # Calls
        call_pattern = re.compile(r'(\w+)\s*\(')
        await_pattern = re.compile(r'await\s+(\w+)')

        current_symbol = None

        for i, line in enumerate(lines):
            line_num = i + 1
            
            # Usings
            using_match = using_pattern.search(line)
            if using_match:
                edges.append(DependencyEdge(
                    source_id=file_path,
                    target_id=using_match.group(1),
                    type="import"
                ))

            # Inheritance
            inh_match = inheritance_pattern.search(line)
            if inh_match:
                source = inh_match.group(1)
                targets = [t.strip() for t in inh_match.group(2).split(',')]
                for target in targets:
                    edges.append(DependencyEdge(
                        source_id=f"{file_path}:{source}",
                        target_id=target,
                        type="inheritance"
                    ))

            # Calls
            if 'class' in line or '(' in line:
                match = re.search(r'(?:class|interface|struct|enum)\s+(\w+)', line)
                if match:
                    current_symbol = match.group(1)
                else:
                    method_match = re.search(r'\s+(\w+)\s*\(', line)
                    if method_match:
                        current_symbol = method_match.group(1)
            
            if current_symbol:
                # Regular calls
                calls = call_pattern.findall(line)
                for call in calls:
                    if call not in {"if", "for", "while", "switch", "catch", "super", "this", "new", "return", "using", "lock", current_symbol}:
                        edges.append(DependencyEdge(
                            source_id=f"{file_path}:{current_symbol}",
                            target_id=call,
                            type="call",
                            metadata={"line": str(line_num)}
                        ))
                
                # Await calls (async flow)
                await_match = await_pattern.search(line)
                if await_match:
                    edges.append(DependencyEdge(
                        source_id=f"{file_path}:{current_symbol}",
                        target_id=await_match.group(1),
                        type="async_call",
                        metadata={"line": str(line_num)}
                    ))

        return edges
